#!/usr/bin/env python3
import argparse
import csv
import json
import math
import statistics
import time

import cv2

from camera import LatestFrameCamera, wait_until_stable
from config import (
    CLASS_THRESHOLDS,
    FRAME_SAMPLE_GAP_SEC,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    IMGSZ,
    INFERENCE_DEVICE,
    INITIAL_PRESET_WAIT_SEC,
    POST_MOVE_FRESH_FRAMES,
    PRESET_BEARING_DEG,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    STATIC_DIR,
)
from detection import FireDetector, _norm
from ptz import PTZController


def wait_fresh_frames(camera, after_seq, count):
    seq = after_seq
    packet = None

    for _ in range(max(1, count)):
        packet = camera.wait_for_newer(seq, timeout=2.0)
        if packet is None:
            return None
        seq = packet.seq

    return packet


def bbox_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)

    inter = iw * ih

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

    union = area_a + area_b - inter

    if union <= 0:
        return 0.0

    return inter / union


def canonical_for(detector, cls_id):
    return detector.class_map.get(int(cls_id))


def extract_diagnostic_detections(detector, frame, diag_conf):
    results = detector.model.predict(
        source=frame,
        imgsz=IMGSZ,
        conf=diag_conf,
        device=INFERENCE_DEVICE,
        verbose=False,
    )

    detections = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            cls_id = int(box.cls[0])

            canonical = canonical_for(detector, cls_id)
            if canonical is None:
                continue

            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append(
                {
                    "class_id": cls_id,
                    "class": canonical,
                    "model_class": str(
                        detector.names.get(cls_id, cls_id)
                    ),
                    "confidence": conf,
                    "bbox": (x1, y1, x2, y2),
                    "production_threshold": float(
                        CLASS_THRESHOLDS[canonical]
                    ),
                    "production_pass": (
                        conf >= CLASS_THRESHOLDS[canonical]
                    ),
                }
            )

    detections.sort(
        key=lambda d: d["confidence"],
        reverse=True,
    )

    return detections


def draw_diagnostic_frame(
    frame,
    *,
    preset,
    sample_index,
    sample_total,
    seq,
    infer_ms,
    detections,
    diag_conf,
):
    out = frame.copy()

    cv2.putText(
        out,
        "SMART FIRE DETECTION v2 | STABILITY TEST",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        out,
        (
            f"Preset={preset} "
            f"| Sample={sample_index}/{sample_total} "
            f"| Seq={seq} "
            f"| Infer={infer_ms:.1f}ms "
            f"| diag_conf={diag_conf:.2f}"
        ),
        (10, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    if not detections:
        cv2.putText(
            out,
            "NO FIRE/SMOKE >= DIAGNOSTIC THRESHOLD",
            (10, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.66,
            (0, 165, 255),
            2,
            cv2.LINE_AA,
        )

    for idx, d in enumerate(detections, start=1):
        x1, y1, x2, y2 = d["bbox"]

        if d["production_pass"]:
            color = (0, 0, 255) if d["class"] == "fire" else (0, 255, 255)
            state = "PASS"
        else:
            color = (255, 255, 0)
            state = "BELOW PROD"

        cv2.rectangle(
            out,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

        label = (
            f"{idx}. {d['class'].upper()} "
            f"{d['confidence']:.3f} "
            f"[{state}; prod={d['production_threshold']:.2f}]"
        )

        cv2.putText(
            out,
            label,
            (x1, max(100, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            color,
            2,
            cv2.LINE_AA,
        )

    return out


def safe_stats(values):
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "std": None,
        }

    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "std": (
            statistics.pstdev(values)
            if len(values) >= 2
            else 0.0
        ),
    }


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Measure Fire/Smoke confidence stability on one fixed PTZ preset "
            "using a low diagnostic threshold."
        )
    )

    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=1,
        help="Preset ที่ต้องการตรึงกล้อง (default: 1)",
    )

    ap.add_argument(
        "--samples",
        type=int,
        default=30,
        help="จำนวน inference samples (default: 30)",
    )

    ap.add_argument(
        "--gap",
        type=float,
        default=0.25,
        help="ช่วงพักระหว่าง sample วินาที (default: 0.25)",
    )

    ap.add_argument(
        "--diag-conf",
        type=float,
        default=0.05,
        help="YOLO diagnostic confidence threshold (default: 0.05)",
    )

    ap.add_argument(
        "--label",
        default="unlabeled",
        help=(
            "ป้ายกำกับการทดลอง เช่น positive_fire หรือ hard_negative "
            "(default: unlabeled)"
        ),
    )

    ap.add_argument(
        "--save-every",
        type=int,
        default=1,
        help="บันทึกภาพทุกกี่ sample; 1=ทุกภาพ (default: 1)",
    )

    args = ap.parse_args()

    if args.samples < 1:
        raise SystemExit("❌ --samples ต้อง >= 1")

    if args.gap < 0:
        raise SystemExit("❌ --gap ต้อง >= 0")

    if not 0.001 <= args.diag_conf <= 1.0:
        raise SystemExit("❌ --diag-conf ต้องอยู่ในช่วง 0.001..1.0")

    if args.save_every < 1:
        raise SystemExit("❌ --save-every ต้อง >= 1")

    run_stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in args.label
    )

    run_dir = (
        STATIC_DIR
        / "stability_runs"
        / f"preset_{args.preset}_{safe_label}_{run_stamp}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 88)
    print("Smart Fire Detection v2 - Detection Stability Test")
    print(f"Preset            : {args.preset}")
    print(f"Center bearing    : {PRESET_BEARING_DEG[args.preset]:.1f}°")
    print(f"Samples           : {args.samples}")
    print(f"Gap               : {args.gap:.3f}s")
    print(f"Diagnostic conf   : {args.diag_conf:.3f}")
    print(f"Production Fire   : {CLASS_THRESHOLDS['fire']:.3f}")
    print(f"Production Smoke  : {CLASS_THRESHOLDS['smoke']:.3f}")
    print(f"Label             : {args.label}")
    print(f"Output            : {run_dir}")
    print("=" * 88)

    print("\n📡 กำลังเปิด RTSP...")
    camera = LatestFrameCamera().start()

    deadline = time.monotonic() + 10.0

    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit("❌ RTSP timeout")
        time.sleep(0.1)

    print("✅ RTSP พร้อม")

    print("\n🧠 กำลังโหลด AI...")
    detector = FireDetector()
    ptz = PTZController()
    print("✅ AI พร้อม")

    print(f"\n🔄 Move -> Preset {args.preset}")
    ok, wait_sec = ptz.goto_preset(args.preset)

    if not ok:
        camera.stop()
        raise SystemExit("❌ PTZ command failed")

    wait_sec = max(wait_sec, INITIAL_PRESET_WAIT_SEC)
    print(f"⏱️ PTZ wait {wait_sec:.2f}s")
    time.sleep(wait_sec)

    arrival_seq = camera.sequence

    fresh = wait_fresh_frames(
        camera,
        arrival_seq,
        POST_MOVE_FRESH_FRAMES,
    )

    if fresh is None:
        camera.stop()
        raise SystemExit("❌ No fresh post-move frame")

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:
        camera.stop()
        raise SystemExit("❌ Image did not become stable")

    print(
        f"✅ Stable frame seq={stable.seq} "
        f"age={time.time() - stable.timestamp:.3f}s"
    )

    print("\n🔥 AI warm-up...")
    warm_start = time.perf_counter()

    extract_diagnostic_detections(
        detector,
        stable.frame,
        args.diag_conf,
    )

    warmup_ms = (
        time.perf_counter() - warm_start
    ) * 1000.0

    print(f"✅ Warm-up completed: {warmup_ms:.1f} ms")

    rows = []
    sample_records = []
    previous_seq = None
    previous_top_bbox = {
        "fire": None,
        "smoke": None,
    }

    print("\n🔬 เริ่ม Stability Sampling")

    try:
        last_packet = stable

        for sample_index in range(1, args.samples + 1):
            if sample_index > 1 and args.gap > 0:
                time.sleep(args.gap)

            packet = camera.wait_for_newer(
                last_packet.seq,
                timeout=2.0,
            )

            if packet is None:
                print(
                    f"[{sample_index:02d}/{args.samples}] "
                    "❌ frame timeout"
                )
                continue

            last_packet = packet

            frame_age_ms = (
                time.time() - packet.timestamp
            ) * 1000.0

            seq_delta = (
                None
                if previous_seq is None
                else packet.seq - previous_seq
            )
            previous_seq = packet.seq

            infer_start = time.perf_counter()

            detections = extract_diagnostic_detections(
                detector,
                packet.frame,
                args.diag_conf,
            )

            infer_ms = (
                time.perf_counter() - infer_start
            ) * 1000.0

            by_class = {
                "fire": [],
                "smoke": [],
            }

            for d in detections:
                if d["class"] in by_class:
                    by_class[d["class"]].append(d)

            top = {
                cls: (
                    max(
                        by_class[cls],
                        key=lambda x: x["confidence"],
                    )
                    if by_class[cls]
                    else None
                )
                for cls in ("fire", "smoke")
            }

            sample_info = {
                "sample": sample_index,
                "seq": packet.seq,
                "seq_delta": seq_delta,
                "frame_age_ms": frame_age_ms,
                "inference_ms": infer_ms,
                "detections": detections,
            }

            sample_records.append(sample_info)

            fire = top["fire"]
            smoke = top["smoke"]

            fire_text = (
                "none"
                if fire is None
                else (
                    f"{fire['confidence']:.3f}"
                    f"{' PASS' if fire['production_pass'] else ' below'}"
                )
            )

            smoke_text = (
                "none"
                if smoke is None
                else (
                    f"{smoke['confidence']:.3f}"
                    f"{' PASS' if smoke['production_pass'] else ' below'}"
                )
            )

            print(
                f"[{sample_index:02d}/{args.samples}] "
                f"seq={packet.seq} "
                f"Δseq={seq_delta if seq_delta is not None else '-':>3} "
                f"age={frame_age_ms:6.2f}ms "
                f"infer={infer_ms:6.1f}ms "
                f"| Fire={fire_text:<12} "
                f"| Smoke={smoke_text}"
            )

            for cls in ("fire", "smoke"):
                d = top[cls]

                if d is None:
                    rows.append(
                        {
                            "sample": sample_index,
                            "seq": packet.seq,
                            "seq_delta": (
                                ""
                                if seq_delta is None
                                else seq_delta
                            ),
                            "frame_age_ms": round(
                                frame_age_ms,
                                3,
                            ),
                            "inference_ms": round(
                                infer_ms,
                                3,
                            ),
                            "class": cls,
                            "confidence": "",
                            "production_threshold": (
                                CLASS_THRESHOLDS[cls]
                            ),
                            "production_pass": False,
                            "x1": "",
                            "y1": "",
                            "x2": "",
                            "y2": "",
                            "iou_prev": "",
                        }
                    )
                    continue

                iou_prev = ""

                if previous_top_bbox[cls] is not None:
                    iou_prev = bbox_iou(
                        previous_top_bbox[cls],
                        d["bbox"],
                    )

                previous_top_bbox[cls] = d["bbox"]

                x1, y1, x2, y2 = d["bbox"]

                rows.append(
                    {
                        "sample": sample_index,
                        "seq": packet.seq,
                        "seq_delta": (
                            ""
                            if seq_delta is None
                            else seq_delta
                        ),
                        "frame_age_ms": round(
                            frame_age_ms,
                            3,
                        ),
                        "inference_ms": round(
                            infer_ms,
                            3,
                        ),
                        "class": cls,
                        "confidence": round(
                            d["confidence"],
                            6,
                        ),
                        "production_threshold": (
                            d["production_threshold"]
                        ),
                        "production_pass": (
                            d["production_pass"]
                        ),
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "iou_prev": (
                            ""
                            if iou_prev == ""
                            else round(iou_prev, 6)
                        ),
                    }
                )

            if sample_index % args.save_every == 0:
                annotated = draw_diagnostic_frame(
                    packet.frame,
                    preset=args.preset,
                    sample_index=sample_index,
                    sample_total=args.samples,
                    seq=packet.seq,
                    infer_ms=infer_ms,
                    detections=detections,
                    diag_conf=args.diag_conf,
                )

                out_path = (
                    run_dir
                    / f"sample_{sample_index:03d}_annotated.jpg"
                )
                cv2.imwrite(
                    str(out_path),
                    annotated,
                )

    finally:
        camera.stop()

    csv_path = run_dir / "samples.csv"

    fieldnames = [
        "sample",
        "seq",
        "seq_delta",
        "frame_age_ms",
        "inference_ms",
        "class",
        "confidence",
        "production_threshold",
        "production_pass",
        "x1",
        "y1",
        "x2",
        "y2",
        "iou_prev",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    class_summary = {}

    for cls in ("fire", "smoke"):
        cls_rows = [
            r for r in rows
            if r["class"] == cls
        ]

        detected_rows = [
            r for r in cls_rows
            if r["confidence"] != ""
        ]

        confs = [
            float(r["confidence"])
            for r in detected_rows
        ]

        prod_pass = [
            r for r in cls_rows
            if r["production_pass"] is True
        ]

        ious = [
            float(r["iou_prev"])
            for r in detected_rows
            if r["iou_prev"] != ""
        ]

        class_summary[cls] = {
            "diagnostic_detection_samples": (
                len(detected_rows)
            ),
            "diagnostic_detection_rate": (
                len(detected_rows) / args.samples
            ),
            "production_pass_samples": (
                len(prod_pass)
            ),
            "production_pass_rate": (
                len(prod_pass) / args.samples
            ),
            "confidence": safe_stats(confs),
            "bbox_iou_to_previous": safe_stats(ious),
        }

    inference_values = [
        float(s["inference_ms"])
        for s in sample_records
    ]

    frame_age_values = [
        float(s["frame_age_ms"])
        for s in sample_records
    ]

    seq_delta_values = [
        int(s["seq_delta"])
        for s in sample_records
        if s["seq_delta"] is not None
    ]

    summary = {
        "timestamp": run_stamp,
        "label": args.label,
        "preset": args.preset,
        "center_bearing_deg": (
            PRESET_BEARING_DEG[args.preset]
        ),
        "requested_samples": args.samples,
        "completed_samples": len(
            sample_records
        ),
        "gap_sec": args.gap,
        "diagnostic_conf": args.diag_conf,
        "production_thresholds": {
            k: float(v)
            for k, v in CLASS_THRESHOLDS.items()
        },
        "warmup_ms": warmup_ms,
        "inference_ms": safe_stats(
            inference_values
        ),
        "frame_age_ms": safe_stats(
            frame_age_values
        ),
        "seq_delta": safe_stats(
            seq_delta_values
        ),
        "classes": class_summary,
    }

    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 88)
    print("DETECTION STABILITY SUMMARY")
    print("=" * 88)

    print(
        f"Completed samples : "
        f"{len(sample_records)}/{args.samples}"
    )

    infer_stats = summary["inference_ms"]

    if infer_stats["count"]:
        print(
            "Inference        : "
            f"mean={infer_stats['mean']:.1f}ms "
            f"min={infer_stats['min']:.1f}ms "
            f"max={infer_stats['max']:.1f}ms "
            f"std={infer_stats['std']:.1f}ms"
        )

    age_stats = summary["frame_age_ms"]

    if age_stats["count"]:
        print(
            "Frame age        : "
            f"mean={age_stats['mean']:.2f}ms "
            f"max={age_stats['max']:.2f}ms"
        )

    delta_stats = summary["seq_delta"]

    if delta_stats["count"]:
        print(
            "Seq delta        : "
            f"mean={delta_stats['mean']:.2f} "
            f"min={delta_stats['min']:.0f} "
            f"max={delta_stats['max']:.0f}"
        )

    for cls in ("fire", "smoke"):
        s = class_summary[cls]

        print("\n" + cls.upper())
        print(
            f"  Diagnostic detected : "
            f"{s['diagnostic_detection_samples']}/"
            f"{args.samples} "
            f"({s['diagnostic_detection_rate'] * 100:.1f}%)"
        )
        print(
            f"  Production pass     : "
            f"{s['production_pass_samples']}/"
            f"{args.samples} "
            f"({s['production_pass_rate'] * 100:.1f}%)"
        )

        c = s["confidence"]

        if c["count"]:
            print(
                f"  Confidence          : "
                f"mean={c['mean']:.3f} "
                f"median={c['median']:.3f} "
                f"min={c['min']:.3f} "
                f"max={c['max']:.3f} "
                f"std={c['std']:.3f}"
            )

        iou = s["bbox_iou_to_previous"]

        if iou["count"]:
            print(
                f"  BBox IoU prev       : "
                f"mean={iou['mean']:.3f} "
                f"min={iou['min']:.3f}"
            )

    print(f"\nCSV     : {csv_path}")
    print(f"Summary : {summary_path}")
    print(f"Images  : {run_dir}")
    print("=" * 88)
    print("✅ Detection stability test completed")


if __name__ == "__main__":
    main()
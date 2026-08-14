#!/usr/bin/env python3
"""
Hard-negative candidate collector for Smart Fire Detection v2.

IMPORTANT:
- This script does NOT automatically label anything as a true negative.
- Run it only in a scene that you know should contain NO real fire/smoke,
  or manually review every saved candidate before adding it to the dataset.
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2

from camera import LatestFrameCamera, wait_until_stable
from config import (
    CLASS_THRESHOLDS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    IMGSZ,
    INFERENCE_DEVICE,
    INITIAL_PRESET_WAIT_SEC,
    POST_MOVE_FRESH_FRAMES,
    PRESET_BEARING_DEG,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    STATIC_DIR,
    SWEEP_SEQUENCE,
)
from detection import FireDetector, bbox_iou
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


def sanitize_name(text):
    return "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in str(text)
    )


def clip_bbox(bbox):
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(FRAME_WIDTH - 1, int(x1)))
    y1 = max(0, min(FRAME_HEIGHT - 1, int(y1)))
    x2 = max(0, min(FRAME_WIDTH, int(x2)))
    y2 = max(0, min(FRAME_HEIGHT, int(y2)))
    return x1, y1, x2, y2


def expand_bbox(bbox, margin_ratio=0.20):
    x1, y1, x2, y2 = clip_bbox(bbox)

    w = max(1, x2 - x1)
    h = max(1, y2 - y1)

    mx = int(w * margin_ratio)
    my = int(h * margin_ratio)

    return clip_bbox(
        (
            x1 - mx,
            y1 - my,
            x2 + mx,
            y2 + my,
        )
    )


def crop_frame(frame, bbox, margin_ratio=0.20):
    x1, y1, x2, y2 = expand_bbox(
        bbox,
        margin_ratio=margin_ratio,
    )

    crop = frame[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    return crop


def draw_candidates(
    frame,
    *,
    preset,
    detections,
    inference_ms,
    sample_no,
    min_save_conf,
):
    out = frame.copy()

    cv2.putText(
        out,
        "SMART FIRE DETECTION v2 | HARD NEGATIVE MINING",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        out,
        (
            f"Preset={preset} "
            f"| Center={PRESET_BEARING_DEG[preset]:.1f}deg "
            f"| Sample={sample_no} "
            f"| Infer={inference_ms:.1f}ms "
            f"| SaveConf>={min_save_conf:.2f}"
        ),
        (10, 49),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.49,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    for i, det in enumerate(detections, start=1):
        x1, y1, x2, y2 = det["bbox"]

        if det["production_pass"]:
            color = (0, 0, 255)
            state = "PROD PASS"
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
            f"{i}. {det['class'].upper()} "
            f"{det['confidence']:.3f} "
            f"[{state}]"
        )

        cv2.putText(
            out,
            label,
            (x1, max(78, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            2,
            cv2.LINE_AA,
        )

    return out


def predict_candidates(detector, frame, diag_conf):
    """
    Run the underlying YOLO model with a lower diagnostic threshold,
    then map only known Fire/Smoke classes.
    """
    results = detector.model.predict(
        source=frame,
        imgsz=IMGSZ,
        conf=diag_conf,
        device=INFERENCE_DEVICE,
        verbose=False,
    )

    candidates = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            cls_id = int(box.cls[0])

            if cls_id not in detector.class_map:
                continue

            canonical = detector.class_map[cls_id]
            confidence = float(box.conf[0])

            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0],
            )
            bbox = clip_bbox(
                (x1, y1, x2, y2)
            )

            candidates.append(
                {
                    "class_id": cls_id,
                    "class": canonical,
                    "model_class": str(
                        detector.names.get(
                            cls_id,
                            cls_id,
                        )
                    ),
                    "confidence": confidence,
                    "production_threshold": float(
                        CLASS_THRESHOLDS[canonical]
                    ),
                    "production_pass": (
                        confidence
                        >= CLASS_THRESHOLDS[canonical]
                    ),
                    "bbox": bbox,
                }
            )

    candidates.sort(
        key=lambda x: x["confidence"],
        reverse=True,
    )

    return candidates


def should_save_candidate(
    *,
    det,
    preset,
    now,
    recent,
    cooldown_sec,
    duplicate_iou,
):
    """
    Avoid writing the same near-identical false positive every frame.
    A candidate is considered a duplicate when:
    - same preset
    - same class
    - IoU is high
    - saved less than cooldown_sec ago
    """
    key = (preset, det["class"])

    previous = recent.get(key)

    if previous is None:
        return True

    age = now - previous["timestamp"]

    if age >= cooldown_sec:
        return True

    iou = bbox_iou(
        previous["bbox"],
        det["bbox"],
    )

    if iou < duplicate_iou:
        return True

    return False


def goto_and_stabilize(
    camera,
    ptz,
    preset,
    *,
    first_move=False,
):
    ok, wait_sec = ptz.goto_preset(preset)

    if not ok:
        print(
            f"❌ PTZ command failed: preset={preset}"
        )
        return None

    if first_move:
        wait_sec = max(
            wait_sec,
            INITIAL_PRESET_WAIT_SEC,
        )

    print(
        f"🔄 Preset {preset} "
        f"center={PRESET_BEARING_DEG[preset]:.1f}° "
        f"| wait={wait_sec:.2f}s"
    )

    time.sleep(wait_sec)

    arrival_seq = camera.sequence

    fresh = wait_fresh_frames(
        camera,
        arrival_seq,
        POST_MOVE_FRESH_FRAMES,
    )

    if fresh is None:
        print(
            f"❌ No fresh frame at preset {preset}"
        )
        return None

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:
        print(
            f"❌ Image not stable at preset {preset}"
        )
        return None

    print(
        f"✅ Stable seq={stable.seq} "
        f"age={(time.time() - stable.timestamp) * 1000:.1f}ms"
    )

    return stable


def save_event(
    *,
    run_dir,
    frame,
    annotated,
    det,
    preset,
    sample_no,
    event_no,
    sequence,
    inference_ms,
    frame_age_ms,
    timestamp,
    crop_margin,
):
    class_dir = (
        run_dir
        / "candidates"
        / det["class"]
    )
    full_dir = class_dir / "full"
    crop_dir = class_dir / "crop"
    ann_dir = class_dir / "annotated"

    for folder in (
        full_dir,
        crop_dir,
        ann_dir,
    ):
        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

    stem = (
        f"event_{event_no:04d}_"
        f"preset_{preset}_"
        f"sample_{sample_no:04d}_"
        f"{det['class']}_"
        f"conf_{det['confidence']:.3f}"
    )

    full_path = full_dir / f"{stem}.jpg"
    crop_path = crop_dir / f"{stem}_crop.jpg"
    ann_path = ann_dir / f"{stem}_annotated.jpg"

    cv2.imwrite(
        str(full_path),
        frame,
    )
    cv2.imwrite(
        str(ann_path),
        annotated,
    )

    crop = crop_frame(
        frame,
        det["bbox"],
        margin_ratio=crop_margin,
    )

    if crop is not None:
        cv2.imwrite(
            str(crop_path),
            crop,
        )
    else:
        crop_path = None

    x1, y1, x2, y2 = det["bbox"]

    return {
        "event_id": event_no,
        "timestamp_unix": timestamp,
        "timestamp_local": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(timestamp),
        ),
        "preset": preset,
        "center_bearing_deg": (
            PRESET_BEARING_DEG[preset]
        ),
        "sample_no": sample_no,
        "frame_seq": sequence,
        "frame_age_ms": round(
            frame_age_ms,
            3,
        ),
        "inference_ms": round(
            inference_ms,
            3,
        ),
        "class": det["class"],
        "model_class": det["model_class"],
        "confidence": round(
            det["confidence"],
            6,
        ),
        "production_threshold": (
            det["production_threshold"]
        ),
        "production_pass": (
            det["production_pass"]
        ),
        "bbox": [
            x1,
            y1,
            x2,
            y2,
        ],
        "full_image": str(
            full_path.relative_to(
                run_dir
            )
        ),
        "crop_image": (
            None
            if crop_path is None
            else str(
                crop_path.relative_to(
                    run_dir
                )
            )
        ),
        "annotated_image": str(
            ann_path.relative_to(
                run_dir
            )
        ),
        # Manual-review fields intentionally left unset.
        "review_label": None,
        "review_notes": "",
    }


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Collect possible Fire/Smoke false-positive candidates "
            "for manual hard-negative review."
        )
    )

    ap.add_argument(
        "--mode",
        choices=("fixed", "sweep"),
        default="fixed",
        help=(
            "fixed=ตรึง preset เดียว, "
            "sweep=กวาด SWEEP_SEQUENCE"
        ),
    )

    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=1,
        help=(
            "Preset สำหรับ mode=fixed "
            "(default: 1)"
        ),
    )

    ap.add_argument(
        "--samples",
        type=int,
        default=100,
        help=(
            "จำนวน samples สำหรับ mode=fixed "
            "(default: 100)"
        ),
    )

    ap.add_argument(
        "--samples-per-preset",
        type=int,
        default=5,
        help=(
            "จำนวน samples ต่อ stop สำหรับ mode=sweep "
            "(default: 5)"
        ),
    )

    ap.add_argument(
        "--cycles",
        type=int,
        default=1,
        help=(
            "จำนวน sweep cycles "
            "(default: 1)"
        ),
    )

    ap.add_argument(
        "--gap",
        type=float,
        default=0.30,
        help=(
            "ช่วงเวลาระหว่าง samples "
            "(default: 0.30s)"
        ),
    )

    ap.add_argument(
        "--diag-conf",
        type=float,
        default=0.05,
        help=(
            "YOLO diagnostic threshold "
            "(default: 0.05)"
        ),
    )

    ap.add_argument(
        "--min-save-conf",
        type=float,
        default=0.30,
        help=(
            "เก็บ candidate เมื่อ confidence >= ค่านี้ "
            "(default: 0.30)"
        ),
    )

    ap.add_argument(
        "--save-cooldown",
        type=float,
        default=2.0,
        help=(
            "ลดภาพซ้ำ: รออย่างน้อยกี่วินาทีก่อนเก็บ bbox เดิม "
            "(default: 2.0)"
        ),
    )

    ap.add_argument(
        "--duplicate-iou",
        type=float,
        default=0.85,
        help=(
            "IoU ที่ถือว่า candidate ซ้ำ "
            "(default: 0.85)"
        ),
    )

    ap.add_argument(
        "--crop-margin",
        type=float,
        default=0.20,
        help=(
            "พื้นที่เผื่อรอบ crop เป็นสัดส่วน bbox "
            "(default: 0.20)"
        ),
    )

    ap.add_argument(
        "--scene-label",
        default="known_no_fire_scene",
        help=(
            "ชื่อฉาก/ชุดทดลองสำหรับ metadata"
        ),
    )

    args = ap.parse_args()

    if args.samples < 1:
        raise SystemExit(
            "❌ --samples ต้อง >= 1"
        )

    if args.samples_per_preset < 1:
        raise SystemExit(
            "❌ --samples-per-preset ต้อง >= 1"
        )

    if args.cycles < 1:
        raise SystemExit(
            "❌ --cycles ต้อง >= 1"
        )

    if args.gap < 0:
        raise SystemExit(
            "❌ --gap ต้อง >= 0"
        )

    if not 0.001 <= args.diag_conf <= 1.0:
        raise SystemExit(
            "❌ --diag-conf ต้องอยู่ 0.001..1.0"
        )

    if not args.diag_conf <= args.min_save_conf <= 1.0:
        raise SystemExit(
            "❌ --min-save-conf ต้อง >= --diag-conf และ <= 1.0"
        )

    if not 0.0 <= args.duplicate_iou <= 1.0:
        raise SystemExit(
            "❌ --duplicate-iou ต้องอยู่ 0..1"
        )

    run_stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    safe_scene = sanitize_name(
        args.scene_label
    )

    run_dir = (
        STATIC_DIR
        / "hard_negative_runs"
        / f"{safe_scene}_{run_stamp}"
    )
    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 92)
    print(
        "Smart Fire Detection v2 - Hard Negative Candidate Collector"
    )
    print(f"Mode              : {args.mode}")
    print(f"Scene label       : {args.scene_label}")
    print(f"Diagnostic conf   : {args.diag_conf:.3f}")
    print(f"Min save conf     : {args.min_save_conf:.3f}")
    print(f"Duplicate IoU     : {args.duplicate_iou:.2f}")
    print(f"Save cooldown     : {args.save_cooldown:.2f}s")
    print(f"Output            : {run_dir}")
    print("")
    print(
        "⚠️ เก็บเป็น CANDIDATE เท่านั้น "
        "ต้อง review ก่อนนำเข้า negative dataset"
    )
    print("=" * 92)

    print("\n📡 กำลังเปิด RTSP...")
    camera = LatestFrameCamera().start()

    deadline = time.monotonic() + 10.0

    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit(
                "❌ RTSP timeout"
            )
        time.sleep(0.1)

    print("✅ RTSP พร้อม")

    print("\n🧠 กำลังโหลด AI...")
    detector = FireDetector()
    ptz = PTZController()
    print("✅ AI พร้อม")

    warm_packet = camera.latest(copy=True)

    print("\n🔥 AI warm-up...")
    t0 = time.perf_counter()

    predict_candidates(
        detector,
        warm_packet.frame,
        args.diag_conf,
    )

    warmup_ms = (
        time.perf_counter() - t0
    ) * 1000.0

    print(
        f"✅ Warm-up completed: "
        f"{warmup_ms:.1f}ms"
    )

    recent = {}
    records = []
    event_no = 0
    sample_no = 0
    first_move = True

    if args.mode == "fixed":
        plan = [
            args.preset
        ]
        total_samples_expected = args.samples
    else:
        plan = (
            SWEEP_SEQUENCE
            * args.cycles
        )
        total_samples_expected = (
            len(plan)
            * args.samples_per_preset
        )

    try:
        if args.mode == "fixed":
            stable = goto_and_stabilize(
                camera,
                ptz,
                args.preset,
                first_move=True,
            )

            if stable is None:
                raise SystemExit(
                    "❌ ไม่สามารถเตรียม fixed preset ได้"
                )

            packet = stable

            for _ in range(args.samples):
                sample_no += 1

                if sample_no > 1:
                    if args.gap > 0:
                        time.sleep(args.gap)

                    new_packet = camera.wait_for_newer(
                        packet.seq,
                        timeout=2.0,
                    )

                    if new_packet is None:
                        print(
                            f"[{sample_no:04d}/"
                            f"{total_samples_expected}] "
                            "frame timeout"
                        )
                        continue

                    packet = new_packet

                inference_start = (
                    time.perf_counter()
                )

                detections = predict_candidates(
                    detector,
                    packet.frame,
                    args.diag_conf,
                )

                inference_ms = (
                    time.perf_counter()
                    - inference_start
                ) * 1000.0

                frame_age_ms = (
                    time.time()
                    - packet.timestamp
                ) * 1000.0

                saveable = [
                    d
                    for d in detections
                    if d["confidence"]
                    >= args.min_save_conf
                ]

                annotated = draw_candidates(
                    packet.frame,
                    preset=args.preset,
                    detections=saveable,
                    inference_ms=inference_ms,
                    sample_no=sample_no,
                    min_save_conf=args.min_save_conf,
                )

                saved_now = 0

                for det in saveable:
                    now = time.time()

                    if not should_save_candidate(
                        det=det,
                        preset=args.preset,
                        now=now,
                        recent=recent,
                        cooldown_sec=(
                            args.save_cooldown
                        ),
                        duplicate_iou=(
                            args.duplicate_iou
                        ),
                    ):
                        continue

                    event_no += 1

                    record = save_event(
                        run_dir=run_dir,
                        frame=packet.frame,
                        annotated=annotated,
                        det=det,
                        preset=args.preset,
                        sample_no=sample_no,
                        event_no=event_no,
                        sequence=packet.seq,
                        inference_ms=inference_ms,
                        frame_age_ms=frame_age_ms,
                        timestamp=now,
                        crop_margin=args.crop_margin,
                    )

                    record["scene_label"] = (
                        args.scene_label
                    )

                    records.append(
                        record
                    )

                    recent[
                        (
                            args.preset,
                            det["class"],
                        )
                    ] = {
                        "timestamp": now,
                        "bbox": det["bbox"],
                    }

                    saved_now += 1

                print(
                    f"[{sample_no:04d}/"
                    f"{total_samples_expected}] "
                    f"preset={args.preset} "
                    f"seq={packet.seq} "
                    f"age={frame_age_ms:.1f}ms "
                    f"infer={inference_ms:.1f}ms "
                    f"pred={len(detections)} "
                    f">={args.min_save_conf:.2f}:"
                    f"{len(saveable)} "
                    f"saved={saved_now}"
                )

        else:
            for preset in plan:
                stable = goto_and_stabilize(
                    camera,
                    ptz,
                    preset,
                    first_move=first_move,
                )
                first_move = False

                if stable is None:
                    continue

                packet = stable

                for local_index in range(
                    1,
                    args.samples_per_preset + 1,
                ):
                    sample_no += 1

                    if local_index > 1:
                        if args.gap > 0:
                            time.sleep(
                                args.gap
                            )

                        new_packet = (
                            camera.wait_for_newer(
                                packet.seq,
                                timeout=2.0,
                            )
                        )

                        if new_packet is None:
                            print(
                                f"[{sample_no:04d}/"
                                f"{total_samples_expected}] "
                                "frame timeout"
                            )
                            continue

                        packet = new_packet

                    inference_start = (
                        time.perf_counter()
                    )

                    detections = (
                        predict_candidates(
                            detector,
                            packet.frame,
                            args.diag_conf,
                        )
                    )

                    inference_ms = (
                        time.perf_counter()
                        - inference_start
                    ) * 1000.0

                    frame_age_ms = (
                        time.time()
                        - packet.timestamp
                    ) * 1000.0

                    saveable = [
                        d
                        for d in detections
                        if d["confidence"]
                        >= args.min_save_conf
                    ]

                    annotated = (
                        draw_candidates(
                            packet.frame,
                            preset=preset,
                            detections=saveable,
                            inference_ms=(
                                inference_ms
                            ),
                            sample_no=sample_no,
                            min_save_conf=(
                                args.min_save_conf
                            ),
                        )
                    )

                    saved_now = 0

                    for det in saveable:
                        now = time.time()

                        if not should_save_candidate(
                            det=det,
                            preset=preset,
                            now=now,
                            recent=recent,
                            cooldown_sec=(
                                args.save_cooldown
                            ),
                            duplicate_iou=(
                                args.duplicate_iou
                            ),
                        ):
                            continue

                        event_no += 1

                        record = save_event(
                            run_dir=run_dir,
                            frame=packet.frame,
                            annotated=annotated,
                            det=det,
                            preset=preset,
                            sample_no=sample_no,
                            event_no=event_no,
                            sequence=packet.seq,
                            inference_ms=(
                                inference_ms
                            ),
                            frame_age_ms=(
                                frame_age_ms
                            ),
                            timestamp=now,
                            crop_margin=(
                                args.crop_margin
                            ),
                        )

                        record[
                            "scene_label"
                        ] = args.scene_label

                        records.append(
                            record
                        )

                        recent[
                            (
                                preset,
                                det["class"],
                            )
                        ] = {
                            "timestamp": now,
                            "bbox": det["bbox"],
                        }

                        saved_now += 1

                    print(
                        f"[{sample_no:04d}/"
                        f"{total_samples_expected}] "
                        f"preset={preset} "
                        f"seq={packet.seq} "
                        f"age={frame_age_ms:.1f}ms "
                        f"infer={inference_ms:.1f}ms "
                        f"pred={len(detections)} "
                        f">={args.min_save_conf:.2f}:"
                        f"{len(saveable)} "
                        f"saved={saved_now}"
                    )

    except KeyboardInterrupt:
        print(
            "\n🛑 Collector stopped by user"
        )

    finally:
        camera.stop()

    jsonl_path = (
        run_dir
        / "candidates.jsonl"
    )

    with jsonl_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        for record in records:
            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    csv_path = (
        run_dir
        / "candidates.csv"
    )

    csv_fields = [
        "event_id",
        "timestamp_local",
        "scene_label",
        "preset",
        "center_bearing_deg",
        "sample_no",
        "frame_seq",
        "frame_age_ms",
        "inference_ms",
        "class",
        "model_class",
        "confidence",
        "production_threshold",
        "production_pass",
        "bbox",
        "full_image",
        "crop_image",
        "annotated_image",
        "review_label",
        "review_notes",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=csv_fields,
        )
        writer.writeheader()

        for record in records:
            row = {
                key: record.get(
                    key,
                    "",
                )
                for key in csv_fields
            }

            row["bbox"] = json.dumps(
                record["bbox"]
            )

            writer.writerow(
                row
            )

    summary = {
        "timestamp": run_stamp,
        "mode": args.mode,
        "scene_label": args.scene_label,
        "diagnostic_conf": args.diag_conf,
        "min_save_conf": args.min_save_conf,
        "production_thresholds": {
            key: float(value)
            for key, value
            in CLASS_THRESHOLDS.items()
        },
        "warmup_ms": warmup_ms,
        "samples_attempted": sample_no,
        "candidate_events_saved": len(
            records
        ),
        "by_class": {
            cls: sum(
                1
                for record in records
                if record["class"] == cls
            )
            for cls in ("fire", "smoke")
        },
        "production_pass_candidates": sum(
            1
            for record in records
            if record["production_pass"]
        ),
        "review_required": True,
    }

    summary_path = (
        run_dir
        / "summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 92)
    print("HARD NEGATIVE COLLECTION SUMMARY")
    print("=" * 92)
    print(
        f"Samples attempted      : "
        f"{sample_no}"
    )
    print(
        f"Candidate events saved : "
        f"{len(records)}"
    )
    print(
        f"  Fire candidates      : "
        f"{summary['by_class']['fire']}"
    )
    print(
        f"  Smoke candidates     : "
        f"{summary['by_class']['smoke']}"
    )
    print(
        f"Production-pass cand.  : "
        f"{summary['production_pass_candidates']}"
    )
    print(f"CSV                    : {csv_path}")
    print(f"JSONL                  : {jsonl_path}")
    print(f"Summary                : {summary_path}")
    print(f"Images                 : {run_dir}")
    print("")
    print(
        "⚠️ อย่านำ candidates ทั้งหมดเข้า negative dataset อัตโนมัติ"
    )
    print(
        "   ให้เปิด annotated/crop ตรวจด้วยคนก่อน:"
    )
    print(
        "   TRUE_NEGATIVE = ไม่มีไฟ/ควันจริง -> ใช้เป็น hard negative"
    )
    print(
        "   ACTUAL_FIRE/SMOKE = มีไฟ/ควันจริง -> ห้ามใส่เป็น negative"
    )
    print("=" * 92)
    print("✅ Hard-negative candidate collection completed")


if __name__ == "__main__":
    main()
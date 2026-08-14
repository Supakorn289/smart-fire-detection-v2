#!/usr/bin/env python3
import argparse
import time
from pathlib import Path

import cv2

from camera import LatestFrameCamera, wait_until_stable
from config import (
    PRESET_BEARING_DEG,
    POST_MOVE_FRESH_FRAMES,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    FRAMES_PER_SCAN,
    MIN_CONFIRM_FRAMES,
    FRAME_SAMPLE_GAP_SEC,
    STATIC_DIR,
)
from detection import FireDetector, consensus
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


def print_detection(prefix, d):
    gps_text = "None"
    if d.gps is not None:
        gps_text = f"{d.gps[0]:.8f}, {d.gps[1]:.8f}"

    distance_text = (
        "None"
        if d.distance_m is None
        else f"{d.distance_m:.3f} m"
    )

    print(
        f"{prefix}"
        f"class={d.canonical_class} "
        f"model_class={d.model_class!r} "
        f"conf={d.confidence:.3f} "
        f"bbox={d.bbox} "
        f"bearing={d.bearing_deg:.3f}° "
        f"distance={distance_text} "
        f"quality={d.distance_quality} "
        f"gps={gps_text}"
    )


def put_text_block(img, lines, x=10, y=24, scale=0.55, color=(0, 255, 0), thickness=2, line_gap=24):
    yy = y
    for line in lines:
        cv2.putText(
            img,
            line,
            (x, yy),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
        yy += line_gap


def annotate_frame(frame, detections, preset, frame_index, frame_total, seq, infer_ms):
    out = frame.copy()

    header_lines = [
        "SMART FIRE DETECTION v2 | AI TEST",
        f"Preset={preset} | Center Bearing={PRESET_BEARING_DEG[preset]:.1f} deg | Frame {frame_index}/{frame_total} | Seq={seq}",
        f"Inference={infer_ms:.1f} ms | Detections={len(detections)}",
    ]
    put_text_block(out, header_lines, x=10, y=24, color=(0, 255, 255), thickness=2, line_gap=24)

    if not detections:
        cv2.putText(
            out,
            "NO FIRE/SMOKE ABOVE THRESHOLD",
            (10, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 165, 255),
            2,
            cv2.LINE_AA,
        )
        return out

    for idx, d in enumerate(detections, start=1):
        x1, y1, x2, y2 = d.bbox
        color = (0, 0, 255) if d.canonical_class == "fire" else (0, 255, 255)

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        distance_text = "N/A"
        if d.distance_m is not None:
            distance_text = f"{d.distance_m:.3f} m"

        gps_text = "gps=None"
        if d.gps is not None:
            gps_text = f"gps={d.gps[0]:.8f},{d.gps[1]:.8f}"

        label_lines = [
            f"{idx}. {d.canonical_class.upper()} conf={d.confidence:.3f}",
            f"bearing={d.bearing_deg:.3f} deg",
            f"distance={distance_text} ({d.distance_quality})",
            gps_text,
        ]

        tx = x1
        ty = max(18, y1 - 72)
        if ty <= 20:
            ty = min(out.shape[0] - 90, y2 + 20)

        put_text_block(out, label_lines, x=tx, y=ty, scale=0.50, color=color, thickness=2, line_gap=18)

        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        cv2.circle(out, (cx, cy), 4, color, -1)

    return out


def save_frame_pair(run_dir: Path, stem: str, raw_frame, annotated_frame):
    raw_path = run_dir / f"{stem}_raw.jpg"
    ann_path = run_dir / f"{stem}_annotated.jpg"

    ok1 = cv2.imwrite(str(raw_path), raw_frame)
    ok2 = cv2.imwrite(str(ann_path), annotated_frame)

    if not ok1 or not ok2:
        raise RuntimeError(f"Save image failed for stem={stem}")

    return raw_path, ann_path


def write_summary(run_dir: Path, preset: int, detections_per_frame, confirmed):
    lines = []
    lines.append("Smart Fire Detection v2 - Detection Test Summary")
    lines.append(f"Preset: {preset}")
    lines.append(f"Center Bearing: {PRESET_BEARING_DEG[preset]:.1f} deg")
    lines.append("")

    for idx, entry in enumerate(detections_per_frame, start=1):
        seq = entry["seq"]
        infer_ms = entry["infer_ms"]
        detections = entry["detections"]
        lines.append(f"Frame {idx}: seq={seq} inference={infer_ms:.1f} ms detections={len(detections)}")
        if not detections:
            lines.append("  - no Fire/Smoke above configured threshold")
        else:
            for d in detections:
                gps_text = "None"
                if d.gps is not None:
                    gps_text = f"{d.gps[0]:.8f}, {d.gps[1]:.8f}"

                distance_text = "None" if d.distance_m is None else f"{d.distance_m:.3f} m"
                lines.append(
                    "  - "
                    f"class={d.canonical_class} "
                    f"model_class={d.model_class!r} "
                    f"conf={d.confidence:.3f} "
                    f"bbox={d.bbox} "
                    f"bearing={d.bearing_deg:.3f}° "
                    f"distance={distance_text} "
                    f"quality={d.distance_quality} "
                    f"gps={gps_text}"
                )
        lines.append("")

    lines.append("Consensus result")
    if not confirmed:
        lines.append("  - no confirmed detection")
    else:
        lines.append(f"  - confirmed detections: {len(confirmed)}")
        for d in confirmed:
            gps_text = "None"
            if d.gps is not None:
                gps_text = f"{d.gps[0]:.8f}, {d.gps[1]:.8f}"
            distance_text = "None" if d.distance_m is None else f"{d.distance_m:.3f} m"
            lines.append(
                "    * "
                f"class={d.canonical_class} "
                f"conf={d.confidence:.3f} "
                f"bbox={d.bbox} "
                f"bearing={d.bearing_deg:.3f}° "
                f"distance={distance_text} "
                f"quality={d.distance_quality} "
                f"gps={gps_text}"
            )

    summary_path = run_dir / "summary.txt"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def main():
    parser = argparse.ArgumentParser(
        description="Live AI pipeline test: RTSP -> PTZ -> AI -> bearing -> distance -> GPS"
    )
    parser.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=1,
        help="Preset ที่ต้องการทดสอบ (default: 1)",
    )
    args = parser.parse_args()

    preset = args.preset

    print("=" * 76)
    print("Smart Fire Detection v2 - Live Detection Pipeline Test")
    print(f"Preset: {preset}")
    print(f"Center bearing: {PRESET_BEARING_DEG[preset]:.1f}°")
    print(f"Frames per scan: {FRAMES_PER_SCAN}")
    print(f"Minimum confirm frames: {MIN_CONFIRM_FRAMES}")
    print("=" * 76)

    run_stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = STATIC_DIR / "detection_runs" / f"preset_{preset}_{run_stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Output dir: {run_dir}")

    print("\n📡 กำลังเปิด RTSP...")
    camera = LatestFrameCamera().start()

    deadline = time.monotonic() + 10.0
    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit("❌ RTSP timeout")
        time.sleep(0.1)

    print("✅ RTSP พร้อม")

    print("\n🧠 กำลังโหลดโมเดล...")
    detector = FireDetector()
    print("✅ Model พร้อม")

    ptz = PTZController()

    try:
        print(f"\n🔄 Move -> Preset {preset}")
        ok, wait_sec = ptz.goto_preset(preset)
        if not ok:
            raise RuntimeError("PTZ command failed")

        print(f"⏱️ รอ PTZ {wait_sec:.2f}s")
        time.sleep(wait_sec)

        arrival_seq = camera.sequence

        fresh = wait_fresh_frames(
            camera,
            arrival_seq,
            POST_MOVE_FRESH_FRAMES,
        )
        if fresh is None:
            raise RuntimeError("No fresh post-move frame")

        stable = wait_until_stable(
            camera,
            fresh.seq,
            STABLE_DIFF_THRESHOLD,
            STABLE_REQUIRED_PAIRS,
            STABLE_TIMEOUT_SEC,
        )
        if stable is None:
            raise RuntimeError("Image did not become stable")

        print(
            f"✅ Fresh + stable frame | "
            f"seq={stable.seq} "
            f"age={time.time() - stable.timestamp:.3f}s"
        )

        detection_sets = []
        packets = []
        detections_per_frame = []
        packet = stable

        print("\n🔎 เริ่ม AI inference")

        for i in range(FRAMES_PER_SCAN):
            if i > 0:
                time.sleep(FRAME_SAMPLE_GAP_SEC)
                packet = camera.wait_for_newer(
                    packet.seq,
                    timeout=2.0,
                )
                if packet is None:
                    print(f"⚠️ Frame #{i+1}: timeout")
                    break

            packets.append(packet)

            t0 = time.perf_counter()
            detections = detector.detect(packet.frame, preset)
            infer_ms = (time.perf_counter() - t0) * 1000.0

            detection_sets.append(detections)
            detections_per_frame.append(
                {
                    "seq": packet.seq,
                    "infer_ms": infer_ms,
                    "detections": detections,
                }
            )

            print(
                f"\nFrame {i+1}/{FRAMES_PER_SCAN} "
                f"| seq={packet.seq} "
                f"| inference={infer_ms:.1f} ms "
                f"| detections={len(detections)}"
            )

            if not detections:
                print("  - no Fire/Smoke above configured threshold")
            else:
                for d in detections:
                    print_detection("  - ", d)

            annotated = annotate_frame(
                packet.frame,
                detections,
                preset,
                i + 1,
                FRAMES_PER_SCAN,
                packet.seq,
                infer_ms,
            )
            raw_path, ann_path = save_frame_pair(
                run_dir,
                f"frame_{i+1:02d}",
                packet.frame,
                annotated,
            )
            print(f"  💾 saved raw       -> {raw_path}")
            print(f"  💾 saved annotated -> {ann_path}")

        confirmed = consensus(
            detection_sets,
            MIN_CONFIRM_FRAMES,
        )

        print("\n" + "=" * 76)
        print("Consensus result")
        print("=" * 76)

        if not confirmed:
            print(
                "ℹ️ ไม่มี detection ที่ยืนยันครบตามจำนวนเฟรม "
                f"({MIN_CONFIRM_FRAMES}/{FRAMES_PER_SCAN})"
            )
        else:
            print(f"✅ Confirmed detections: {len(confirmed)}")
            for d in confirmed:
                print_detection("  - ", d)

        if packets:
            result_frame = packets[-1].frame.copy()
            last_seq = packets[-1].seq
        else:
            result_frame = stable.frame.copy()
            last_seq = stable.seq

        result_annotated = annotate_frame(
            result_frame,
            confirmed,
            preset,
            len(detections_per_frame),
            FRAMES_PER_SCAN,
            last_seq,
            detections_per_frame[-1]["infer_ms"] if detections_per_frame else 0.0,
        )

        state_text = "CONFIRMED DETECTION" if confirmed else "NO CONFIRMED DETECTION"
        state_color = (0, 255, 0) if confirmed else (0, 165, 255)
        cv2.putText(
            result_annotated,
            state_text,
            (10, 125),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            state_color,
            2,
            cv2.LINE_AA,
        )

        final_raw = run_dir / "final_raw.jpg"
        final_ann = run_dir / "final_annotated.jpg"
        if not cv2.imwrite(str(final_raw), result_frame):
            raise RuntimeError(f"Save image failed: {final_raw}")
        if not cv2.imwrite(str(final_ann), result_annotated):
            raise RuntimeError(f"Save image failed: {final_ann}")

        print(f"\n📷 Saved final raw       -> {final_raw}")
        print(f"📷 Saved final annotated -> {final_ann}")

        summary_path = write_summary(run_dir, preset, detections_per_frame, confirmed)
        print(f"📝 Saved summary         -> {summary_path}")

        print("\nPipeline checks:")
        print("  RTSP / fresh frame        ✅")
        print("  PTZ / stable frame        ✅")
        print("  YOLO inference            ✅")
        print("  Fire/Smoke class mapping  ✅")

        if confirmed:
            print("  Consensus                 ✅ detection confirmed")
            print("  Pixel X -> bearing        ✅ calculated")

            if any(d.distance_m is not None for d in confirmed):
                print("  Pixel Y -> distance       ✅ calculated")
            else:
                print("  Pixel Y -> distance       ⚠️ unavailable/out of calibrated range")

            if any(d.gps is not None for d in confirmed):
                print("  Bearing+distance -> GPS   ✅ calculated")
            else:
                print("  Bearing+distance -> GPS   ⚠️ unavailable without valid distance")
        else:
            print("  Consensus                 ℹ️ no confirmed Fire/Smoke")
            print("  Bearing/Distance/GPS      ℹ️ skipped because no confirmed target")

        print("\n✅ Live detection pipeline test completed")

    finally:
        camera.stop()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import argparse
import json
import time

import cv2

from camera import LatestFrameCamera, wait_until_stable
from config import (
    SWEEP_SEQUENCE,
    PRESET_BEARING_DEG,
    INITIAL_PRESET_WAIT_SEC,
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
from geometry import bearing_to_compass
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


def put_text(
    frame,
    text,
    xy,
    color=(0, 255, 255),
    scale=0.55,
    thickness=2,
):
    cv2.putText(
        frame,
        text,
        xy,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def detection_to_dict(d):
    return {
        "class": d.canonical_class,
        "model_class": d.model_class,
        "confidence": round(float(d.confidence), 6),
        "bbox": list(d.bbox),
        "bearing_deg": round(float(d.bearing_deg), 6),
        "distance_m": (
            None if d.distance_m is None
            else round(float(d.distance_m), 6)
        ),
        "distance_quality": d.distance_quality,
        "gps": (
            None if d.gps is None
            else [
                round(float(d.gps[0]), 8),
                round(float(d.gps[1]), 8),
            ]
        ),
    }


def annotate_final(
    frame,
    *,
    step_index,
    total_steps,
    preset,
    confirmed,
    scan_ms,
):
    out = frame.copy()

    put_text(
        out,
        "SMART FIRE DETECTION v2 | FULL SWEEP TEST",
        (10, 24),
    )
    put_text(
        out,
        (
            f"Step={step_index}/{total_steps} | "
            f"Preset={preset} | "
            f"Center={PRESET_BEARING_DEG[preset]:.1f} deg | "
            f"Scan={scan_ms:.0f} ms"
        ),
        (10, 48),
    )

    if confirmed:
        put_text(
            out,
            f"CONFIRMED DETECTIONS: {len(confirmed)}",
            (10, 78),
            color=(0, 255, 0),
            scale=0.75,
        )
    else:
        put_text(
            out,
            "NO CONFIRMED FIRE/SMOKE",
            (10, 78),
            color=(0, 165, 255),
            scale=0.75,
        )

    for idx, d in enumerate(confirmed, start=1):
        x1, y1, x2, y2 = d.bbox

        color = (
            (0, 0, 255)
            if d.canonical_class == "fire"
            else (0, 255, 255)
        )

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        distance_text = (
            "N/A"
            if d.distance_m is None
            else f"{d.distance_m:.2f}m"
        )

        compass = bearing_to_compass(d.bearing_deg)

        lines = [
            (
                f"{idx}. {d.canonical_class.upper()} "
                f"conf={d.confidence:.3f}"
            ),
            (
                f"bearing={d.bearing_deg:.2f}deg "
                f"{compass}"
            ),
            (
                f"distance={distance_text} "
                f"[{d.distance_quality}]"
            ),
        ]

        if d.gps is not None:
            lines.append(
                f"gps={d.gps[0]:.8f},{d.gps[1]:.8f}"
            )
        else:
            lines.append("gps=None")

        tx = max(5, min(x1, out.shape[1] - 430))
        ty = max(105, y1 - 70)

        for line_no, line in enumerate(lines):
            put_text(
                out,
                line,
                (tx, ty + line_no * 20),
                color=color,
                scale=0.50,
            )

        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        cv2.circle(out, (cx, cy), 4, color, -1)

    return out


def main():
    ap = argparse.ArgumentParser(
        description=(
            "One complete PTZ sweep test without Telegram: "
            "PTZ -> fresh/stable -> 3-frame AI -> IoU consensus -> save images"
        )
    )
    ap.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="จำนวนรอบ sweep (default: 1)",
    )
    args = ap.parse_args()

    if args.cycles < 1:
        raise SystemExit("❌ --cycles ต้อง >= 1")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = STATIC_DIR / "sweep_runs" / f"sweep_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 84)
    print("Smart Fire Detection v2 - Full Sweep Test")
    print(f"Sweep sequence : {SWEEP_SEQUENCE}")
    print(f"Cycles         : {args.cycles}")
    print(f"Frames/scan    : {FRAMES_PER_SCAN}")
    print(f"Confirm        : {MIN_CONFIRM_FRAMES}/{FRAMES_PER_SCAN}")
    print(f"Output         : {run_dir}")
    print("=" * 84)

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

    # Warm-up model ก่อนเริ่ม sweep จริง
    print("\n🔥 AI warm-up...")
    warm_packet = camera.latest(copy=True)
    t0 = time.perf_counter()
    detector.detect(warm_packet.frame, 1)
    warmup_ms = (time.perf_counter() - t0) * 1000.0
    print(f"✅ Warm-up completed: {warmup_ms:.1f} ms")

    results = []
    total_steps = len(SWEEP_SEQUENCE) * args.cycles
    global_step = 0
    total_confirmed = 0

    try:
        for cycle in range(1, args.cycles + 1):
            print(
                f"\n{'#' * 84}\n"
                f"CYCLE {cycle}/{args.cycles}\n"
                f"{'#' * 84}"
            )

            for preset in SWEEP_SEQUENCE:
                global_step += 1
                step_start = time.perf_counter()

                print(
                    f"\n{'-' * 84}\n"
                    f"[Step {global_step}/{total_steps}] "
                    f"Preset {preset} | "
                    f"Center {PRESET_BEARING_DEG[preset]:.1f}°"
                )

                ok, wait_sec = ptz.goto_preset(preset)

                if not ok:
                    print("❌ PTZ command failed")
                    results.append(
                        {
                            "step": global_step,
                            "cycle": cycle,
                            "preset": preset,
                            "status": "ptz_failed",
                            "detections": [],
                        }
                    )
                    continue

                # จุดแรกไม่ทราบตำแหน่งเริ่มต้นจริงของกล้อง
                if global_step == 1:
                    wait_sec = max(
                        wait_sec,
                        INITIAL_PRESET_WAIT_SEC,
                    )

                print(f"⏱️ PTZ wait {wait_sec:.2f}s")
                time.sleep(wait_sec)

                arrival_seq = camera.sequence

                fresh = wait_fresh_frames(
                    camera,
                    arrival_seq,
                    POST_MOVE_FRESH_FRAMES,
                )

                if fresh is None:
                    print("❌ No fresh frame")
                    results.append(
                        {
                            "step": global_step,
                            "cycle": cycle,
                            "preset": preset,
                            "status": "fresh_frame_failed",
                            "detections": [],
                        }
                    )
                    continue

                stable = wait_until_stable(
                    camera,
                    fresh.seq,
                    STABLE_DIFF_THRESHOLD,
                    STABLE_REQUIRED_PAIRS,
                    STABLE_TIMEOUT_SEC,
                )

                if stable is None:
                    print("❌ Image did not become stable")
                    results.append(
                        {
                            "step": global_step,
                            "cycle": cycle,
                            "preset": preset,
                            "status": "stable_frame_failed",
                            "detections": [],
                        }
                    )
                    continue

                print(
                    f"✅ Stable frame seq={stable.seq} "
                    f"age={time.time() - stable.timestamp:.3f}s"
                )

                detection_sets = []
                packet = stable
                last_packet = stable
                inference_times = []

                for frame_index in range(FRAMES_PER_SCAN):
                    if frame_index > 0:
                        time.sleep(FRAME_SAMPLE_GAP_SEC)

                        packet = camera.wait_for_newer(
                            last_packet.seq,
                            timeout=2.0,
                        )

                        if packet is None:
                            print(
                                f"⚠️ Frame "
                                f"{frame_index + 1}/{FRAMES_PER_SCAN} timeout"
                            )
                            break

                    last_packet = packet

                    infer_start = time.perf_counter()
                    detections = detector.detect(
                        packet.frame,
                        preset,
                    )
                    infer_ms = (
                        time.perf_counter() - infer_start
                    ) * 1000.0

                    inference_times.append(infer_ms)
                    detection_sets.append(detections)

                    print(
                        f"Frame {frame_index + 1}/{FRAMES_PER_SCAN} "
                        f"| seq={packet.seq} "
                        f"| infer={infer_ms:.1f}ms "
                        f"| detections={len(detections)}"
                    )

                    for d in detections:
                        dist = (
                            "N/A"
                            if d.distance_m is None
                            else f"{d.distance_m:.2f}m"
                        )
                        gps = (
                            "None"
                            if d.gps is None
                            else (
                                f"{d.gps[0]:.8f},"
                                f"{d.gps[1]:.8f}"
                            )
                        )

                        print(
                            "  - "
                            f"{d.canonical_class} "
                            f"conf={d.confidence:.3f} "
                            f"bearing={d.bearing_deg:.2f}° "
                            f"distance={dist} "
                            f"quality={d.distance_quality} "
                            f"gps={gps}"
                        )

                confirmed = consensus(
                    detection_sets,
                    MIN_CONFIRM_FRAMES,
                )

                total_confirmed += len(confirmed)

                if confirmed:
                    print(
                        f"🔥 CONFIRMED: "
                        f"{len(confirmed)} detection(s)"
                    )
                else:
                    print("✅ No confirmed Fire/Smoke")

                scan_ms = (
                    time.perf_counter() - step_start
                ) * 1000.0

                step_stem = (
                    f"step_{global_step:02d}_"
                    f"cycle_{cycle:02d}_"
                    f"preset_{preset}"
                )

                raw_path = run_dir / f"{step_stem}_raw.jpg"
                annotated_path = (
                    run_dir / f"{step_stem}_annotated.jpg"
                )

                cv2.imwrite(
                    str(raw_path),
                    last_packet.frame,
                )

                annotated = annotate_final(
                    last_packet.frame,
                    step_index=global_step,
                    total_steps=total_steps,
                    preset=preset,
                    confirmed=confirmed,
                    scan_ms=scan_ms,
                )

                cv2.imwrite(
                    str(annotated_path),
                    annotated,
                )

                print(
                    f"💾 Saved -> "
                    f"{annotated_path.name}"
                )

                results.append(
                    {
                        "step": global_step,
                        "cycle": cycle,
                        "preset": preset,
                        "center_bearing_deg": (
                            PRESET_BEARING_DEG[preset]
                        ),
                        "status": "ok",
                        "stable_seq": stable.seq,
                        "frames_processed": len(
                            detection_sets
                        ),
                        "inference_ms": [
                            round(x, 3)
                            for x in inference_times
                        ],
                        "scan_ms": round(scan_ms, 3),
                        "confirmed_count": len(
                            confirmed
                        ),
                        "detections": [
                            detection_to_dict(d)
                            for d in confirmed
                        ],
                        "raw_image": raw_path.name,
                        "annotated_image": (
                            annotated_path.name
                        ),
                    }
                )

    except KeyboardInterrupt:
        print("\n🛑 Sweep stopped by user")

    finally:
        camera.stop()

    summary = {
        "timestamp": timestamp,
        "sequence": SWEEP_SEQUENCE,
        "cycles_requested": args.cycles,
        "steps_completed": len(results),
        "total_confirmed_detections": total_confirmed,
        "results": results,
    }

    summary_path = run_dir / "sweep_summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 84)
    print("FULL SWEEP SUMMARY")
    print("=" * 84)
    print(f"Recorded steps       : {len(results)}")
    print(
        f"Confirmed detections : "
        f"{total_confirmed}"
    )
    print(f"Summary JSON         : {summary_path}")
    print(f"Images               : {run_dir}")
    print("=" * 84)
    print("✅ Full sweep test completed")


if __name__ == "__main__":
    main()
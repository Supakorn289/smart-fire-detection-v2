#!/usr/bin/env python3

import argparse
import statistics
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


# ============================================================
# Camera helpers
# ============================================================

def wait_fresh_frames(
    camera,
    after_seq,
    count,
):
    """
    Wait for a number of frames newer than after_seq.

    Returns:
        Latest fresh frame packet, or None on timeout.
    """

    seq = after_seq
    packet = None

    for _ in range(max(1, count)):
        packet = camera.wait_for_newer(
            seq,
            timeout=2.0,
        )

        if packet is None:
            return None

        seq = packet.seq

    return packet


# ============================================================
# AI Warm-up
# ============================================================

def warm_up_detector(
    camera,
    detector,
    preset,
    runs=3,
    start_packet=None,
):
    """
    Warm up AI inference AFTER PTZ movement and image stabilization.

    Warm-up results are intentionally discarded:
    - ไม่เข้า detection_sets
    - ไม่เข้า consensus
    - ไม่ถูกบันทึกเป็น test frame
    - ไม่ถูกนำไปรวมใน measured performance

    Args:
        camera:
            LatestFrameCamera instance.

        detector:
            FireDetector instance.

        preset:
            Current PTZ preset.

        runs:
            Number of warm-up inference runs.

        start_packet:
            Stable frame packet to use for the first warm-up run.

    Returns:
        tuple:
            (
                list of warm-up inference times in milliseconds,
                sequence number of the last warm-up frame
            )
    """

    if runs <= 0:
        print(
            "\nℹ️ Post-stable AI warm-up disabled"
        )

        last_seq = (
            start_packet.seq
            if start_packet is not None
            else camera.sequence
        )

        return [], last_seq

    packet = (
        start_packet
        if start_packet is not None
        else camera.latest(copy=True)
    )

    if packet is None:
        raise RuntimeError(
            "No frame available for AI warm-up"
        )

    print(
        f"\n🔥 Post-stable AI warm-up "
        f"({runs} runs)..."
    )

    timings_ms = []

    for i in range(runs):

        # รอบแรกใช้ stable frame
        #
        # รอบถัดไปพยายามใช้ frame ใหม่
        # เพื่อให้ warm-up ผ่าน latest-frame pipeline จริง
        if i > 0:
            newer = camera.wait_for_newer(
                packet.seq,
                timeout=2.0,
            )

            if newer is not None:
                packet = newer

            else:
                latest = camera.latest(
                    copy=True,
                )

                if latest is not None:
                    packet = latest

                print(
                    "  ⚠️ New frame timeout "
                    "during warm-up; "
                    "using latest available frame"
                )

        t0 = time.perf_counter()

        # ใช้ detection pipeline จริงเพื่อ warm:
        # - preprocessing
        # - inference backend
        # - model inference
        # - postprocessing
        #
        # แต่ทิ้ง detection result ทั้งหมด
        detector.detect(
            packet.frame,
            preset,
        )

        infer_ms = (
            time.perf_counter()
            - t0
        ) * 1000.0

        timings_ms.append(
            infer_ms
        )

        print(
            f"  Warm-up {i + 1}/{runs} "
            f"| seq={packet.seq} "
            f"| inference={infer_ms:.1f} ms"
        )

    print(
        "✅ Post-stable AI warm-up completed"
    )

    print(
        f"   first  = "
        f"{timings_ms[0]:.1f} ms"
    )

    print(
        f"   last   = "
        f"{timings_ms[-1]:.1f} ms"
    )

    print(
        f"   median = "
        f"{statistics.median(timings_ms):.1f} ms"
    )

    return (
        timings_ms,
        packet.seq,
    )


# ============================================================
# Detection display helpers
# ============================================================

def print_detection(
    prefix,
    d,
):
    gps_text = "None"

    if d.gps is not None:
        gps_text = (
            f"{d.gps[0]:.8f}, "
            f"{d.gps[1]:.8f}"
        )

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


def put_text_block(
    img,
    lines,
    x=10,
    y=24,
    scale=0.55,
    color=(0, 255, 0),
    thickness=2,
    line_gap=24,
):
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


def annotate_frame(
    frame,
    detections,
    preset,
    frame_index,
    frame_total,
    seq,
    infer_ms,
):
    out = frame.copy()

    header_lines = [
        "SMART FIRE DETECTION v2 | AI TEST",

        (
            f"Preset={preset} "
            f"| Center Bearing="
            f"{PRESET_BEARING_DEG[preset]:.1f} deg "
            f"| Frame {frame_index}/{frame_total} "
            f"| Seq={seq}"
        ),

        (
            f"Inference={infer_ms:.1f} ms "
            f"| Detections={len(detections)}"
        ),
    ]

    put_text_block(
        out,
        header_lines,
        x=10,
        y=24,
        color=(0, 255, 255),
        thickness=2,
        line_gap=24,
    )

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

    for idx, d in enumerate(
        detections,
        start=1,
    ):
        x1, y1, x2, y2 = d.bbox

        color = (
            (0, 0, 255)
            if d.canonical_class == "fire"
            else (0, 255, 255)
        )

        cv2.rectangle(
            out,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

        distance_text = "N/A"

        if d.distance_m is not None:
            distance_text = (
                f"{d.distance_m:.3f} m"
            )

        gps_text = "gps=None"

        if d.gps is not None:
            gps_text = (
                f"gps={d.gps[0]:.8f},"
                f"{d.gps[1]:.8f}"
            )

        label_lines = [
            (
                f"{idx}. "
                f"{d.canonical_class.upper()} "
                f"conf={d.confidence:.3f}"
            ),

            (
                f"bearing="
                f"{d.bearing_deg:.3f} deg"
            ),

            (
                f"distance={distance_text} "
                f"({d.distance_quality})"
            ),

            gps_text,
        ]

        tx = x1

        ty = max(
            18,
            y1 - 72,
        )

        if ty <= 20:
            ty = min(
                out.shape[0] - 90,
                y2 + 20,
            )

        put_text_block(
            out,
            label_lines,
            x=tx,
            y=ty,
            scale=0.50,
            color=color,
            thickness=2,
            line_gap=18,
        )

        cx = int(
            (x1 + x2) / 2
        )

        cy = int(
            (y1 + y2) / 2
        )

        cv2.circle(
            out,
            (cx, cy),
            4,
            color,
            -1,
        )

    return out


# ============================================================
# Save helpers
# ============================================================

def save_frame_pair(
    run_dir: Path,
    stem: str,
    raw_frame,
    annotated_frame,
):
    raw_path = (
        run_dir
        / f"{stem}_raw.jpg"
    )

    ann_path = (
        run_dir
        / f"{stem}_annotated.jpg"
    )

    ok_raw = cv2.imwrite(
        str(raw_path),
        raw_frame,
    )

    ok_annotated = cv2.imwrite(
        str(ann_path),
        annotated_frame,
    )

    if not ok_raw or not ok_annotated:
        raise RuntimeError(
            f"Save image failed "
            f"for stem={stem}"
        )

    return (
        raw_path,
        ann_path,
    )


# ============================================================
# Summary
# ============================================================

def write_summary(
    run_dir: Path,
    preset: int,
    detections_per_frame,
    confirmed,
    warmup_timings_ms,
):
    lines = []

    lines.append(
        "Smart Fire Detection v2 - "
        "Detection Test Summary"
    )

    lines.append(
        f"Preset: {preset}"
    )

    lines.append(
        f"Center Bearing: "
        f"{PRESET_BEARING_DEG[preset]:.1f} deg"
    )

    lines.append("")

    # --------------------------------------------------------
    # Warm-up
    # --------------------------------------------------------

    lines.append(
        "Post-Stable AI Warm-up"
    )

    lines.append(
        "Warm-up is excluded from "
        "measured test frames and consensus."
    )

    if warmup_timings_ms:

        for idx, value in enumerate(
            warmup_timings_ms,
            start=1,
        ):
            lines.append(
                f"  Warm-up {idx}: "
                f"{value:.1f} ms"
            )

        lines.append(
            f"  First: "
            f"{warmup_timings_ms[0]:.1f} ms"
        )

        lines.append(
            f"  Last: "
            f"{warmup_timings_ms[-1]:.1f} ms"
        )

        lines.append(
            f"  Median: "
            f"{statistics.median(warmup_timings_ms):.1f} ms"
        )

    else:
        lines.append(
            "  Disabled"
        )

    lines.append("")

    # --------------------------------------------------------
    # Measured performance
    # --------------------------------------------------------

    measured_times = [
        entry["infer_ms"]
        for entry
        in detections_per_frame
    ]

    lines.append(
        "Measured AI Inference"
    )

    lines.append(
        "Warm-up samples are excluded."
    )

    if measured_times:

        lines.append(
            f"  Samples: "
            f"{len(measured_times)}"
        )

        lines.append(
            f"  Mean: "
            f"{statistics.mean(measured_times):.1f} ms"
        )

        lines.append(
            f"  Median: "
            f"{statistics.median(measured_times):.1f} ms"
        )

        lines.append(
            f"  Min: "
            f"{min(measured_times):.1f} ms"
        )

        lines.append(
            f"  Max: "
            f"{max(measured_times):.1f} ms"
        )

    else:
        lines.append(
            "  No measured frames"
        )

    lines.append("")

    # --------------------------------------------------------
    # Per-frame detection results
    # --------------------------------------------------------

    for idx, entry in enumerate(
        detections_per_frame,
        start=1,
    ):
        seq = entry["seq"]
        infer_ms = entry["infer_ms"]
        detections = entry["detections"]

        lines.append(
            f"Frame {idx}: "
            f"seq={seq} "
            f"inference={infer_ms:.1f} ms "
            f"detections={len(detections)}"
        )

        if not detections:

            lines.append(
                "  - no Fire/Smoke "
                "above configured threshold"
            )

        else:

            for d in detections:

                gps_text = "None"

                if d.gps is not None:
                    gps_text = (
                        f"{d.gps[0]:.8f}, "
                        f"{d.gps[1]:.8f}"
                    )

                distance_text = (
                    "None"
                    if d.distance_m is None
                    else f"{d.distance_m:.3f} m"
                )

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

    # --------------------------------------------------------
    # Consensus
    # --------------------------------------------------------

    lines.append(
        "Consensus result"
    )

    if not confirmed:

        lines.append(
            "  - no confirmed detection"
        )

    else:

        lines.append(
            f"  - confirmed detections: "
            f"{len(confirmed)}"
        )

        for d in confirmed:

            gps_text = "None"

            if d.gps is not None:
                gps_text = (
                    f"{d.gps[0]:.8f}, "
                    f"{d.gps[1]:.8f}"
                )

            distance_text = (
                "None"
                if d.distance_m is None
                else f"{d.distance_m:.3f} m"
            )

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

    summary_path = (
        run_dir
        / "summary.txt"
    )

    summary_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return summary_path


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Live AI pipeline test: "
            "RTSP -> PTZ -> Stable Frame -> "
            "AI Warm-up -> Fresh Frame -> "
            "Measured AI -> Consensus -> "
            "Bearing -> Distance -> GPS"
        )
    )

    parser.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=1,
        help=(
            "Preset ที่ต้องการทดสอบ "
            "(default: 1)"
        ),
    )

    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=3,
        help=(
            "จำนวน post-stable AI warm-up inference "
            "ก่อนเริ่มวัดจริง "
            "(default: 3, 0=disable)"
        ),
    )

    args = parser.parse_args()

    if args.warmup_runs < 0:
        raise SystemExit(
            "❌ --warmup-runs ต้อง >= 0"
        )

    preset = args.preset

    # ========================================================
    # Header
    # ========================================================

    print(
        "=" * 76
    )

    print(
        "Smart Fire Detection v2 - "
        "Live Detection Pipeline Test"
    )

    print(
        f"Preset: {preset}"
    )

    print(
        f"Center bearing: "
        f"{PRESET_BEARING_DEG[preset]:.1f}°"
    )

    print(
        f"Frames per scan: "
        f"{FRAMES_PER_SCAN}"
    )

    print(
        f"Minimum confirm frames: "
        f"{MIN_CONFIRM_FRAMES}"
    )

    print(
        f"Post-stable AI warm-up runs: "
        f"{args.warmup_runs}"
    )

    print(
        "=" * 76
    )

    # ========================================================
    # Output directory
    # ========================================================

    run_stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    run_dir = (
        STATIC_DIR
        / "detection_runs"
        / f"preset_{preset}_{run_stamp}"
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"\n📁 Output dir: "
        f"{run_dir}"
    )

    # ========================================================
    # Camera
    # ========================================================

    print(
        "\n📡 กำลังเปิด RTSP..."
    )

    camera = (
        LatestFrameCamera()
        .start()
    )

    try:

        # ----------------------------------------------------
        # Wait for first RTSP frame
        # ----------------------------------------------------

        deadline = (
            time.monotonic()
            + 10.0
        )

        while (
            camera.latest(
                copy=False
            )
            is None
        ):

            if (
                time.monotonic()
                >= deadline
            ):
                raise RuntimeError(
                    "RTSP timeout"
                )

            time.sleep(
                0.1
            )

        print(
            "✅ RTSP พร้อม"
        )

        # ====================================================
        # Model
        # ====================================================

        print(
            "\n🧠 กำลังโหลดโมเดล..."
        )

        detector = FireDetector()

        print(
            "✅ Model พร้อม"
        )

        # ====================================================
        # PTZ
        # ====================================================

        ptz = PTZController()

        print(
            f"\n🔄 Move -> "
            f"Preset {preset}"
        )

        ok, wait_sec = (
            ptz.goto_preset(
                preset
            )
        )

        if not ok:
            raise RuntimeError(
                "PTZ command failed"
            )

        print(
            f"⏱️ รอ PTZ "
            f"{wait_sec:.2f}s"
        )

        time.sleep(
            wait_sec
        )

        # ====================================================
        # Fresh frame after PTZ move
        # ====================================================

        arrival_seq = (
            camera.sequence
        )

        fresh = wait_fresh_frames(
            camera,
            arrival_seq,
            POST_MOVE_FRESH_FRAMES,
        )

        if fresh is None:
            raise RuntimeError(
                "No fresh post-move frame"
            )

        # ====================================================
        # Stable frame
        # ====================================================

        stable = wait_until_stable(
            camera,
            fresh.seq,
            STABLE_DIFF_THRESHOLD,
            STABLE_REQUIRED_PAIRS,
            STABLE_TIMEOUT_SEC,
        )

        if stable is None:
            raise RuntimeError(
                "Image did not become stable"
            )

        print(
            f"✅ Fresh + stable frame "
            f"| seq={stable.seq} "
            f"| age="
            f"{time.time() - stable.timestamp:.3f}s"
        )

        # ====================================================
        # POST-STABLE AI WARM-UP
        # ====================================================

        warmup_timings_ms, last_warmup_seq = (
            warm_up_detector(
                camera,
                detector,
                preset,
                runs=args.warmup_runs,
                start_packet=stable,
            )
        )

        # ====================================================
        # Fresh measurement frame AFTER warm-up
        # ====================================================
        #
        # ห้ามใช้:
        # - stable frame เดิม
        # - warm-up frame
        #
        # เป็น Frame 1 ของการวัดจริง
        #
        # ใช้ sequence boundary เพื่อรับประกันว่า
        # measurement frame ใหม่กว่า warm-up ทั้งหมด
        # ====================================================

        measurement_boundary_seq = max(
            camera.sequence,
            last_warmup_seq,
        )

        measurement_packet = (
            camera.wait_for_newer(
                measurement_boundary_seq,
                timeout=2.0,
            )
        )

        if measurement_packet is None:
            raise RuntimeError(
                "No fresh frame after AI warm-up"
            )

        print(
            "✅ Fresh measurement frame "
            "after warm-up "
            f"| seq={measurement_packet.seq} "
            f"| age="
            f"{time.time() - measurement_packet.timestamp:.3f}s"
        )

        # ====================================================
        # MEASURED TEST START
        # ====================================================

        detection_sets = []
        packets = []
        detections_per_frame = []

        # Frame 1 ต้องเริ่มจาก frame
        # ที่ใหม่กว่า warm-up ทั้งหมด
        packet = measurement_packet

        print(
            "\n🔎 เริ่ม AI inference "
            "(post-stable warm-up excluded)"
        )

        for i in range(
            FRAMES_PER_SCAN
        ):

            # ------------------------------------------------
            # Frame 2+ ต้องใหม่กว่า frame ก่อนหน้า
            # ------------------------------------------------

            if i > 0:

                time.sleep(
                    FRAME_SAMPLE_GAP_SEC
                )

                packet = (
                    camera.wait_for_newer(
                        packet.seq,
                        timeout=2.0,
                    )
                )

                if packet is None:

                    print(
                        f"⚠️ Frame "
                        f"#{i + 1}: timeout"
                    )

                    break

            packets.append(
                packet
            )

            # =================================================
            # Measured inference
            # =================================================

            t0 = (
                time.perf_counter()
            )

            detections = (
                detector.detect(
                    packet.frame,
                    preset,
                )
            )

            infer_ms = (
                time.perf_counter()
                - t0
            ) * 1000.0

            detection_sets.append(
                detections
            )

            detections_per_frame.append(
                {
                    "seq": packet.seq,
                    "infer_ms": infer_ms,
                    "detections": detections,
                }
            )

            print(
                f"\nFrame "
                f"{i + 1}/"
                f"{FRAMES_PER_SCAN} "
                f"| seq={packet.seq} "
                f"| inference="
                f"{infer_ms:.1f} ms "
                f"| detections="
                f"{len(detections)}"
            )

            if not detections:

                print(
                    "  - no Fire/Smoke "
                    "above configured threshold"
                )

            else:

                for d in detections:

                    print_detection(
                        "  - ",
                        d,
                    )

            # =================================================
            # Annotate + save
            # =================================================

            annotated = (
                annotate_frame(
                    packet.frame,
                    detections,
                    preset,
                    i + 1,
                    FRAMES_PER_SCAN,
                    packet.seq,
                    infer_ms,
                )
            )

            raw_path, ann_path = (
                save_frame_pair(
                    run_dir,
                    f"frame_{i + 1:02d}",
                    packet.frame,
                    annotated,
                )
            )

            print(
                f"  💾 saved raw       "
                f"-> {raw_path}"
            )

            print(
                f"  💾 saved annotated "
                f"-> {ann_path}"
            )

        # ====================================================
        # Performance summary
        # ====================================================

        measured_times = [
            entry["infer_ms"]
            for entry
            in detections_per_frame
        ]

        if measured_times:

            print(
                "\n"
                + "-" * 76
            )

            print(
                "Measured inference "
                "(post-stable warm-up excluded)"
            )

            print(
                "-" * 76
            )

            print(
                f"Samples: "
                f"{len(measured_times)}"
            )

            print(
                f"Mean   : "
                f"{statistics.mean(measured_times):.1f} ms"
            )

            print(
                f"Median : "
                f"{statistics.median(measured_times):.1f} ms"
            )

            print(
                f"Min    : "
                f"{min(measured_times):.1f} ms"
            )

            print(
                f"Max    : "
                f"{max(measured_times):.1f} ms"
            )

        # ====================================================
        # Consensus
        # ====================================================

        confirmed = consensus(
            detection_sets,
            MIN_CONFIRM_FRAMES,
        )

        print(
            "\n"
            + "=" * 76
        )

        print(
            "Consensus result"
        )

        print(
            "=" * 76
        )

        if not confirmed:

            print(
                "ℹ️ ไม่มี detection "
                "ที่ยืนยันครบตามจำนวนเฟรม "
                f"({MIN_CONFIRM_FRAMES}/"
                f"{FRAMES_PER_SCAN})"
            )

        else:

            print(
                f"✅ Confirmed detections: "
                f"{len(confirmed)}"
            )

            for d in confirmed:

                print_detection(
                    "  - ",
                    d,
                )

        # ====================================================
        # Final output frame
        # ====================================================

        if packets:

            result_frame = (
                packets[-1]
                .frame
                .copy()
            )

            last_seq = (
                packets[-1].seq
            )

        else:

            # ไม่ย้อนกลับไปใช้ stable frame
            # เพราะเป็น frame ก่อน warm-up
            result_frame = (
                measurement_packet
                .frame
                .copy()
            )

            last_seq = (
                measurement_packet.seq
            )

        last_infer_ms = (
            detections_per_frame[-1]["infer_ms"]
            if detections_per_frame
            else 0.0
        )

        result_annotated = (
            annotate_frame(
                result_frame,
                confirmed,
                preset,
                len(
                    detections_per_frame
                ),
                FRAMES_PER_SCAN,
                last_seq,
                last_infer_ms,
            )
        )

        state_text = (
            "CONFIRMED DETECTION"
            if confirmed
            else "NO CONFIRMED DETECTION"
        )

        state_color = (
            (0, 255, 0)
            if confirmed
            else (0, 165, 255)
        )

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

        final_raw = (
            run_dir
            / "final_raw.jpg"
        )

        final_ann = (
            run_dir
            / "final_annotated.jpg"
        )

        if not cv2.imwrite(
            str(final_raw),
            result_frame,
        ):
            raise RuntimeError(
                f"Save image failed: "
                f"{final_raw}"
            )

        if not cv2.imwrite(
            str(final_ann),
            result_annotated,
        ):
            raise RuntimeError(
                f"Save image failed: "
                f"{final_ann}"
            )

        print(
            f"\n📷 Saved final raw       "
            f"-> {final_raw}"
        )

        print(
            f"📷 Saved final annotated "
            f"-> {final_ann}"
        )

        # ====================================================
        # Summary
        # ====================================================

        summary_path = (
            write_summary(
                run_dir,
                preset,
                detections_per_frame,
                confirmed,
                warmup_timings_ms,
            )
        )

        print(
            f"📝 Saved summary         "
            f"-> {summary_path}"
        )

        # ====================================================
        # Pipeline checks
        # ====================================================

        print(
            "\nPipeline checks:"
        )

        print(
            "  RTSP / fresh frame        ✅"
        )

        print(
            "  PTZ / stable frame        ✅"
        )

        if warmup_timings_ms:

            print(
                "  Post-stable AI warm-up    ✅"
            )

        else:

            print(
                "  Post-stable AI warm-up    "
                "ℹ️ disabled"
            )

        print(
            "  Fresh frame after warm-up ✅"
        )

        print(
            "  YOLO inference            ✅"
        )

        print(
            "  Fire/Smoke class mapping  ✅"
        )

        if confirmed:

            print(
                "  Consensus                 "
                "✅ detection confirmed"
            )

            print(
                "  Pixel X -> bearing        "
                "✅ calculated"
            )

            if any(
                d.distance_m is not None
                for d in confirmed
            ):

                print(
                    "  Pixel Y -> distance       "
                    "✅ calculated"
                )

            else:

                print(
                    "  Pixel Y -> distance       "
                    "⚠️ unavailable / "
                    "calibration pending"
                )

            if any(
                d.gps is not None
                for d in confirmed
            ):

                print(
                    "  Bearing+distance -> GPS   "
                    "✅ calculated"
                )

            else:

                print(
                    "  Bearing+distance -> GPS   "
                    "⚠️ unavailable without "
                    "valid calibration"
                )

        else:

            print(
                "  Consensus                 "
                "ℹ️ no confirmed Fire/Smoke"
            )

            print(
                "  Bearing/Distance/GPS      "
                "ℹ️ skipped because "
                "no confirmed target"
            )

        print(
            "\n✅ Live detection "
            "pipeline test completed"
        )

    finally:

        # กล้องต้องถูกปิดเสมอ แม้เกิด exception
        # ระหว่าง:
        #
        # - model loading
        # - PTZ
        # - frame stability
        # - warm-up
        # - inference
        # - image saving
        #
        camera.stop()


if __name__ == "__main__":
    main()
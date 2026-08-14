#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import time
from pathlib import Path

import cv2

from calibration import fit_distance_model, save_distance_model
from camera import LatestFrameCamera, wait_until_stable
from config import (
    CALIBRATION_DIR,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    INITIAL_PRESET_WAIT_SEC,
    POST_MOVE_FRESH_FRAMES,
    PRESET_BEARING_DEG,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
)
from ptz import PTZController


def open_in_paint(path: Path):
    """Open captured image in Microsoft Paint on Windows when available."""
    if platform.system().lower() != "windows":
        return False

    try:
        subprocess.Popen(["mspaint", str(path)])
        return True
    except Exception:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


def wait_fresh_frames(
    camera: LatestFrameCamera,
    after_seq: int,
    count: int,
    timeout_per_frame: float = 2.0,
):
    """Require a number of frames newer than after_seq."""
    seq = after_seq
    packet = None

    for _ in range(max(1, count)):
        packet = camera.wait_for_newer(seq, timeout=timeout_per_frame)
        if packet is None:
            return None
        seq = packet.seq

    return packet


def capture_fresh_frame(
    camera: LatestFrameCamera,
    timeout: float = 5.0,
):
    """Wait for a frame newer than the currently visible frame."""
    seq = camera.sequence
    packet = camera.wait_for_newer(seq, timeout=timeout)

    if packet is None:
        packet = camera.latest(copy=True)

    return packet


def move_to_preset_and_wait_stable(
    camera: LatestFrameCamera,
    preset: int,
):
    """
    Move PTZ to the requested preset and verify fresh/stable frames
    before calibration starts.
    """
    ptz = PTZController()

    print("\n" + "=" * 68)
    print(
        f"🔄 กำลังหมุนกล้องไป Preset {preset} "
        f"(center bearing={PRESET_BEARING_DEG[preset]:.1f}°)"
    )

    seq_before_move = camera.sequence

    ok, wait_sec = ptz.goto_preset(preset)
    if not ok:
        raise RuntimeError(f"PTZ command failed: preset={preset}")

    # Calibration may start from an unknown physical position.
    wait_sec = max(wait_sec, INITIAL_PRESET_WAIT_SEC)

    print(f"⏱️ รอ PTZ {wait_sec:.2f}s")
    time.sleep(wait_sec)

    # Boundary after movement delay: any frames used below must be newer.
    arrival_seq = max(seq_before_move, camera.sequence)

    fresh = wait_fresh_frames(
        camera,
        arrival_seq,
        POST_MOVE_FRESH_FRAMES,
    )

    if fresh is None:
        raise RuntimeError(
            f"ไม่ได้รับ fresh frame หลัง PTZ ไป Preset {preset}"
        )

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:
        raise RuntimeError(
            f"ภาพไม่ Stable หลัง PTZ ไป Preset {preset}"
        )

    print(
        f"✅ Preset {preset} พร้อม Calibration "
        f"| stable seq={stable.seq} "
        f"| age={time.time() - stable.timestamp:.3f}s"
    )
    print("=" * 68)

    return stable


def draw_y_guide(frame):
    """Create a helper copy with horizontal Y guides every 50 px."""
    guide = frame.copy()

    for y in range(0, FRAME_HEIGHT, 50):
        cv2.line(
            guide,
            (0, y),
            (FRAME_WIDTH - 1, y),
            (0, 255, 255),
            1,
        )

        cv2.putText(
            guide,
            f"Y={y}",
            (8, min(FRAME_HEIGHT - 8, y + 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return guide


def read_y_pixel(index: int):
    while True:
        raw = input(
            f"[{index}] y pixel ของจุดสัมผัสพื้น "
            f"(0-{FRAME_HEIGHT - 1}) "
            "หรือพิมพ์ r เพื่อถ่ายใหม่: "
        ).strip().lower()

        if raw == "r":
            return None

        try:
            y = float(raw)
        except ValueError:
            print("❌ กรุณาใส่ตัวเลข Y หรือ r")
            continue

        if not (0 <= y < FRAME_HEIGHT):
            print(
                f"❌ Y ต้องอยู่ระหว่าง 0 ถึง {FRAME_HEIGHT - 1}"
            )
            continue

        return y


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Capture calibration images and fit perspective distance: "
            "y = H + K/Z"
        )
    )

    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=None,
        help=(
            "Calibration แยก Preset 1-9. "
            "ถ้าระบุ โปรแกรมจะสั่ง PTZ ไป Preset นั้นและรอ Fresh+Stable Frame "
            "ก่อนเริ่ม. ถ้าไม่ระบุจะสร้าง Global Calibration จากมุมกล้องปัจจุบัน"
        ),
    )

    args = ap.parse_args()

    print("=" * 68)
    print("Smart Fire Detection v2 - Distance Calibration")
    print(f"Image size: {FRAME_WIDTH}x{FRAME_HEIGHT}")

    if args.preset is None:
        print("Mode: GLOBAL")
        print(
            "⚠️ Global mode จะไม่สั่ง PTZ — ใช้มุมกล้องปัจจุบันในการ Calibration"
        )
    else:
        print(
            f"Mode: PRESET {args.preset} "
            f"(center bearing={PRESET_BEARING_DEG[args.preset]:.1f}°)"
        )
        print(
            "ระบบจะสั่ง PTZ ไป Preset ที่เลือกและยืนยัน Fresh+Stable Frame "
            "อัตโนมัติก่อนเริ่ม"
        )

    print("พิกัดภาพ: มุมซ้ายบน = (0,0), ค่า Y เพิ่มลงด้านล่าง")
    print(
        "ใช้ Y ของ 'จุดล่างสุดที่วัตถุสัมผัสพื้น' "
        "ไม่ใช่กลางกรอบวัตถุ"
    )
    print("=" * 68)

    try:
        n = int(
            input(
                "จำนวนจุด calibration "
                "(ขั้นต่ำ 3, แนะนำ 5-8): "
            ).strip()
        )
    except ValueError:
        raise SystemExit(
            "❌ จำนวนจุดต้องเป็นตัวเลขจำนวนเต็ม"
        )

    if n < 3:
        raise SystemExit(
            "❌ ต้องมีอย่างน้อย 3 จุด"
        )

    capture_dir = CALIBRATION_DIR / "captures"
    capture_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n📡 กำลังเชื่อมต่อ RTSP...")
    camera = LatestFrameCamera().start()

    deadline = time.monotonic() + 10.0

    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit(
                "❌ RTSP timeout: ไม่ได้รับภาพจากกล้อง"
            )
        time.sleep(0.1)

    print("✅ RTSP พร้อมใช้งาน")

    samples = []

    try:
        if args.preset is not None:
            try:
                move_to_preset_and_wait_stable(
                    camera,
                    args.preset,
                )
            except RuntimeError as e:
                raise SystemExit(
                    f"❌ {e}"
                )

        else:
            print(
                "\nℹ️ Global Calibration: "
                "ตรวจสอบด้วยสายตาว่ากล้องอยู่ในมุมที่ต้องการแล้ว"
            )
            input(
                "เมื่อกล้องอยู่นิ่งและพร้อมแล้ว กด Enter เพื่อเริ่ม Calibration..."
            )

            boundary_seq = camera.sequence

            fresh = wait_fresh_frames(
                camera,
                boundary_seq,
                POST_MOVE_FRESH_FRAMES,
            )

            if fresh is None:
                raise SystemExit(
                    "❌ ไม่ได้รับ fresh frame ก่อนเริ่ม Global Calibration"
                )

            stable = wait_until_stable(
                camera,
                fresh.seq,
                STABLE_DIFF_THRESHOLD,
                STABLE_REQUIRED_PAIRS,
                STABLE_TIMEOUT_SEC,
            )

            if stable is None:
                raise SystemExit(
                    "❌ ภาพไม่ Stable ก่อนเริ่ม Global Calibration"
                )

            print(
                f"✅ Global calibration frame stable "
                f"| seq={stable.seq}"
            )

        for i in range(1, n + 1):
            print("\n" + "-" * 68)

            while True:
                try:
                    z = float(
                        input(
                            f"[{i}/{n}] "
                            "ระยะจริงจากกล้องถึงวัตถุ (m): "
                        ).strip()
                    )

                    if z <= 0:
                        raise ValueError

                    break

                except ValueError:
                    print(
                        "❌ ระยะต้องเป็นตัวเลขมากกว่า 0"
                    )

            while True:
                input(
                    f"วางวัตถุที่ระยะ {z:.2f} m ให้เรียบร้อย "
                    "แล้วกด Enter เพื่อถ่ายภาพ..."
                )

                packet = capture_fresh_frame(camera)

                if packet is None:
                    print(
                        "❌ ถ่ายภาพไม่สำเร็จ ลองใหม่"
                    )
                    continue

                preset_tag = (
                    f"preset_{args.preset}"
                    if args.preset
                    else "global"
                )

                base_name = (
                    f"{preset_tag}_point_"
                    f"{i:02d}_{z:.2f}m"
                )

                raw_path = (
                    capture_dir
                    / f"{base_name}.jpg"
                )

                guide_path = (
                    capture_dir
                    / f"{base_name}_guide.jpg"
                )

                ok1 = cv2.imwrite(
                    str(raw_path),
                    packet.frame,
                )

                ok2 = cv2.imwrite(
                    str(guide_path),
                    draw_y_guide(packet.frame),
                )

                if not ok1:
                    print(
                        "❌ บันทึกภาพไม่สำเร็จ ลองใหม่"
                    )
                    continue

                print(
                    f"✅ ถ่ายภาพแล้ว: {raw_path}"
                )

                if ok2:
                    print(
                        f"   ภาพช่วยดูแนว Y: {guide_path}"
                    )

                opened = open_in_paint(
                    raw_path
                )

                if opened:
                    print(
                        "🎨 เปิดภาพใน Paint แล้ว"
                    )
                else:
                    print(
                        "เปิดภาพนี้ด้วย Paint/GIMP "
                        "แล้วเลื่อนเมาส์ไปที่จุดสัมผัสพื้น"
                    )

                print(
                    "วิธีอ่าน: X ไม่จำเป็นสำหรับสมการนี้ "
                    "ให้จดเฉพาะค่า Y"
                )

                y = read_y_pixel(i)

                if y is None:
                    print(
                        "🔄 ถ่ายภาพจุดนี้ใหม่"
                    )
                    continue

                samples.append(
                    (z, y)
                )

                print(
                    f"✅ เก็บ Sample #{i}: "
                    f"distance={z:.2f}m, "
                    f"y={y:.1f}px"
                )
                break

    finally:
        camera.stop()

    print(
        "\n📐 กำลังคำนวณ Least-Squares Calibration..."
    )

    model = fit_distance_model(
        samples,
        args.preset,
    )

    path = save_distance_model(
        model
    )

    print(f"✅ Saved: {path}")
    print(f"H={model.H:.6f}")
    print(f"K={model.K:.6f}")
    print(
        f"pixel_RMSE={model.pixel_rmse:.3f}px"
    )
    print(
        f"calibrated_range="
        f"{model.min_distance_m:.2f}-"
        f"{model.max_distance_m:.2f}m"
    )

    print("\nผลตรวจย้อนกลับ:")

    for z, y in samples:
        est = model.estimate(y)

        if est is None:
            print(
                f"  real={z:.2f}m | "
                f"y={y:.1f}px | "
                "estimated=N/A"
            )
            continue

        print(
            f"  real={z:.2f}m | "
            f"y={y:.1f}px | "
            f"estimated={est:.2f}m | "
            f"error={abs(est-z):.2f}m"
        )

    print("\n✅ Calibration เสร็จแล้ว")
    print(
        "แนะนำให้ใช้ verify_distance.py "
        "กับระยะใหม่ที่ไม่ได้ใช้ calibrate"
    )


if __name__ == "__main__":
    main()
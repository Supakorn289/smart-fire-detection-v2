#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import time
from pathlib import Path

import cv2

from calibration import fit_distance_model, save_distance_model
from camera import LatestFrameCamera
from config import FRAME_HEIGHT, FRAME_WIDTH, CALIBRATION_DIR


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


def capture_fresh_frame(camera: LatestFrameCamera, timeout: float = 5.0):
    """Wait for a frame newer than the currently visible frame."""
    seq = camera.sequence
    packet = camera.wait_for_newer(seq, timeout=timeout)
    if packet is None:
        packet = camera.latest(copy=True)
    return packet


def draw_y_guide(frame):
    """Create a helper copy with horizontal Y guides every 50 px."""
    guide = frame.copy()
    for y in range(0, FRAME_HEIGHT, 50):
        cv2.line(guide, (0, y), (FRAME_WIDTH - 1, y), (0, 255, 255), 1)
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
            f"[{index}] y pixel ของจุดสัมผัสพื้น (0-{FRAME_HEIGHT - 1}) "
            f"หรือพิมพ์ r เพื่อถ่ายใหม่: "
        ).strip().lower()
        if raw == "r":
            return None
        try:
            y = float(raw)
        except ValueError:
            print("❌ กรุณาใส่ตัวเลข Y หรือ r")
            continue
        if not (0 <= y < FRAME_HEIGHT):
            print(f"❌ Y ต้องอยู่ระหว่าง 0 ถึง {FRAME_HEIGHT - 1}")
            continue
        return y


def main():
    ap = argparse.ArgumentParser(
        description="Capture calibration images and fit perspective distance: y = H + K/Z"
    )
    ap.add_argument("--preset", type=int, choices=range(1, 10), default=None)
    args = ap.parse_args()

    print("=" * 68)
    print("Smart Fire Detection v2 - Distance Calibration")
    print(f"Image size: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print("พิกัดภาพ: มุมซ้ายบน = (0,0), ค่า Y เพิ่มลงด้านล่าง")
    print("ใช้ Y ของ 'จุดล่างสุดที่วัตถุสัมผัสพื้น' ไม่ใช่กลางกรอบวัตถุ")
    print("=" * 68)

    try:
        n = int(input("จำนวนจุด calibration (ขั้นต่ำ 3, แนะนำ 5-8): ").strip())
    except ValueError:
        raise SystemExit("❌ จำนวนจุดต้องเป็นตัวเลขจำนวนเต็ม")

    if n < 3:
        raise SystemExit("❌ ต้องมีอย่างน้อย 3 จุด")

    capture_dir = CALIBRATION_DIR / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)

    print("\n📡 กำลังเชื่อมต่อ RTSP...")
    camera = LatestFrameCamera().start()
    deadline = time.monotonic() + 10.0
    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit("❌ RTSP timeout: ไม่ได้รับภาพจากกล้อง")
        time.sleep(0.1)
    print("✅ RTSP พร้อมใช้งาน")

    samples = []
    try:
        for i in range(1, n + 1):
            print("\n" + "-" * 68)
            while True:
                try:
                    z = float(input(f"[{i}/{n}] ระยะจริงจากกล้องถึงวัตถุ (m): ").strip())
                    if z <= 0:
                        raise ValueError
                    break
                except ValueError:
                    print("❌ ระยะต้องเป็นตัวเลขมากกว่า 0")

            while True:
                input(
                    f"วางวัตถุที่ระยะ {z:.2f} m ให้เรียบร้อย แล้วกด Enter เพื่อถ่ายภาพ..."
                )

                packet = capture_fresh_frame(camera)
                if packet is None:
                    print("❌ ถ่ายภาพไม่สำเร็จ ลองใหม่")
                    continue

                preset_tag = f"preset_{args.preset}" if args.preset else "global"
                base_name = f"{preset_tag}_point_{i:02d}_{z:.2f}m"
                raw_path = capture_dir / f"{base_name}.jpg"
                guide_path = capture_dir / f"{base_name}_guide.jpg"

                ok1 = cv2.imwrite(str(raw_path), packet.frame)
                ok2 = cv2.imwrite(str(guide_path), draw_y_guide(packet.frame))
                if not ok1:
                    print("❌ บันทึกภาพไม่สำเร็จ ลองใหม่")
                    continue

                print(f"✅ ถ่ายภาพแล้ว: {raw_path}")
                if ok2:
                    print(f"   ภาพช่วยดูแนว Y: {guide_path}")

                opened = open_in_paint(raw_path)
                if opened:
                    print("🎨 เปิดภาพใน Paint แล้ว")
                else:
                    print("เปิดภาพนี้ด้วย Paint/GIMP แล้วเลื่อนเมาส์ไปที่จุดสัมผัสพื้น")

                print("วิธีอ่าน: X ไม่จำเป็นสำหรับสมการนี้ ให้จดเฉพาะค่า Y")
                y = read_y_pixel(i)
                if y is None:
                    print("🔄 ถ่ายภาพจุดนี้ใหม่")
                    continue

                samples.append((z, y))
                print(f"✅ เก็บ Sample #{i}: distance={z:.2f}m, y={y:.1f}px")
                break

    finally:
        camera.stop()

    print("\n📐 กำลังคำนวณ Least-Squares Calibration...")
    model = fit_distance_model(samples, args.preset)
    path = save_distance_model(model)

    print(f"✅ Saved: {path}")
    print(f"H={model.H:.6f}")
    print(f"K={model.K:.6f}")
    print(f"pixel_RMSE={model.pixel_rmse:.3f}px")
    print("\nผลตรวจย้อนกลับ:")
    for z, y in samples:
        est = model.estimate(y)
        print(
            f"  real={z:.2f}m | y={y:.1f}px | "
            f"estimated={est:.2f}m | error={abs(est-z):.2f}m"
        )

    print("\n✅ Calibration เสร็จแล้ว")
    print("แนะนำให้ใช้ verify_distance.py กับระยะใหม่ที่ไม่ได้ใช้ calibrate")


if __name__ == "__main__":
    main()

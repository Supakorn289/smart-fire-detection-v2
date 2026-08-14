#!/usr/bin/env python3
import argparse
import math
import os
import platform
import subprocess
import time

import cv2

from calibration import load_distance_model
from camera import LatestFrameCamera
from config import FRAME_HEIGHT, FRAME_WIDTH, CALIBRATION_DIR


def open_in_paint(path):
    """เปิดภาพด้วย Microsoft Paint บน Windows ถ้าทำได้"""
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


def capture_fresh_frame(camera, timeout=5.0):
    """รอเฟรมใหม่กว่าเฟรมปัจจุบัน เพื่อลดโอกาสใช้ภาพเก่า"""
    seq = camera.sequence
    packet = camera.wait_for_newer(seq, timeout=timeout)
    if packet is None:
        packet = camera.latest(copy=True)
    return packet


def draw_y_guide(frame):
    """สร้างภาพช่วยอ่านค่า Y ทุก 50 pixel"""
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

    # เส้นล่างสุด
    y = FRAME_HEIGHT - 1
    cv2.line(
        guide,
        (0, y),
        (FRAME_WIDTH - 1, y),
        (0, 0, 255),
        1,
    )

    return guide


def read_y_pixel(index):
    while True:
        raw = input(
            f"[{index}] y pixel ของจุดสัมผัสพื้น (0-{FRAME_HEIGHT - 1}) "
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
            print(f"❌ Y ต้องอยู่ระหว่าง 0 ถึง {FRAME_HEIGHT - 1}")
            continue

        return y


def main():
    ap = argparse.ArgumentParser(
        description="Verify perspective distance calibration using captured RTSP images"
    )
    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=None,
        help="ตรวจ calibration เฉพาะ preset 1-9; ถ้าไม่ใส่จะใช้ global calibration",
    )
    args = ap.parse_args()

    model = load_distance_model(args.preset)
    if model is None:
        if args.preset:
            raise SystemExit(
                f"❌ ไม่พบ calibration ของ Preset {args.preset}\n"
                f"ให้รัน: python calibrate_distance.py --preset {args.preset}"
            )
        raise SystemExit(
            "❌ ไม่พบ global distance calibration\n"
            "ให้รัน: python calibrate_distance.py"
        )

    print("=" * 72)
    print("Smart Fire Detection v2 - Distance Verification")
    print(f"Image size: {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print(
        f"Calibration: {'Preset ' + str(args.preset) if args.preset else 'Global'}"
    )
    print(f"H={model.H:.6f}")
    print(f"K={model.K:.6f}")
    if hasattr(model, "pixel_rmse"):
        print(f"Calibration pixel_RMSE={model.pixel_rmse:.3f}px")
    print("")
    print("ใช้ระยะที่ 'ไม่ได้ใช้' ตอน Calibration เช่น ถ้า calibrate 6,8,10m")
    print("แนะนำ verify ที่ 7m และ 9m")
    print("อ่าน Y จาก 'จุดล่างสุดที่วัตถุสัมผัสพื้น'")
    print("=" * 72)

    try:
        n = int(
            input("จำนวนจุด verification (ขั้นต่ำ 1, แนะนำ 2-5): ").strip()
        )
    except ValueError:
        raise SystemExit("❌ จำนวนจุดต้องเป็นตัวเลขจำนวนเต็ม")

    if n < 1:
        raise SystemExit("❌ ต้องมีอย่างน้อย 1 จุด")

    capture_dir = CALIBRATION_DIR / "verification"
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

    results = []

    try:
        for i in range(1, n + 1):
            print("\n" + "-" * 72)

            while True:
                try:
                    real = float(
                        input(
                            f"[{i}/{n}] ระยะจริงจากกล้องถึงวัตถุ (m): "
                        ).strip()
                    )
                    if real <= 0:
                        raise ValueError
                    break
                except ValueError:
                    print("❌ ระยะต้องเป็นตัวเลขมากกว่า 0")

            while True:
                input(
                    f"วางวัตถุที่ระยะ {real:.2f} m ให้เรียบร้อย "
                    "แล้วกด Enter เพื่อถ่ายภาพ..."
                )

                packet = capture_fresh_frame(camera)
                if packet is None:
                    print("❌ ถ่ายภาพไม่สำเร็จ ลองใหม่")
                    continue

                preset_tag = (
                    f"preset_{args.preset}"
                    if args.preset
                    else "global"
                )
                base_name = (
                    f"{preset_tag}_verify_{i:02d}_{real:.2f}m"
                )

                raw_path = capture_dir / f"{base_name}.jpg"
                guide_path = capture_dir / f"{base_name}_guide.jpg"

                ok_raw = cv2.imwrite(str(raw_path), packet.frame)
                ok_guide = cv2.imwrite(
                    str(guide_path),
                    draw_y_guide(packet.frame),
                )

                if not ok_raw:
                    print("❌ บันทึกภาพไม่สำเร็จ ลองใหม่")
                    continue

                print(f"✅ ถ่ายภาพแล้ว: {raw_path}")
                if ok_guide:
                    print(f"   ภาพช่วยดูแนว Y: {guide_path}")

                if open_in_paint(raw_path):
                    print("🎨 เปิดภาพใน Paint แล้ว")
                else:
                    print(
                        "เปิดภาพด้วย Paint/GIMP แล้วเลื่อนเมาส์ไปที่จุดสัมผัสพื้น"
                    )

                print(
                    "วิธีอ่าน: X ไม่ต้องใช้ ให้จดเฉพาะค่า Y "
                    "ของจุดล่างสุดที่สัมผัสพื้น"
                )

                y = read_y_pixel(i)
                if y is None:
                    print("🔄 ถ่ายภาพจุดนี้ใหม่")
                    continue

                estimated = model.estimate(y)
                if estimated is None or not math.isfinite(estimated):
                    print("❌ Calibration ไม่สามารถคำนวณระยะจาก Y นี้ได้")
                    print("   ลองตรวจค่า Y หรือเลือกจุดทดสอบใหม่")
                    continue

                error_m = abs(estimated - real)
                error_pct = (error_m / real) * 100.0

                results.append(
                    {
                        "real": real,
                        "y": y,
                        "estimated": estimated,
                        "error_m": error_m,
                        "error_pct": error_pct,
                    }
                )

                print("\n📏 ผล Verification จุดนี้")
                print(f"   ระยะจริง       : {real:.3f} m")
                print(f"   Y pixel         : {y:.1f} px")
                print(f"   ระยะที่คำนวณได้: {estimated:.3f} m")
                print(f"   Error           : {error_m:.3f} m")
                print(f"   Error (%)       : {error_pct:.2f}%")

                if error_pct <= 5:
                    print("   ระดับผล         : ✅ ดีมาก")
                elif error_pct <= 10:
                    print("   ระดับผล         : ✅ ดี")
                elif error_pct <= 15:
                    print("   ระดับผล         : ⚠️ พอใช้")
                else:
                    print("   ระดับผล         : ❌ ควร Calibration ใหม่")

                break

    finally:
        camera.stop()

    if not results:
        raise SystemExit("❌ ไม่มีผล verification")

    mae = sum(r["error_m"] for r in results) / len(results)
    mape = sum(r["error_pct"] for r in results) / len(results)
    rmse = math.sqrt(
        sum((r["estimated"] - r["real"]) ** 2 for r in results)
        / len(results)
    )
    max_error_pct = max(r["error_pct"] for r in results)

    print("\n" + "=" * 72)
    print("สรุปผล Distance Verification")
    print("=" * 72)

    print(
        f"{'Real(m)':>9} | {'Y(px)':>8} | {'Estimate(m)':>11} | "
        f"{'Error(m)':>9} | {'Error(%)':>9}"
    )
    print("-" * 72)

    for r in results:
        print(
            f"{r['real']:9.3f} | "
            f"{r['y']:8.1f} | "
            f"{r['estimated']:11.3f} | "
            f"{r['error_m']:9.3f} | "
            f"{r['error_pct']:8.2f}%"
        )

    print("-" * 72)
    print(f"MAE       = {mae:.3f} m")
    print(f"RMSE      = {rmse:.3f} m")
    print(f"MAPE      = {mape:.2f}%")
    print(f"Max Error = {max_error_pct:.2f}%")

    print("")
    if max_error_pct <= 5:
        print("✅ ผลรวมดีมาก: calibration เหมาะกับช่วงที่ทดสอบ")
    elif max_error_pct <= 10:
        print("✅ ผลรวมดี: calibration ใช้งานได้ในช่วงที่ทดสอบ")
    elif max_error_pct <= 15:
        print(
            "⚠️ ผลรวมพอใช้: แนะนำเพิ่มจุด calibration และ verify อีกครั้ง"
        )
    else:
        print(
            "❌ Error สูง: ควรทำ calibration ใหม่ "
            "หรือแยก calibration ตาม Preset/ลักษณะพื้น"
        )

    print(f"\n📁 ภาพ Verification อยู่ที่: {capture_dir}")
    print("✅ Distance verification completed")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import argparse
import math
import os
import platform
import subprocess
import time

import cv2

from calibration import load_north_offset_deg
from camera import LatestFrameCamera, wait_until_stable
from config import (
    FRAME_WIDTH,
    FRAME_HEIGHT,
    HFOV_DEG,
    PRESET_BEARING_DEG,
    POST_MOVE_FRESH_FRAMES,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    INITIAL_PRESET_WAIT_SEC,
    CALIBRATION_DIR,
)
from geometry import pixel_to_bearing, normalize_bearing
from ptz import PTZController


def open_in_paint(path):
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


def circular_signed_error(predicted_deg, actual_deg):
    """ค่าคลาดเคลื่อน signed ในช่วง -180..+180 องศา"""
    return ((predicted_deg - actual_deg + 180.0) % 360.0) - 180.0


def wait_fresh_frames(camera, after_seq, count):
    seq = after_seq
    packet = None
    for _ in range(max(1, count)):
        packet = camera.wait_for_newer(seq, timeout=2.0)
        if packet is None:
            return None
        seq = packet.seq
    return packet


def capture_stable_frame(camera):
    """รับเฉพาะเฟรมใหม่และนิ่ง เพื่อลด stale/motion frame"""
    start_seq = camera.sequence
    fresh = wait_fresh_frames(camera, start_seq, POST_MOVE_FRESH_FRAMES)
    if fresh is None:
        return None

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )
    return stable if stable is not None else fresh


def draw_x_guide(frame):
    guide = frame.copy()
    center_x = FRAME_WIDTH // 2

    # เส้นแนว X ทุก 100 px
    for x in range(0, FRAME_WIDTH, 100):
        cv2.line(
            guide,
            (x, 0),
            (x, FRAME_HEIGHT - 1),
            (0, 255, 255),
            1,
        )
        cv2.putText(
            guide,
            f"X={x}",
            (min(FRAME_WIDTH - 75, x + 4), 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    # เส้นกลางภาพ
    cv2.line(
        guide,
        (center_x, 0),
        (center_x, FRAME_HEIGHT - 1),
        (0, 0, 255),
        2,
    )
    cv2.putText(
        guide,
        f"CENTER X={center_x}",
        (max(5, center_x - 95), 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )

    return guide


def read_float(prompt, allow_zero=False):
    while True:
        try:
            value = float(input(prompt).strip())
            if allow_zero:
                return value
            if value > 0:
                return value
        except ValueError:
            pass
        print("❌ กรุณาใส่ตัวเลขที่ถูกต้อง")


def read_x_pixel(index):
    while True:
        raw = input(
            f"[{index}] X pixel ของ 'จุดกึ่งกลางเป้าหมาย' (0-{FRAME_WIDTH - 1}) "
            "หรือพิมพ์ r เพื่อถ่ายใหม่: "
        ).strip().lower()

        if raw == "r":
            return None

        try:
            x = float(raw)
        except ValueError:
            print("❌ กรุณาใส่ตัวเลข X หรือ r")
            continue

        if not (0 <= x < FRAME_WIDTH):
            print(f"❌ X ต้องอยู่ระหว่าง 0 ถึง {FRAME_WIDTH - 1}")
            continue

        return x


def main():
    ap = argparse.ArgumentParser(
        description="Verify pixel-to-bearing calibration with captured RTSP images"
    )
    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=1,
        help="Preset ที่ใช้ตรวจ (default: 1)",
    )
    args = ap.parse_args()

    preset = args.preset
    preset_bearing = PRESET_BEARING_DEG[preset]
    north_offset = load_north_offset_deg()
    center_true_bearing = normalize_bearing(preset_bearing + north_offset)

    print("=" * 76)
    print("Smart Fire Detection v2 - Bearing Verification")
    print(f"Image size : {FRAME_WIDTH}x{FRAME_HEIGHT}")
    print(f"HFOV       : {HFOV_DEG:.3f}°")
    print(f"Preset     : {preset}")
    print(f"Preset bearing (nominal) : {preset_bearing:.3f}°")
    print(f"North offset             : {north_offset:+.3f}°")
    print(f"Center true bearing      : {center_true_bearing:.3f}°")
    print("")
    print("วิธีสร้าง 'มุมจริง' ด้วยตลับเมตร:")
    print("  1) ลากแนวกลางภาพของ Preset นี้ไปข้างหน้า = forward distance D")
    print("  2) จากจุดนั้นวัดฉากไปทางขวาเป็น +L หรือซ้ายเป็น -L")
    print("  3) relative angle = atan2(L, D)")
    print("  4) actual bearing = center bearing + relative angle")
    print("")
    print("ตัวอย่าง D=8m:")
    print("  -20° -> L≈-2.91m")
    print("  -10° -> L≈-1.41m")
    print("    0° -> L= 0.00m")
    print("  +10° -> L≈+1.41m")
    print("  +20° -> L≈+2.91m")
    print("=" * 76)

    try:
        n = int(input("จำนวนจุด verification (แนะนำ 5 จุด): ").strip())
    except ValueError:
        raise SystemExit("❌ จำนวนจุดต้องเป็นเลขจำนวนเต็ม")
    if n < 1:
        raise SystemExit("❌ ต้องมีอย่างน้อย 1 จุด")

    print("\n📡 กำลังเชื่อมต่อ RTSP...")
    camera = LatestFrameCamera().start()
    ptz = PTZController()

    deadline = time.monotonic() + 10.0
    while camera.latest(copy=False) is None:
        if time.monotonic() >= deadline:
            camera.stop()
            raise SystemExit("❌ RTSP timeout")
        time.sleep(0.1)

    print("✅ RTSP พร้อมใช้งาน")

    print(f"\n🔄 กำลังหมุนไป Preset {preset}...")
    seq_before_move = camera.sequence
    ok, wait_sec = ptz.goto_preset(preset)
    if not ok:
        camera.stop()
        raise SystemExit("❌ PTZ command failed")

    # ครั้งแรกไม่รู้ว่ากล้องเริ่มจากมุมไหน จึงเผื่อ INITIAL_PRESET_WAIT_SEC
    wait_sec = max(wait_sec, INITIAL_PRESET_WAIT_SEC)
    print(f"⏱️ รอ PTZ {wait_sec:.2f}s")
    time.sleep(wait_sec)

    fresh = wait_fresh_frames(camera, max(seq_before_move, camera.sequence), POST_MOVE_FRESH_FRAMES)
    if fresh is None:
        camera.stop()
        raise SystemExit("❌ ไม่ได้รับ fresh frame หลัง PTZ")

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )
    if stable is None:
        print("⚠️ ไม่ยืนยันภาพนิ่งภายใน timeout แต่จะให้ลองทดสอบต่อ")
    else:
        print(f"✅ PTZ + stable frame พร้อม | seq={stable.seq}")

    out_dir = CALIBRATION_DIR / "bearing_verification"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []

    try:
        for i in range(1, n + 1):
            print("\n" + "-" * 76)
            print(f"[{i}/{n}] สร้างตำแหน่งเป้าหมายบนพื้น")

            forward_m = read_float(
                "ระยะไปข้างหน้าตามแนวกลางกล้อง D (m): "
            )
            lateral_m = read_float(
                "ระยะเยื้อง L (m) | ขวาเป็น +, ซ้ายเป็น -, กลาง=0: ",
                allow_zero=True,
            )

            relative_deg = math.degrees(math.atan2(lateral_m, forward_m))
            actual_bearing = normalize_bearing(center_true_bearing + relative_deg)
            slant_distance = math.hypot(forward_m, lateral_m)

            half_fov = HFOV_DEG / 2.0
            print(f"📐 Relative angle จริง = {relative_deg:+.3f}°")
            print(f"🧭 Actual bearing จริง  = {actual_bearing:.3f}°")
            print(f"📏 ระยะตรงถึงเป้าหมาย   = {slant_distance:.3f}m")

            if abs(relative_deg) > half_fov:
                print(
                    f"⚠️ จุดนี้อยู่นอก HFOV โดยประมาณ "
                    f"(±{half_fov:.2f}°) เป้าหมายอาจไม่อยู่ในภาพ"
                )

            while True:
                input(
                    "วางเป้าหมายที่ตำแหน่งนี้ให้นิ่ง แล้วกด Enter เพื่อถ่ายภาพ..."
                )

                packet = capture_stable_frame(camera)
                if packet is None:
                    print("❌ ไม่ได้รับภาพใหม่ ลองอีกครั้ง")
                    continue

                base = (
                    f"preset_{preset:02d}_verify_{i:02d}_"
                    f"rel_{relative_deg:+.2f}deg"
                )
                raw_path = out_dir / f"{base}.jpg"
                guide_path = out_dir / f"{base}_guide.jpg"

                cv2.imwrite(str(raw_path), packet.frame)
                cv2.imwrite(str(guide_path), draw_x_guide(packet.frame))

                print(f"✅ ถ่ายภาพแล้ว: {raw_path}")
                print(f"   ภาพช่วยดู X: {guide_path}")

                if open_in_paint(raw_path):
                    print("🎨 เปิดภาพใน Paint แล้ว")
                else:
                    print("เปิดภาพด้วย Paint/GIMP แล้วอ่านพิกัด X")

                print(
                    "เอาเมาส์ชี้ที่ 'กึ่งกลางเป้าหมาย' และจดเฉพาะ X pixel "
                    "(ไม่ใช้ Y ในการทดสอบ Bearing)"
                )

                x_px = read_x_pixel(i)
                if x_px is None:
                    print("🔄 ถ่ายภาพจุดนี้ใหม่")
                    continue

                predicted = pixel_to_bearing(
                    preset_bearing,
                    x_px,
                    FRAME_WIDTH,
                    HFOV_DEG,
                    north_offset_deg=north_offset,
                )

                signed_error = circular_signed_error(predicted, actual_bearing)
                abs_error = abs(signed_error)

                # แปลง angular error เป็น lateral error โดยประมาณที่ระยะเป้าหมาย
                lateral_error_m = slant_distance * math.tan(math.radians(abs_error))

                results.append(
                    {
                        "forward": forward_m,
                        "lateral": lateral_m,
                        "relative": relative_deg,
                        "actual": actual_bearing,
                        "x": x_px,
                        "predicted": predicted,
                        "signed_error": signed_error,
                        "abs_error": abs_error,
                        "range": slant_distance,
                        "lateral_error_m": lateral_error_m,
                    }
                )

                print("\n🧭 ผล Bearing Verification จุดนี้")
                print(f"   X pixel             : {x_px:.1f}px")
                print(f"   Bearing จริง        : {actual_bearing:.3f}°")
                print(f"   Bearing ที่คำนวณได้ : {predicted:.3f}°")
                print(f"   Signed error        : {signed_error:+.3f}°")
                print(f"   Absolute error      : {abs_error:.3f}°")
                print(
                    f"   Lateral error โดยประมาณ @ {slant_distance:.2f}m "
                    f": {lateral_error_m:.3f}m"
                )

                break

    finally:
        camera.stop()

    if not results:
        raise SystemExit("❌ ไม่มีผล verification")

    mae_deg = sum(r["abs_error"] for r in results) / len(results)
    rmse_deg = math.sqrt(
        sum(r["signed_error"] ** 2 for r in results) / len(results)
    )
    max_deg = max(r["abs_error"] for r in results)

    print("\n" + "=" * 96)
    print("สรุปผล Bearing Verification")
    print("=" * 96)
    print(
        f"{'Rel(°)':>8} | {'X(px)':>7} | {'Actual(°)':>10} | "
        f"{'Pred(°)':>9} | {'Err(°)':>8} | {'LatErr(m)':>9}"
    )
    print("-" * 96)

    for r in results:
        print(
            f"{r['relative']:8.3f} | "
            f"{r['x']:7.1f} | "
            f"{r['actual']:10.3f} | "
            f"{r['predicted']:9.3f} | "
            f"{r['signed_error']:+8.3f} | "
            f"{r['lateral_error_m']:9.3f}"
        )

    print("-" * 96)
    print(f"Angular MAE  = {mae_deg:.3f}°")
    print(f"Angular RMSE = {rmse_deg:.3f}°")
    print(f"Max Error    = {max_deg:.3f}°")

    print("")
    if max_deg <= 1.0:
        print("✅ ผลดีมาก: angular error สูงสุดไม่เกิน 1°")
    elif max_deg <= 2.0:
        print("✅ ผลดี: angular error สูงสุดไม่เกิน 2°")
    elif max_deg <= 3.0:
        print("⚠️ พอใช้: ควรเพิ่มจุดทดสอบ/สอบเทียบ HFOV หรือ principal point")
    else:
        print("❌ Error สูง: ควรตรวจ HFOV, แนวกลางภาพ, North offset และตำแหน่ง Preset")

    print(f"\n📁 ภาพอยู่ที่: {out_dir}")
    print("✅ Bearing verification completed")


if __name__ == "__main__":
    main()
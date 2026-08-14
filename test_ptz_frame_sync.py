import time
import cv2

from camera import LatestFrameCamera, wait_until_stable
from ptz import PTZController
from config import (
    POST_MOVE_FRESH_FRAMES,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    STATIC_DIR,
)


def wait_fresh(camera, after_seq, count):
    seq = after_seq
    packet = None

    for _ in range(count):
        packet = camera.wait_for_newer(seq, timeout=2.0)
        if packet is None:
            return None
        seq = packet.seq

    return packet


camera = LatestFrameCamera().start()
ptz = PTZController()

print("Waiting for RTSP...")

deadline = time.monotonic() + 10

while camera.latest(copy=False) is None:
    if time.monotonic() > deadline:
        raise RuntimeError("RTSP timeout")
    time.sleep(0.1)

print("✅ RTSP ready")

# ทดสอบให้เห็นความแตกต่างของภาพชัด ๆ
sequence = [1, 3, 5, 1, 7, 9, 1]

try:
    for preset in sequence:
        seq_before = camera.sequence

        print(f"\n==============================")
        print(f"Move to preset {preset}")
        print(f"seq before move = {seq_before}")

        ok, wait_sec = ptz.goto_preset(preset)

        if not ok:
            print("❌ PTZ command failed")
            continue

        print(f"PTZ wait = {wait_sec:.2f}s")
        time.sleep(wait_sec)

        # sequence หลังจากกล้องควรถึงตำแหน่งแล้ว
        arrival_seq = camera.sequence

        print(f"seq after movement = {arrival_seq}")

        # บังคับรอเฟรมใหม่หลังกล้องถึง
        fresh = wait_fresh(
            camera,
            arrival_seq,
            POST_MOVE_FRESH_FRAMES
        )

        if fresh is None:
            print("❌ Fresh frame timeout")
            continue

        print(
            f"fresh seq = {fresh.seq} "
            f"age={time.time() - fresh.timestamp:.3f}s"
        )

        # ตรวจว่าภาพหยุดนิ่งจริง
        stable = wait_until_stable(
            camera,
            fresh.seq,
            STABLE_DIFF_THRESHOLD,
            STABLE_REQUIRED_PAIRS,
            STABLE_TIMEOUT_SEC
        )

        if stable is None:
            print("❌ Image never became stable")
            continue

        age = time.time() - stable.timestamp

        output = STATIC_DIR / f"sync_preset_{preset}.jpg"
        cv2.imwrite(str(output), stable.frame)

        print(
            f"✅ STABLE preset={preset} "
            f"seq={stable.seq} "
            f"age={age:.3f}s"
        )
        print(f"saved -> {output}")

finally:
    camera.stop()

print("\n✅ PTZ + frame sync test completed")
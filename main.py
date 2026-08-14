#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
import cv2
import psutil
from camera import LatestFrameCamera, wait_until_stable
from config import (SWEEP_SEQUENCE, PRESET_BEARING_DEG, INITIAL_PRESET_WAIT_SEC,
                    STABLE_DIFF_THRESHOLD, STABLE_REQUIRED_PAIRS, STABLE_TIMEOUT_SEC,
                    POST_MOVE_FRESH_FRAMES, FRAMES_PER_SCAN, MIN_CONFIRM_FRAMES,
                    FRAME_SAMPLE_GAP_SEC, ALERT_COOLDOWN_SEC, STATIC_DIR,
                    DASHBOARD_WRITE_INTERVAL_SEC)
from detection import FireDetector, consensus
from notify import TelegramWorker, format_alert
from overlay import draw_detection, draw_status
from ptz import PTZController

LATEST_FRAME = STATIC_DIR / 'latest_frame.jpg'
LATEST_ALERT = STATIC_DIR / 'latest_alert.jpg'
STATUS_JSON = STATIC_DIR / 'status.json'

def atomic_imwrite(path: Path, frame):
    tmp = path.with_name(path.stem + '.tmp' + path.suffix)
    if cv2.imwrite(str(tmp), frame):
        os.replace(tmp, path)

def write_status(data):
    tmp = STATUS_JSON.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, STATUS_JSON)

def wait_fresh_frames(camera, after_seq, count):
    seq = after_seq
    last = None
    for _ in range(count):
        last = camera.wait_for_newer(seq, timeout=2.0)
        if last is None:
            return None
        seq = last.seq
    return last

def scan_preset(camera, ptz, detector, preset):
    print(f'\n🔄 Move -> preset {preset} center={PRESET_BEARING_DEG[preset]:.1f}°')
    ok, wait_sec = ptz.goto_preset(preset)
    if not ok:
        print('❌ PTZ command failed')
        return [], None
    time.sleep(wait_sec)

    # Important: note sequence AFTER movement delay, then require newer frames.
    arrival_seq = camera.sequence
    fresh = wait_fresh_frames(camera, arrival_seq, POST_MOVE_FRESH_FRAMES)
    if fresh is None:
        print('⚠️ No fresh post-move frame')
        return [], None
    stable = wait_until_stable(camera, fresh.seq, STABLE_DIFF_THRESHOLD,
                               STABLE_REQUIRED_PAIRS, STABLE_TIMEOUT_SEC)
    if stable is None:
        print('⚠️ Image not stable; skip preset')
        return [], None

    sets = []
    packet = stable
    for i in range(FRAMES_PER_SCAN):
        if i > 0:
            packet = camera.wait_for_newer(packet.seq, timeout=2.0)
            if packet is None:
                break
            time.sleep(FRAME_SAMPLE_GAP_SEC)
        sets.append(detector.detect(packet.frame, preset))
    return consensus(sets, MIN_CONFIRM_FRAMES), packet

def main():
    print('🔥 Smart Fire Detection v2')
    camera = LatestFrameCamera().start()
    deadline = time.monotonic() + 10.0
    while camera.latest(copy=False) is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if camera.latest(copy=False) is None:
        raise RuntimeError('เปิด RTSP ไม่สำเร็จภายใน 10 วินาที')

    detector = FireDetector()
    ptz = PTZController()
    notifier = TelegramWorker()
    last_alert = 0.0
    last_dashboard = 0.0

    ok, _ = ptz.goto_preset(1)
    if not ok:
        raise RuntimeError('ไป Preset 1 ไม่สำเร็จ')
    time.sleep(INITIAL_PRESET_WAIT_SEC)

    try:
        while True:
            for preset in SWEEP_SEQUENCE[1:]:
                confirmed, packet = scan_preset(camera, ptz, detector, preset)
                if packet is None:
                    continue
                frame = packet.frame.copy()
                for d in confirmed:
                    draw_detection(frame, d)
                draw_status(frame, preset, PRESET_BEARING_DEG[preset], 'SCAN')
                now = time.time()
                if now - last_dashboard >= DASHBOARD_WRITE_INTERVAL_SEC:
                    atomic_imwrite(LATEST_FRAME, frame)
                    last_dashboard = now
                write_status({'timestamp': now, 'preset': preset,
                              'center_bearing_deg': PRESET_BEARING_DEG[preset],
                              'detections': len(confirmed),
                              'cpu_percent': psutil.cpu_percent(interval=None),
                              'ram_percent': psutil.virtual_memory().percent})
                if confirmed and now - last_alert >= ALERT_COOLDOWN_SEC:
                    best = confirmed[0]
                    atomic_imwrite(LATEST_ALERT, frame)
                    notifier.submit(format_alert(best), str(LATEST_ALERT))
                    print(format_alert(best))
                    last_alert = now
    except KeyboardInterrupt:
        print('\n🛑 Stop')
    finally:
        camera.stop()

if __name__ == '__main__':
    main()

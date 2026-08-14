#!/usr/bin/env python3
import time
from ptz import PTZController
from config import SWEEP_SEQUENCE, PRESET_BEARING_DEG
ptz = PTZController()
for preset in SWEEP_SEQUENCE:
    ok, wait_sec = ptz.goto_preset(preset)
    print(f'preset={preset} bearing={PRESET_BEARING_DEG[preset]:.1f} ok={ok} wait={wait_sec:.2f}s')
    if not ok:
        raise SystemExit('❌ PTZ failed')
    time.sleep(wait_sec)
print('✅ PTZ sequence passed')

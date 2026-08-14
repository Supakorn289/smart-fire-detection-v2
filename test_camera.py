#!/usr/bin/env python3
import time
import cv2
from camera import LatestFrameCamera
cam = LatestFrameCamera().start()
try:
    last = -1
    p = None
    for _ in range(10):
        p = cam.wait_for_newer(last, timeout=3.0)
        if p is None:
            raise SystemExit('❌ ไม่ได้รับเฟรมใหม่')
        last = p.seq
        print(f'frame={p.seq} age={time.time()-p.timestamp:.3f}s shape={p.frame.shape}')
    cv2.imwrite('static/camera_test.jpg', p.frame)
    print('✅ camera test passed -> static/camera_test.jpg')
finally:
    cam.stop()

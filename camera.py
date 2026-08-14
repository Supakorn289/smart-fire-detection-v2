import os
import threading
import time
from dataclasses import dataclass
import cv2
import numpy as np
from config import CAMERA_ID, FRAME_WIDTH, FRAME_HEIGHT

@dataclass
class FramePacket:
    seq: int
    timestamp: float
    frame: np.ndarray

class LatestFrameCamera:
    '''Continuously decodes RTSP but exposes only the newest frame.'''
    def __init__(self, source: str = CAMERA_ID):
        self.source = source
        self._cap = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._packet = None
        self._stop = threading.Event()
        self._thread = None
        self._connected = False

    @property
    def connected(self):
        return self._connected

    @property
    def sequence(self):
        with self._lock:
            return -1 if self._packet is None else self._packet.seq

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='rtsp-latest-frame', daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._cap is not None:
            self._cap.release()
        self._connected = False

    def _open(self):
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|stimeout;5000000'
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self):
        seq = 0
        while not self._stop.is_set():
            if self._cap is None or not self._cap.isOpened():
                if self._cap is not None:
                    self._cap.release()
                self._cap = self._open()
                if not self._cap.isOpened():
                    self._connected = False
                    time.sleep(1.0)
                    continue
                self._connected = True
            ok, frame = self._cap.read()
            if not ok or frame is None:
                self._connected = False
                self._cap.release()
                self._cap = None
                time.sleep(0.5)
                continue
            if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
            packet = FramePacket(seq, time.time(), frame)
            seq += 1
            with self._cond:
                self._packet = packet
                self._cond.notify_all()

    def latest(self, copy=True):
        with self._lock:
            if self._packet is None:
                return None
            p = self._packet
            return FramePacket(p.seq, p.timestamp, p.frame.copy() if copy else p.frame)

    def wait_for_newer(self, after_seq: int, timeout: float = 2.0, copy=True):
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                if self._packet is not None and self._packet.seq > after_seq:
                    p = self._packet
                    return FramePacket(p.seq, p.timestamp, p.frame.copy() if copy else p.frame)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)

def motion_score(a, b) -> float:
    ga = cv2.cvtColor(cv2.resize(a, (160, 90)), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, (160, 90)), cv2.COLOR_BGR2GRAY)
    return float(cv2.absdiff(ga, gb).mean())

def wait_until_stable(camera: LatestFrameCamera, after_seq: int, threshold: float,
                      required_pairs: int, timeout: float):
    deadline = time.monotonic() + timeout
    prev = None
    stable_pairs = 0
    seq = after_seq
    while time.monotonic() < deadline:
        p = camera.wait_for_newer(seq, timeout=min(1.0, max(0.05, deadline - time.monotonic())))
        if p is None:
            continue
        seq = p.seq
        if prev is not None:
            if motion_score(prev.frame, p.frame) <= threshold:
                stable_pairs += 1
                if stable_pairs >= required_pairs:
                    return p
            else:
                stable_pairs = 0
        prev = p
    return None

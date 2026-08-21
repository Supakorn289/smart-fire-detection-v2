#!/usr/bin/env python3
# tests/test_integration_runtime_scan.py

"""
Smart Fire Detection v2
Runtime Scan Integration Tests

Scope:

    PTZ
      ↓
    Fresh frame
      ↓
    Stable frame
      ↓
    AI samples
      ↓
    Multi-frame Consensus
      ↓
    Location Safety
      ↓
    Runtime Status

ไม่ใช้:
- Camera จริง
- PTZ จริง
- RTSP
- Final Model จริง
- Telegram
- Network
- Production hardware
"""

from types import SimpleNamespace

import numpy as np

import config
import main as runtime

from detection import Detection


# ============================================================
# Helpers
# ============================================================

def make_frame(
    value=0,
):
    """
    Synthetic BGR frame
    """

    return np.full(
        (
            config.FRAME_HEIGHT,
            config.FRAME_WIDTH,
            3,
        ),
        value,
        dtype=np.uint8,
    )


def make_packet(
    seq,
    *,
    value=0,
    timestamp=1000.0,
):
    """
    Minimal FramePacket-compatible object
    """

    return SimpleNamespace(
        seq=seq,
        timestamp=timestamp,
        frame=make_frame(
            value
        ),
    )


def make_fire_detection(
    *,
    confidence=0.90,
    bbox=(
        300,
        200,
        500,
        500,
    ),
    gps=None,
    distance_m=None,
    distance_quality="unavailable",
):
    return Detection(
        bbox=bbox,
        model_class="fire",
        canonical_class="fire",
        confidence=confidence,
        distance_m=distance_m,
        bearing_deg=45.0,
        gps=gps,
        distance_quality=distance_quality,
    )


# ============================================================
# Fake PTZ
# ============================================================

class FakePTZ:

    def __init__(
        self,
        *,
        ok=True,
        wait_sec=0.0,
    ):
        self.ok = ok
        self.wait_sec = wait_sec
        self.calls = []


    def goto_preset(
        self,
        preset,
    ):
        self.calls.append(
            preset
        )

        return (
            self.ok,
            self.wait_sec,
        )


# ============================================================
# Fake Camera
# ============================================================

class FakeCamera:

    def __init__(
        self,
        packets=None,
        *,
        sequence=10,
    ):
        self.sequence = sequence

        self.packets = list(
            packets or []
        )

        self.wait_calls = []


    def wait_for_newer(
        self,
        after_seq,
        timeout=2.0,
        copy=True,
    ):
        self.wait_calls.append(
            {
                "after_seq":
                    after_seq,

                "timeout":
                    timeout,

                "copy":
                    copy,
            }
        )

        if not self.packets:
            return None

        return self.packets.pop(
            0
        )


# ============================================================
# Fake Detector
# ============================================================

class FakeDetector:

    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []


    def detect(
        self,
        frame,
        preset,
    ):
        self.calls.append(
            {
                "frame":
                    frame,

                "preset":
                    preset,
            }
        )

        if not self.responses:
            raise AssertionError(
                "FakeDetector has no response left"
            )

        return self.responses.pop(
            0
        )


# ============================================================
# Test 1
# wait_fresh_frames requires progressively newer packets
# ============================================================

def test_wait_fresh_frames_advances_sequence():

    packets = [
        make_packet(11),
        make_packet(12),
        make_packet(13),
    ]


    camera = FakeCamera(
        packets,
        sequence=10,
    )


    result = runtime.wait_fresh_frames(
        camera,
        after_seq=10,
        count=3,
    )


    assert result is not None

    assert (
        result.seq
        == 13
    )


    assert [
        call["after_seq"]
        for call
        in camera.wait_calls
    ] == [
        10,
        11,
        12,
    ]


# ============================================================
# Test 2
# PTZ failure must stop scan before AI
# ============================================================

def test_scan_preset_stops_on_ptz_failure(
    monkeypatch,
):

    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds: None,
    )


    ptz = FakePTZ(
        ok=False
    )


    camera = FakeCamera()


    detector = FakeDetector(
        []
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
        )
    )


    assert confirmed == []

    assert packet is None


    assert (
        info["status"]
        == "ptz_failed"
    )

    assert (
        info["ptz_ok"]
        is False
    )

    assert (
        info["frames_processed"]
        == 0
    )


    assert (
        ptz.calls
        == [1]
    )

    assert (
        detector.calls
        == []
    )


# ============================================================
# Test 3
# Fresh-frame timeout must stop before stability / AI
# ============================================================

def test_scan_preset_stops_on_fresh_frame_timeout(
    monkeypatch,
):

    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds: None,
    )


    monkeypatch.setattr(
        runtime,
        "wait_fresh_frames",
        lambda camera, after_seq, count:
            None,
    )


    stable_called = {
        "value": False
    }


    def fake_stable(
        *args,
        **kwargs,
    ):
        stable_called["value"] = True

        return make_packet(
            20
        )


    monkeypatch.setattr(
        runtime,
        "wait_until_stable",
        fake_stable,
    )


    ptz = FakePTZ(
        ok=True,
        wait_sec=0.0,
    )


    camera = FakeCamera(
        sequence=10
    )


    detector = FakeDetector(
        []
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
        )
    )


    assert confirmed == []

    assert packet is None


    assert (
        info["status"]
        == "fresh_frame_timeout"
    )

    assert (
        info["ptz_ok"]
        is True
    )

    assert (
        info["frames_processed"]
        == 0
    )


    # Stable check ต้องไม่เกิด
    # ถ้ายังไม่มี Fresh Frame
    assert (
        stable_called["value"]
        is False
    )


    assert (
        detector.calls
        == []
    )


# ============================================================
# Test 4
# Stability timeout must prevent AI inference
# ============================================================

def test_scan_preset_stops_when_frame_never_stabilizes(
    monkeypatch,
):

    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds: None,
    )


    fresh_packet = make_packet(
        13
    )


    monkeypatch.setattr(
        runtime,
        "wait_fresh_frames",
        lambda camera, after_seq, count:
            fresh_packet,
    )


    monkeypatch.setattr(
        runtime,
        "wait_until_stable",
        lambda *args, **kwargs:
            None,
    )


    ptz = FakePTZ(
        ok=True,
        wait_sec=0.0,
    )


    camera = FakeCamera(
        sequence=10
    )


    detector = FakeDetector(
        []
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
        )
    )


    assert confirmed == []

    assert packet is None


    assert (
        info["status"]
        == "stability_timeout"
    )

    assert (
        info["ptz_ok"]
        is True
    )

    assert (
        info["frames_processed"]
        == 0
    )


    assert (
        detector.calls
        == []
    )


# ============================================================
# Test 5
# Partial frames must not create 2/3 confirmation
# ============================================================

def test_scan_preset_partial_frames_do_not_confirm(
    monkeypatch,
):

    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds: None,
    )


    fresh_packet = make_packet(
        13
    )


    stable_packet = make_packet(
        20
    )


    monkeypatch.setattr(
        runtime,
        "wait_fresh_frames",
        lambda camera, after_seq, count:
            fresh_packet,
    )


    monkeypatch.setattr(
        runtime,
        "wait_until_stable",
        lambda *args, **kwargs:
            stable_packet,
    )


    # Frame 2 จะ timeout
    camera = FakeCamera(
        packets=[],
        sequence=10,
    )


    ptz = FakePTZ(
        ok=True,
        wait_sec=0.0,
    )


    detector = FakeDetector(
        [
            [
                make_fire_detection(
                    confidence=0.95
                )
            ]
        ]
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
        )
    )


    # มี Detection แค่ Frame เดียว
    # ห้ามกลายเป็น Confirmed Detection
    assert confirmed == []


    assert (
        packet.seq
        == 20
    )


    assert (
        info["status"]
        == "partial_frames"
    )


    assert (
        info["frames_processed"]
        == 1
    )


    assert (
        len(
            detector.calls
        )
        == 1
    )


# ============================================================
# Test 6
# Full Runtime Scan:
#
# PTZ -> Fresh -> Stable -> 3 Frames -> 2/3 Consensus
# ============================================================

def test_scan_preset_full_two_of_three_consensus(
    monkeypatch,
):

    sleep_calls = []


    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds:
            sleep_calls.append(
                seconds
            ),
    )


    fresh_packet = make_packet(
        13,
        value=1,
    )


    stable_packet = make_packet(
        20,
        value=2,
    )


    frame_2 = make_packet(
        21,
        value=3,
    )


    frame_3 = make_packet(
        22,
        value=4,
    )


    monkeypatch.setattr(
        runtime,
        "wait_fresh_frames",
        lambda camera, after_seq, count:
            fresh_packet,
    )


    monkeypatch.setattr(
        runtime,
        "wait_until_stable",
        lambda *args, **kwargs:
            stable_packet,
    )


    camera = FakeCamera(
        packets=[
            frame_2,
            frame_3,
        ],
        sequence=10,
    )


    ptz = FakePTZ(
        ok=True,
        wait_sec=0.0,
    )


    detector = FakeDetector(
        [
            # Frame 1
            [
                make_fire_detection(
                    confidence=0.61,
                    bbox=(
                        300,
                        200,
                        500,
                        500,
                    ),
                    distance_m=20.0,
                    distance_quality=(
                        "calibrated"
                    ),
                    gps=(
                        1.234567,
                        2.345678,
                    ),
                )
            ],

            # Frame 2
            [
                make_fire_detection(
                    confidence=0.92,
                    bbox=(
                        310,
                        205,
                        510,
                        505,
                    ),
                    distance_m=20.0,
                    distance_quality=(
                        "calibrated"
                    ),
                    gps=(
                        1.234567,
                        2.345678,
                    ),
                )
            ],

            # Frame 3
            [],
        ]
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
            first_move=False,
            site_bearing_calibrated=False,
        )
    )


    # --------------------------------------------------------
    # Complete scan
    # --------------------------------------------------------

    assert (
        info["status"]
        == "ok"
    )

    assert (
        info["ptz_ok"]
        is True
    )

    assert (
        info["stable_seq"]
        == 20
    )

    assert (
        info["frames_processed"]
        == config.FRAMES_PER_SCAN
    )

    assert (
        len(
            info["inference_ms"]
        )
        == config.FRAMES_PER_SCAN
    )


    # --------------------------------------------------------
    # Detector receives exactly 3 frames
    # --------------------------------------------------------

    assert (
        len(
            detector.calls
        )
        == 3
    )


    assert (
        detector.calls[0]["frame"]
        is stable_packet.frame
    )

    assert (
        detector.calls[1]["frame"]
        is frame_2.frame
    )

    assert (
        detector.calls[2]["frame"]
        is frame_3.frame
    )


    # --------------------------------------------------------
    # Same preset for every AI frame
    # --------------------------------------------------------

    assert {
        call["preset"]
        for call
        in detector.calls
    } == {
        1
    }


    # --------------------------------------------------------
    # 2 / 3 Consensus
    # --------------------------------------------------------

    assert (
        len(
            confirmed
        )
        == 1
    )


    result = confirmed[0]


    assert (
        result.canonical_class
        == "fire"
    )


    # Highest-confidence representative
    assert np.isclose(
        result.confidence,
        0.92,
        atol=1e-6,
    )


    # --------------------------------------------------------
    # CRITICAL LOCATION SAFETY
    #
    # Detection object มี GPS และ distance quality calibrated
    # แต่ Site Bearing ยังไม่ calibrated
    #
    # main.py ต้อง suppress GPS
    # --------------------------------------------------------

    assert (
        result.distance_m
        == 20.0
    )

    assert (
        result.distance_quality
        == "calibrated"
    )

    assert (
        result.gps
        is None
    )


    # --------------------------------------------------------
    # Last packet must be latest AI sample
    # --------------------------------------------------------

    assert (
        packet.seq
        == 22
    )


# ============================================================
# Test 7
# first_move must respect INITIAL_PRESET_WAIT_SEC
# ============================================================

def test_scan_preset_first_move_uses_initial_wait(
    monkeypatch,
):

    sleep_calls = []


    monkeypatch.setattr(
        runtime.time,
        "sleep",
        lambda seconds:
            sleep_calls.append(
                seconds
            ),
    )


    # ออกจาก scan หลัง Fresh timeout
    # เพื่อไม่ต้องจำลอง pipeline ที่เหลือ
    monkeypatch.setattr(
        runtime,
        "wait_fresh_frames",
        lambda camera, after_seq, count:
            None,
    )


    ptz = FakePTZ(
        ok=True,
        wait_sec=0.01,
    )


    camera = FakeCamera(
        sequence=10
    )


    detector = FakeDetector(
        []
    )


    confirmed, packet, info = (
        runtime.scan_preset(
            camera,
            ptz,
            detector,
            preset=1,
            first_move=True,
        )
    )


    assert confirmed == []

    assert packet is None


    assert (
        info["status"]
        == "fresh_frame_timeout"
    )


    # first movement:
    #
    # wait_sec = max(
    #     PTZ calculated wait,
    #     INITIAL_PRESET_WAIT_SEC
    # )
    assert (
        sleep_calls[0]
        == config.INITIAL_PRESET_WAIT_SEC
    )


# ============================================================
# Test 8
# Scan result -> Runtime Dashboard status
# ============================================================

def test_scan_result_builds_runtime_status(
    monkeypatch,
):

    # --------------------------------------------------------
    # ไม่ต้องการค่าจากเครื่องจริงของ pytest runner
    # --------------------------------------------------------

    monkeypatch.setattr(
        runtime.psutil,
        "cpu_percent",
        lambda interval=None:
            12.5,
    )


    monkeypatch.setattr(
        runtime.psutil,
        "virtual_memory",
        lambda:
            SimpleNamespace(
                percent=34.0
            ),
    )


    detection = make_fire_detection(
        confidence=0.93,
        gps=None,
        distance_m=None,
        distance_quality="unavailable",
    )


    scan_info = {
        "status":
            "ok",

        "preset":
            1,

        "ptz_ok":
            True,

        "frames_processed":
            3,

        "inference_ms":
            [
                100.0,
                101.0,
                102.0,
            ],

        "stable_seq":
            20,

        "scan_ms":
            500.12345,
    }


    status = runtime.build_status(
        timestamp=1234567890.0,
        cycle=2,
        step=4,
        preset=1,
        confirmed=[
            detection
        ],
        scan_info=scan_info,
        site_bearing_calibrated=False,
    )


    assert (
        status["timestamp"]
        == 1234567890.0
    )

    assert (
        status["runtime_status"]
        == "ok"
    )

    assert (
        status["cycle"]
        == 2
    )

    assert (
        status["step"]
        == 4
    )

    assert (
        status["preset"]
        == 1
    )

    assert (
        status["frames_processed"]
        == 3
    )

    assert (
        status["detections"]
        == 1
    )

    assert (
        status["cpu_percent"]
        == 12.5
    )

    assert (
        status["ram_percent"]
        == 34.0
    )


    assert (
        len(
            status["confirmed"]
        )
        == 1
    )


    confirmed = (
        status["confirmed"][0]
    )


    assert (
        confirmed["class"]
        == "fire"
    )

    assert (
        confirmed[
            "bearing_calibrated"
        ]
        is False
    )

    assert (
        confirmed["gps"]
        is None
    )
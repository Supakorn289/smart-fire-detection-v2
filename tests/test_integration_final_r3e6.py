#!/usr/bin/env python3
# tests/test_integration_final_r3e6.py

"""
Smart Fire Detection v2
Final R3-E6 Software Integration Tests

Scope:
    config.py
        ↓
    detection.FireDetector.detect()
        ↓
    YOLO.predict contract
        ↓
    Detection object
        ↓
    Multi-frame consensus

IMPORTANT:
- ไม่โหลด Final PT จริง
- ไม่ใช้ Camera
- ไม่ใช้ PTZ
- ไม่ใช้ Network
- ไม่ใช้ Telegram
- ไม่แก้ไข Model
"""

import numpy as np

import config
import detection


# ============================================================
# Fake Ultralytics objects
# ============================================================

class FakeBox:
    """
    จำลอง Ultralytics Box object
    เฉพาะ field ที่ detection.py ใช้งานจริง
    """

    def __init__(
        self,
        *,
        class_id,
        confidence,
        bbox,
    ):
        self.cls = np.array(
            [class_id],
            dtype=np.float32,
        )

        self.conf = np.array(
            [confidence],
            dtype=np.float32,
        )

        self.xyxy = np.array(
            [bbox],
            dtype=np.float32,
        )


class FakeResult:
    """
    จำลองหนึ่ง Ultralytics Result
    """

    def __init__(
        self,
        boxes,
    ):
        self.boxes = boxes


class RecordingModel:
    """
    Fake YOLO model

    - เก็บ kwargs ทุกครั้งที่ predict() ถูกเรียก
    - คืนผลลัพธ์ตาม responses ที่กำหนดไว้
    """

    def __init__(
        self,
        responses,
    ):
        self.responses = list(
            responses
        )

        self.calls = []


    def predict(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        if not self.responses:
            raise AssertionError(
                "Fake model has no response left"
            )

        return [
            self.responses.pop(0)
        ]


# ============================================================
# Helpers
# ============================================================

def make_frame():
    """
    สร้าง OpenCV-style BGR frame
    ที่ Resolution ตรง Production Geometry
    """

    return np.zeros(
        (
            config.FRAME_HEIGHT,
            config.FRAME_WIDTH,
            3,
        ),
        dtype=np.uint8,
    )


def make_detector(
    fake_model,
):
    """
    สร้าง FireDetector โดยไม่เรียก __init__()

    เหตุผล:
    __init__() จริงจะ:
    - ตรวจ SHA
    - โหลด Final PT
    - ตรวจ Model metadata

    สิ่งเหล่านั้นถูกตรวจแยกแล้วโดย:
    - inspect_model.py
    - preflight.py

    Integration Test นี้เน้น detect() -> consensus()
    """

    detector = (
        detection.FireDetector.__new__(
            detection.FireDetector
        )
    )

    detector.model = (
        fake_model
    )

    detector.names = {
        0: "fire",
        1: "smoke",
    }

    detector.class_map = {
        0: "fire",
        1: "smoke",
    }

    detector.unknown_names = []

    detector.north_offset_deg = 0.0

    return detector


def make_fire_result(
    *,
    confidence=0.90,
    bbox=(
        300,
        200,
        500,
        500,
    ),
):
    return FakeResult(
        [
            FakeBox(
                class_id=0,
                confidence=confidence,
                bbox=bbox,
            )
        ]
    )


def make_empty_result():
    return FakeResult(
        []
    )


# ============================================================
# Test 1
# Final Config Contract
# ============================================================

def test_final_r3e6_configuration_contract():

    assert (
        config.validate_final_model_contract()
        is True
    )

    assert (
        config.FINAL_MODEL_RELEASE
        == "R3-E6"
    )

    assert (
        config.MODEL_BACKEND
        == "pt"
    )

    assert (
        config.INFERENCE_DEVICE
        == "cpu"
    )

    assert (
        config.IMGSZ
        == 768
    )

    assert (
        config.CLASS_THRESHOLDS
        == {
            "fire": 0.25,
            "smoke": 0.25,
        }
    )

    assert (
        config.MODEL_NMS_IOU
        == 0.70
    )

    assert (
        config.MODEL_MAX_DET
        == 300
    )

    assert (
        config.MODEL_RECT
        is False
    )

    assert (
        config.MODEL_BATCH
        == 1
    )

    assert (
        config.FRAMES_PER_SCAN
        == 3
    )

    assert (
        config.MIN_CONFIRM_FRAMES
        == 2
    )

    assert (
        config.CONSENSUS_IOU_THRESHOLD
        == 0.30
    )


# ============================================================
# Test 2
# Raw BGR -> Exact YOLO.predict Contract
# ============================================================

def test_detector_uses_exact_final_predict_contract(
    monkeypatch,
):

    # --------------------------------------------------------
    # Distance Calibration ไม่เกี่ยวกับ Test นี้
    # --------------------------------------------------------

    monkeypatch.setattr(
        detection,
        "load_distance_model",
        lambda preset: None,
    )


    # --------------------------------------------------------
    # Fake Model
    # --------------------------------------------------------

    fake_model = RecordingModel(
        [
            make_empty_result(),
        ]
    )


    detector = make_detector(
        fake_model
    )


    # --------------------------------------------------------
    # Original BGR Frame
    # --------------------------------------------------------

    frame = make_frame()


    # --------------------------------------------------------
    # Detection
    # --------------------------------------------------------

    result = detector.detect(
        frame,
        preset=1,
    )


    assert result == []

    assert (
        len(
            fake_model.calls
        )
        == 1
    )


    call = (
        fake_model.calls[0]
    )


    # --------------------------------------------------------
    # CRITICAL:
    # ต้องเป็น Frame object เดิม
    #
    # ป้องกัน:
    # - manual resize
    # - manual RGB conversion
    # - manual normalization
    # - manual tensor conversion
    # --------------------------------------------------------

    assert (
        call["source"]
        is frame
    )


    # --------------------------------------------------------
    # Exact Final R3-E6 Contract
    # --------------------------------------------------------

    assert (
        call["imgsz"]
        == 768
    )

    assert (
        call["conf"]
        == 0.25
    )

    assert (
        call["iou"]
        == 0.70
    )

    assert (
        call["max_det"]
        == 300
    )

    assert (
        call["rect"]
        is False
    )

    assert (
        call["device"]
        == "cpu"
    )

    assert (
        call["verbose"]
        is False
    )


    # --------------------------------------------------------
    # Effective batch = 1
    #
    # detection.py ส่ง Single Numpy Image
    # จึงไม่ต้องส่ง batch= เข้า predict()
    # --------------------------------------------------------

    assert (
        "batch"
        not in call
    )


# ============================================================
# Test 3
# Detect -> Detection -> 2/3 Consensus
# ============================================================

def test_detect_to_consensus_two_of_three_pipeline(
    monkeypatch,
):

    # --------------------------------------------------------
    # Integration test นี้ไม่ใช้ Distance Calibration
    # --------------------------------------------------------

    monkeypatch.setattr(
        detection,
        "load_distance_model",
        lambda preset: None,
    )


    # --------------------------------------------------------
    # Frame 1:
    # fire confidence 0.61
    #
    # Frame 2:
    # same fire confidence 0.92
    #
    # Frame 3:
    # no detection
    #
    # Final expected:
    # 2/3 consensus = confirmed
    # representative = confidence 0.92
    # --------------------------------------------------------

    fake_model = RecordingModel(
        [
            make_fire_result(
                confidence=0.61,
                bbox=(
                    300,
                    200,
                    500,
                    500,
                ),
            ),

            make_fire_result(
                confidence=0.92,
                bbox=(
                    310,
                    205,
                    510,
                    505,
                ),
            ),

            make_empty_result(),
        ]
    )


    detector = make_detector(
        fake_model
    )


    frames = [
        make_frame(),
        make_frame(),
        make_frame(),
    ]


    detection_sets = []


    for frame in frames:

        current = detector.detect(
            frame,
            preset=1,
        )

        detection_sets.append(
            current
        )


    # --------------------------------------------------------
    # ตรวจ Candidate Detection ก่อน
    # --------------------------------------------------------

    assert (
        len(
            detection_sets[0]
        )
        == 1
    )

    assert (
        len(
            detection_sets[1]
        )
        == 1
    )

    assert (
        len(
            detection_sets[2]
        )
        == 0
    )


    first = (
        detection_sets[0][0]
    )

    second = (
        detection_sets[1][0]
    )


    assert (
        first.canonical_class
        == "fire"
    )

    assert (
        second.canonical_class
        == "fire"
    )


    assert (
        first.model_class
        == "fire"
    )

    assert (
        second.model_class
        == "fire"
    )


    # --------------------------------------------------------
    # ไม่มี Distance Calibration
    #
    # ต้องไม่สร้างค่าระยะ / GPS ปลอม
    # --------------------------------------------------------

    assert (
        first.distance_m
        is None
    )

    assert (
        first.gps
        is None
    )

    assert (
        first.distance_quality
        == "unavailable"
    )


    # --------------------------------------------------------
    # Multi-frame Consensus
    # --------------------------------------------------------

    confirmed = detection.consensus(
        detection_sets,
        min_frames=(
            config.MIN_CONFIRM_FRAMES
        ),
        iou_threshold=(
            config.CONSENSUS_IOU_THRESHOLD
        ),
    )


    # --------------------------------------------------------
    # 2 of 3 frames -> Confirmed
    # --------------------------------------------------------

    assert (
        len(
            confirmed
        )
        == 1
    )


    final_detection = (
        confirmed[0]
    )


    assert (
        final_detection.canonical_class
        == "fire"
    )


    # --------------------------------------------------------
    # consensus() ใช้ Detection ที่ confidence สูงสุด
    # เป็น Representative
    # --------------------------------------------------------

    assert np.isclose(
        final_detection.confidence,
        0.92,
        atol=1e-6,
    )


    # --------------------------------------------------------
    # ทุก inference call ต้องใช้ Contract เดียวกัน
    # --------------------------------------------------------

    assert (
        len(
            fake_model.calls
        )
        == 3
    )


    for index, call in enumerate(
        fake_model.calls
    ):

        assert (
            call["source"]
            is frames[index]
        )

        assert (
            call["imgsz"]
            == config.IMGSZ
        )

        assert (
            call["conf"]
            == 0.25
        )

        assert (
            call["iou"]
            == config.MODEL_NMS_IOU
        )

        assert (
            call["max_det"]
            == config.MODEL_MAX_DET
        )

        assert (
            call["rect"]
            is config.MODEL_RECT
        )

        assert (
            call["device"]
            == config.INFERENCE_DEVICE
        )

        assert (
            call["verbose"]
            is False
        )
#!/usr/bin/env python3
# tests/test_config_runtime.py

"""
Smart Fire Detection v2
Config Runtime Automated Tests

หน้าที่:
- ทดสอบ Environment helper functions
- ทดสอบ Runtime configuration validation
- ทดสอบ Import-time validation
- ป้องกัน Configuration regression

ไฟล์นี้:
- ไม่เปิดกล้อง
- ไม่สั่ง PTZ
- ไม่โหลด AI model
- ไม่เชื่อม Telegram
- ไม่แก้ไฟล์ Calibration จริง
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import config


# ============================================================
# Environment helper tests
# ============================================================

def test_env_text_strips_whitespace(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_TEXT",
        "   hello world   ",
    )

    assert (
        config.env_text(
            "TEST_CONFIG_TEXT",
            "",
        )
        == "hello world"
    )


def test_env_text_uses_default(
    monkeypatch,
):

    monkeypatch.delenv(
        "TEST_CONFIG_TEXT",
        raising=False,
    )

    assert (
        config.env_text(
            "TEST_CONFIG_TEXT",
            "default-value",
        )
        == "default-value"
    )


def test_env_int_valid(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_INT",
        "123",
    )

    assert (
        config.env_int(
            "TEST_CONFIG_INT",
            0,
        )
        == 123
    )


def test_env_int_invalid_raises_config_error(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_INT",
        "not-an-integer",
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.env_int(
            "TEST_CONFIG_INT",
            0,
        )


def test_env_float_valid(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_FLOAT",
        "12.75",
    )

    assert (
        config.env_float(
            "TEST_CONFIG_FLOAT",
            0.0,
        )
        == pytest.approx(
            12.75
        )
    )


def test_env_float_invalid_raises_config_error(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_FLOAT",
        "not-a-float",
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.env_float(
            "TEST_CONFIG_FLOAT",
            0.0,
        )


# ============================================================
# Boolean helper
# ============================================================

@pytest.mark.parametrize(
    "raw_value",
    [
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
        "on",
        "ON",
    ],
)
def test_env_bool_true_values(
    monkeypatch,
    raw_value,
):

    monkeypatch.setenv(
        "TEST_CONFIG_BOOL",
        raw_value,
    )

    assert (
        config.env_bool(
            "TEST_CONFIG_BOOL",
            False,
        )
        is True
    )


@pytest.mark.parametrize(
    "raw_value",
    [
        "0",
        "false",
        "FALSE",
        "no",
        "NO",
        "off",
        "OFF",
    ],
)
def test_env_bool_false_values(
    monkeypatch,
    raw_value,
):

    monkeypatch.setenv(
        "TEST_CONFIG_BOOL",
        raw_value,
    )

    assert (
        config.env_bool(
            "TEST_CONFIG_BOOL",
            True,
        )
        is False
    )


def test_env_bool_default(
    monkeypatch,
):

    monkeypatch.delenv(
        "TEST_CONFIG_BOOL",
        raising=False,
    )

    assert (
        config.env_bool(
            "TEST_CONFIG_BOOL",
            True,
        )
        is True
    )


def test_env_bool_invalid_raises_config_error(
    monkeypatch,
):

    monkeypatch.setenv(
        "TEST_CONFIG_BOOL",
        "maybe",
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.env_bool(
            "TEST_CONFIG_BOOL",
            True,
        )


# ============================================================
# Path helper
# ============================================================

def test_env_path_relative_to_project(
    monkeypatch,
):

    relative = (
        "test-runtime-output"
    )

    monkeypatch.setenv(
        "TEST_CONFIG_PATH",
        relative,
    )

    result = config.env_path(
        "TEST_CONFIG_PATH",
        "unused",
    )

    expected = (
        config.BASE_DIR
        / relative
    )

    assert (
        result.resolve()
        == expected.resolve()
    )


def test_env_path_absolute_preserved(
    monkeypatch,
    tmp_path,
):

    monkeypatch.setenv(
        "TEST_CONFIG_PATH",
        str(
            tmp_path
        ),
    )

    result = config.env_path(
        "TEST_CONFIG_PATH",
        "unused",
    )

    assert (
        result.resolve()
        == tmp_path.resolve()
    )


# ============================================================
# Baseline Runtime Validation
# ============================================================

def test_runtime_config_baseline_is_valid():

    # Current default/development configuration
    # ต้องผ่าน validator

    config.validate_runtime_config()


# ============================================================
# Frame / Consensus validation
# ============================================================

def test_min_confirm_frames_cannot_exceed_frames_per_scan(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "FRAMES_PER_SCAN",
        3,
    )

    monkeypatch.setattr(
        config,
        "MIN_CONFIRM_FRAMES",
        4,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_frames_per_scan_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "FRAMES_PER_SCAN",
        0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_frame_sample_gap_cannot_be_negative(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "FRAME_SAMPLE_GAP_SEC",
        -0.1,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Detection Threshold validation
# ============================================================

def test_fire_threshold_above_one_is_invalid(
    monkeypatch,
):

    thresholds = dict(
        config.CLASS_THRESHOLDS
    )

    thresholds[
        "fire"
    ] = 1.1

    monkeypatch.setattr(
        config,
        "CLASS_THRESHOLDS",
        thresholds,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_smoke_threshold_below_zero_is_invalid(
    monkeypatch,
):

    thresholds = dict(
        config.CLASS_THRESHOLDS
    )

    thresholds[
        "smoke"
    ] = -0.1

    monkeypatch.setattr(
        config,
        "CLASS_THRESHOLDS",
        thresholds,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Consensus IoU
# ============================================================

@pytest.mark.parametrize(
    "value",
    [
        -0.01,
        1.01,
    ],
)
def test_consensus_iou_out_of_range_is_invalid(
    monkeypatch,
    value,
):

    monkeypatch.setattr(
        config,
        "CONSENSUS_IOU_THRESHOLD",
        value,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        0.30,
        0.50,
        1.0,
    ],
)
def test_consensus_iou_valid_range(
    monkeypatch,
    value,
):

    monkeypatch.setattr(
        config,
        "CONSENSUS_IOU_THRESHOLD",
        value,
    )

    config.validate_runtime_config()


# ============================================================
# Alert Dedup IoU
# ============================================================

@pytest.mark.parametrize(
    "value",
    [
        -0.01,
        1.01,
    ],
)
def test_alert_dedup_iou_out_of_range_is_invalid(
    monkeypatch,
    value,
):

    monkeypatch.setattr(
        config,
        "ALERT_DEDUP_IOU_THRESHOLD",
        value,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        0.50,
        1.0,
    ],
)
def test_alert_dedup_iou_valid_range(
    monkeypatch,
    value,
):

    monkeypatch.setattr(
        config,
        "ALERT_DEDUP_IOU_THRESHOLD",
        value,
    )

    config.validate_runtime_config()


# ============================================================
# Alert Cooldown
# ============================================================

def test_alert_cooldown_cannot_be_negative(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "ALERT_COOLDOWN_SEC",
        -1.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_zero_alert_cooldown_is_valid(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "ALERT_COOLDOWN_SEC",
        0.0,
    )

    config.validate_runtime_config()


# ============================================================
# Startup Warm-up
# ============================================================

def test_startup_warmup_cannot_be_negative(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "STARTUP_WARMUP_RUNS",
        -1,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_zero_startup_warmup_is_valid(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "STARTUP_WARMUP_RUNS",
        0,
    )

    config.validate_runtime_config()


# ============================================================
# AI Backend / Device
# ============================================================

def test_invalid_model_backend_is_rejected(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "MODEL_BACKEND",
        "invalid-backend",
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    "backend",
    [
        "pt",
        "openvino",
    ],
)
def test_supported_model_backends_are_valid(
    monkeypatch,
    backend,
):

    monkeypatch.setattr(
        config,
        "MODEL_BACKEND",
        backend,
    )

    config.validate_runtime_config()


def test_empty_inference_device_is_rejected(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "INFERENCE_DEVICE",
        "",
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Image size
# ============================================================

def test_imgsz_too_small_is_invalid(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "IMGSZ",
        31,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_imgsz_32_is_valid(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "IMGSZ",
        32,
    )

    config.validate_runtime_config()


# ============================================================
# Frame Resolution / HFOV
# ============================================================

@pytest.mark.parametrize(
    (
        "width",
        "height",
    ),
    [
        (
            0,
            720,
        ),
        (
            1280,
            0,
        ),
        (
            -1,
            720,
        ),
        (
            1280,
            -1,
        ),
    ],
)
def test_invalid_frame_resolution_is_rejected(
    monkeypatch,
    width,
    height,
):

    monkeypatch.setattr(
        config,
        "FRAME_WIDTH",
        width,
    )

    monkeypatch.setattr(
        config,
        "FRAME_HEIGHT",
        height,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    "hfov",
    [
        0.0,
        -1.0,
        180.0,
        181.0,
    ],
)
def test_invalid_hfov_is_rejected(
    monkeypatch,
    hfov,
):

    monkeypatch.setattr(
        config,
        "HFOV_DEG",
        hfov,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Network Port validation
# ============================================================

@pytest.mark.parametrize(
    "port",
    [
        0,
        -1,
        65536,
    ],
)
def test_invalid_camera_port_is_rejected(
    monkeypatch,
    port,
):

    monkeypatch.setattr(
        config,
        "CAMERA_PORT",
        port,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    "port",
    [
        0,
        -1,
        65536,
    ],
)
def test_invalid_rtsp_port_is_rejected(
    monkeypatch,
    port,
):

    monkeypatch.setattr(
        config,
        "RTSP_PORT",
        port,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# PTZ Presets
# ============================================================

def test_preset_pan_and_bearing_ids_must_match(
    monkeypatch,
):

    bad_pan = dict(
        config.PRESET_PAN_DEG
    )

    preset_to_remove = next(
        iter(
            bad_pan
        )
    )

    bad_pan.pop(
        preset_to_remove
    )

    monkeypatch.setattr(
        config,
        "PRESET_PAN_DEG",
        bad_pan,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_sweep_cannot_reference_unknown_preset(
    monkeypatch,
):

    bad_sweep = list(
        config.SWEEP_SEQUENCE
    )

    bad_sweep.append(
        999
    )

    monkeypatch.setattr(
        config,
        "SWEEP_SEQUENCE",
        bad_sweep,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# PTZ / Stability timing
# ============================================================

def test_ptz_speed_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "DEG_PER_SEC",
        0.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_ptz_buffer_cannot_be_negative(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "PTZ_BUFFER_SEC",
        -0.1,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_stable_required_pairs_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "STABLE_REQUIRED_PAIRS",
        0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_stable_timeout_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "STABLE_TIMEOUT_SEC",
        0.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_post_move_fresh_frames_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "POST_MOVE_FRESH_FRAMES",
        0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Distance Range
# ============================================================

def test_min_distance_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "MIN_VALID_DISTANCE_M",
        0.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_max_distance_must_exceed_min_distance(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "MIN_VALID_DISTANCE_M",
        10.0,
    )

    monkeypatch.setattr(
        config,
        "MAX_VALID_DISTANCE_M",
        10.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# GPS Validation
# ============================================================

def test_both_nan_camera_coordinates_are_allowed(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "CAMERA_LAT",
        float(
            "nan"
        ),
    )

    monkeypatch.setattr(
        config,
        "CAMERA_LON",
        float(
            "nan"
        ),
    )

    config.validate_runtime_config()


def test_mixed_nan_camera_coordinates_are_invalid(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "CAMERA_LAT",
        float(
            "nan"
        ),
    )

    monkeypatch.setattr(
        config,
        "CAMERA_LON",
        98.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


@pytest.mark.parametrize(
    (
        "lat",
        "lon",
    ),
    [
        (
            91.0,
            98.0,
        ),
        (
            -91.0,
            98.0,
        ),
        (
            18.0,
            181.0,
        ),
        (
            18.0,
            -181.0,
        ),
    ],
)
def test_camera_coordinates_out_of_range_are_invalid(
    monkeypatch,
    lat,
    lon,
):

    monkeypatch.setattr(
        config,
        "CAMERA_LAT",
        lat,
    )

    monkeypatch.setattr(
        config,
        "CAMERA_LON",
        lon,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


def test_valid_camera_coordinates_are_allowed(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "CAMERA_LAT",
        18.0,
    )

    monkeypatch.setattr(
        config,
        "CAMERA_LON",
        98.0,
    )

    config.validate_runtime_config()


# ============================================================
# Dashboard
# ============================================================

def test_dashboard_write_interval_must_be_positive(
    monkeypatch,
):

    monkeypatch.setattr(
        config,
        "DASHBOARD_WRITE_INTERVAL_SEC",
        0.0,
    )

    with pytest.raises(
        config.ConfigError
    ):

        config.validate_runtime_config()


# ============================================================
# Import-time validation helpers
# ============================================================

def run_config_import_with_env(
    variable,
    value,
):
    """
    Import config.py in a new Python process.

    ใช้ subprocess เพื่อไม่ให้ Environment ที่ผิด
    ทำให้ config module ของ pytest process เสียสถานะ
    """

    env = os.environ.copy()

    env[
        variable
    ] = value

    command = [
        sys.executable,
        "-c",
        "import config",
    ]

    return subprocess.run(
        command,
        cwd=str(
            config.BASE_DIR
        ),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )


# ============================================================
# Import-time malformed Environment tests
# ============================================================

def test_import_rejects_invalid_integer_environment():

    result = (
        run_config_import_with_env(
            "IMGSZ",
            "abc",
        )
    )

    combined = (
        result.stdout
        + result.stderr
    )

    assert (
        result.returncode
        != 0
    )

    assert (
        "IMGSZ"
        in combined
    )

    assert (
        "Invalid integer"
        in combined
    )


def test_import_rejects_invalid_boolean_environment():

    result = (
        run_config_import_with_env(
            "HEADLESS_MODE",
            "abc",
        )
    )

    combined = (
        result.stdout
        + result.stderr
    )

    assert (
        result.returncode
        != 0
    )

    assert (
        "HEADLESS_MODE"
        in combined
    )

    assert (
        "Invalid boolean"
        in combined
    )


def test_import_rejects_consensus_iou_above_one():

    result = (
        run_config_import_with_env(
            "CONSENSUS_IOU_THRESHOLD",
            "2",
        )
    )

    combined = (
        result.stdout
        + result.stderr
    )

    assert (
        result.returncode
        != 0
    )

    assert (
        "CONSENSUS_IOU_THRESHOLD"
        in combined
    )


def test_import_accepts_valid_warmup_override():

    result = (
        run_config_import_with_env(
            "STARTUP_WARMUP_RUNS",
            "7",
        )
    )

    assert (
        result.returncode
        == 0
    ), (
        result.stdout
        + result.stderr
    )
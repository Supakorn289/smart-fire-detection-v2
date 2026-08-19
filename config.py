#!/usr/bin/env python3
# config.py

"""
Smart Fire Detection v2
Central Runtime Configuration

Final AI Model Integration:
    Release : R3-E6
    Status  : Frozen

หน้าที่:
- เป็น Single Source of Truth ของ Runtime Configuration
- อ่าน Environment Variables อย่างปลอดภัย
- ตรวจรูปแบบและช่วงของ Configuration
- เก็บ Final AI Model Contract
- รองรับ Production Preflight

หมายเหตุ:
- config.py ไม่โหลด YOLO model
- config.py ไม่คำนวณ SHA256 ของไฟล์จริง
- config.py ไม่เชื่อม Camera / Telegram
- Production artifact/model validation เป็นหน้าที่ของ preflight.py
"""

import math
import os
from pathlib import Path


# ============================================================
# Project
# ============================================================

BASE_DIR = Path(
    __file__
).resolve().parent


# ============================================================
# Environment helpers
# ============================================================

class ConfigError(ValueError):
    """
    Configuration มีค่าผิดรูปแบบ
    หรือไม่อยู่ในช่วงที่ระบบรองรับ
    """


def env_text(
    name,
    default="",
):
    """
    อ่าน Environment Variable แบบข้อความ

    ใช้ strip() กับค่าทั่วไป

    Password ที่ whitespace อาจมีความหมาย
    ต้องใช้ os.getenv() โดยตรง
    """

    value = os.getenv(
        name,
        default,
    )

    if value is None:
        value = ""

    return str(
        value
    ).strip()


def env_int(
    name,
    default,
):
    """
    อ่าน Environment Variable แบบ Integer
    """

    raw = os.getenv(
        name,
        str(default),
    )

    try:
        return int(
            str(raw).strip()
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise ConfigError(
            f"Invalid integer environment variable "
            f"{name}={raw!r}"
        ) from exc


def env_float(
    name,
    default,
):
    """
    อ่าน Environment Variable แบบ Float

    รองรับ nan โดยตั้งใจ
    สำหรับ CAMERA_LAT / CAMERA_LON
    ก่อนกำหนด Production Site
    """

    raw = os.getenv(
        name,
        str(default),
    )

    try:
        return float(
            str(raw).strip()
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise ConfigError(
            f"Invalid float environment variable "
            f"{name}={raw!r}"
        ) from exc


def env_bool(
    name,
    default=False,
):
    """
    Boolean values:

    True:
        1
        true
        yes
        on

    False:
        0
        false
        no
        off
    """

    default_text = (
        "1"
        if default
        else "0"
    )

    raw = env_text(
        name,
        default_text,
    ).lower()

    if raw in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if raw in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ConfigError(
        f"Invalid boolean environment variable "
        f"{name}={raw!r}; expected one of "
        f"1/0, true/false, yes/no, on/off"
    )


def env_path(
    name,
    default,
):
    """
    อ่าน Path จาก Environment

    Relative path จะ Resolve จาก BASE_DIR
    ไม่ใช่ Current Working Directory
    """

    raw = env_text(
        name,
        str(default),
    )

    path = Path(
        raw
    ).expanduser()

    if not path.is_absolute():
        path = (
            BASE_DIR
            / path
        )

    return path.resolve()


# ============================================================
# Camera / RTSP
# ============================================================

CAMERA_IP = env_text(
    "CAMERA_IP"
)

CAMERA_PORT = env_int(
    "CAMERA_PORT",
    81,
)

CAMERA_USER = env_text(
    "CAMERA_USER"
)

# Password ไม่ strip()
CAMERA_PWD = os.getenv(
    "CAMERA_PWD",
    "",
)

RTSP_PORT = env_int(
    "RTSP_PORT",
    10554,
)

RTSP_PATH = env_text(
    "RTSP_PATH",
    "/tcp/av0_0",
)


# ============================================================
# Camera ID / RTSP URL
# ============================================================

CAMERA_ID = env_text(
    "CAMERA_ID"
)

if not CAMERA_ID:

    if CAMERA_IP:

        CAMERA_ID = (
            f"rtsp://"
            f"{CAMERA_USER}:"
            f"{CAMERA_PWD}@"
            f"{CAMERA_IP}:"
            f"{RTSP_PORT}"
            f"{RTSP_PATH}"
        )

    else:

        # Development / Offline mode
        CAMERA_ID = ""


# ============================================================
# Camera frame
# ============================================================

FRAME_WIDTH = env_int(
    "FRAME_WIDTH",
    1280,
)

FRAME_HEIGHT = env_int(
    "FRAME_HEIGHT",
    720,
)


# ============================================================
# Camera Horizontal FOV
# ============================================================
#
# Camera Geometry
#
# หากเปลี่ยน:
#
# - Camera
# - Lens
# - Optical Zoom
# - Digital Crop
# - Resolution
#
# ต้องตรวจ Calibration ใหม่
#
# ============================================================

HFOV_DEG = env_float(
    "HFOV_DEG",
    60.195288,
)


# ============================================================
# PTZ
# ============================================================

# Physical pan coordinates
# -177.5 .. +177.5

PRESET_PAN_DEG = {
    1: 0.0,
    2: 45.0,
    3: 90.0,
    4: 135.0,
    5: 177.5,
    6: -45.0,
    7: -90.0,
    8: -135.0,
    9: -177.5,
}


# Compass azimuth
#
# 0   = North
# 90  = East
# 180 = South
# 270 = West

PRESET_BEARING_DEG = {
    1: 0.0,
    2: 45.0,
    3: 90.0,
    4: 135.0,
    5: 177.5,
    6: 315.0,
    7: 270.0,
    8: 225.0,
    9: 182.5,
}


# ============================================================
# PTZ Sweep
# ============================================================

SWEEP_SEQUENCE = [
    1,
    2,
    3,
    4,
    5,
    4,
    3,
    2,
    1,
    6,
    7,
    8,
    9,
    8,
    7,
    6,
    1,
]


# ============================================================
# PTZ / Frame synchronization
# ============================================================

DEG_PER_SEC = env_float(
    "DEG_PER_SEC",
    15.0,
)

PTZ_BUFFER_SEC = env_float(
    "PTZ_BUFFER_SEC",
    1.5,
)

INITIAL_PRESET_WAIT_SEC = env_float(
    "INITIAL_PRESET_WAIT_SEC",
    5.0,
)

STABLE_DIFF_THRESHOLD = env_float(
    "STABLE_DIFF_THRESHOLD",
    3.0,
)

STABLE_REQUIRED_PAIRS = env_int(
    "STABLE_REQUIRED_PAIRS",
    3,
)

STABLE_TIMEOUT_SEC = env_float(
    "STABLE_TIMEOUT_SEC",
    5.0,
)

POST_MOVE_FRESH_FRAMES = env_int(
    "POST_MOVE_FRESH_FRAMES",
    3,
)


# ============================================================
# FINAL AI MODEL CONTRACT
# R3-E6 RELEASE V1
# ============================================================
#
# Final Model เป็น Frozen Artifact
#
# ห้าม:
# - Train
# - Fine-tune
# - Quantize
# - Save checkpoint ใหม่แทน Master
# - เปลี่ยน class order
#
# ============================================================

FINAL_MODEL_RELEASE = (
    "R3-E6"
)

FINAL_MODEL_SOURCE_NAME = (
    "fire_smoke_r3_e6_final.pt"
)

FINAL_MODEL_MASTER_PATH = (
    BASE_DIR
    / "models"
    / "final"
    / FINAL_MODEL_SOURCE_NAME
).resolve()

FINAL_MODEL_RUNTIME_PATH = (
    BASE_DIR
    / "models"
    / "fire.pt"
).resolve()


# ------------------------------------------------------------
# Binary integrity
# ------------------------------------------------------------

EXPECTED_MODEL_SHA256 = (
    "49dc0464d99a6c250cf3c3e305d4149c"
    "3d4ce3ee354d9d7a5ae1cb8c53a22183"
)


# ------------------------------------------------------------
# Class Contract
# ------------------------------------------------------------
#
# Exact:
#   0 = fire
#   1 = smoke
#
# ------------------------------------------------------------

EXPECTED_MODEL_CLASSES = {
    0: "fire",
    1: "smoke",
}


# ------------------------------------------------------------
# Runtime reference versions
# ------------------------------------------------------------

EXPECTED_ULTRALYTICS_VERSION = (
    "8.4.95"
)

REFERENCE_PYTORCH_VERSION = (
    "2.11.0"
)

# Model Team ไม่มี authoritative exact torchvision version
# ห้ามเดา version แล้วถือเป็น Final Contract
REFERENCE_TORCHVISION_VERSION = None


# ============================================================
# AI Backend
# ============================================================

MODEL_BACKEND = (
    env_text(
        "MODEL_BACKEND",
        "pt",
    )
    .lower()
)


MODEL_PATH_PT = str(
    env_path(
        "MODEL_PATH_PT",
        FINAL_MODEL_RUNTIME_PATH,
    )
)


MODEL_PATH_OPENVINO = str(
    env_path(
        "MODEL_PATH_OPENVINO",
        (
            BASE_DIR
            / "models"
            / "fire_openvino_model"
        ),
    )
)


INFERENCE_DEVICE = env_text(
    "INFERENCE_DEVICE",
    "cpu",
)


# ============================================================
# Final Model Inference Contract
# ============================================================
#
# YOLO.predict() High-Level API:
#
# source   = raw OpenCV BGR frame
# imgsz    = 768
# conf     = 0.25
# iou      = 0.70
# max_det  = 300
# rect     = False
# batch    = 1
#
# ห้ามทำ manual preprocessing ก่อน YOLO.predict()
#
# ============================================================

IMGSZ = env_int(
    "IMGSZ",
    768,
)

MODEL_NMS_IOU = env_float(
    "MODEL_NMS_IOU",
    0.70,
)

MODEL_MAX_DET = env_int(
    "MODEL_MAX_DET",
    300,
)

MODEL_RECT = env_bool(
    "MODEL_RECT",
    False,
)

MODEL_BATCH = env_int(
    "MODEL_BATCH",
    1,
)


# ============================================================
# AI Startup
# ============================================================

STARTUP_WARMUP_RUNS = env_int(
    "STARTUP_WARMUP_RUNS",
    3,
)


# ============================================================
# Detection / Candidate Detection
# ============================================================
#
# 0.25 = MODEL CANDIDATE THRESHOLD
#
# ไม่ใช่ Final Alert Threshold
#
# Candidate
#      ↓
# Multi-frame Consensus
#      ↓
# Confirmed Detection
#      ↓
# Alert Dedup
#      ↓
# Notification
#
# ============================================================

FRAMES_PER_SCAN = env_int(
    "FRAMES_PER_SCAN",
    3,
)

MIN_CONFIRM_FRAMES = env_int(
    "MIN_CONFIRM_FRAMES",
    2,
)

FRAME_SAMPLE_GAP_SEC = env_float(
    "FRAME_SAMPLE_GAP_SEC",
    0.15,
)


CLASS_THRESHOLDS = {

    "fire": env_float(
        "FIRE_THRESHOLD",
        0.25,
    ),

    "smoke": env_float(
        "SMOKE_THRESHOLD",
        0.25,
    ),
}


CLASS_ALIASES = {

    "fire": {
        "fire",
        "flame",
        "flames",
    },

    "smoke": {
        "smoke",
        "smokes",
        "fire-smoke",
        "firesmoke",
    },
}


# ============================================================
# Consensus
# ============================================================
#
# KEEP:
#
# Frames          = 3
# Confirm         = 2
# Consensus IoU   = 0.30
#
# ============================================================

CONSENSUS_IOU_THRESHOLD = env_float(
    "CONSENSUS_IOU_THRESHOLD",
    0.30,
)


# ============================================================
# Calibration
# ============================================================

CALIBRATION_DIR = env_path(
    "CALIBRATION_DIR",
    (
        BASE_DIR
        / "calibration"
    ),
)


GLOBAL_DISTANCE_CALIBRATION = (
    CALIBRATION_DIR
    / "distance_global.json"
)


SITE_CALIBRATION_FILE = (
    CALIBRATION_DIR
    / "site.json"
)


MIN_VALID_DISTANCE_M = env_float(
    "MIN_VALID_DISTANCE_M",
    1.0,
)

MAX_VALID_DISTANCE_M = env_float(
    "MAX_VALID_DISTANCE_M",
    200.0,
)


# ============================================================
# Camera Site Coordinates
# ============================================================
#
# Development:
#
# CAMERA_LAT=nan
# CAMERA_LON=nan
#
# Production:
#
# ต้องเป็นตัวเลขจริงทั้งคู่
#
# ============================================================

CAMERA_LAT = env_float(
    "CAMERA_LAT",
    "nan",
)

CAMERA_LON = env_float(
    "CAMERA_LON",
    "nan",
)


# ============================================================
# Telegram
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "",
)

TELEGRAM_CHAT_ID = env_text(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# Alert
# ============================================================

ALERT_COOLDOWN_SEC = env_float(
    "ALERT_COOLDOWN_SEC",
    30,
)

ALERT_DEDUP_IOU_THRESHOLD = env_float(
    "ALERT_DEDUP_IOU_THRESHOLD",
    0.50,
)


# ============================================================
# Output / Dashboard
# ============================================================

STATIC_DIR = env_path(
    "STATIC_DIR",
    (
        BASE_DIR
        / "static"
    ),
)


DASHBOARD_WRITE_INTERVAL_SEC = env_float(
    "DASHBOARD_WRITE_INTERVAL_SEC",
    1.0,
)


# ============================================================
# Server
# ============================================================

HEADLESS_MODE = env_bool(
    "HEADLESS_MODE",
    True,
)


# ============================================================
# Internal validation helper
# ============================================================

def _require_config(
    condition,
    message,
):
    """
    Raise ConfigError หาก Condition ไม่ผ่าน
    """

    if not condition:

        raise ConfigError(
            message
        )


# ============================================================
# Generic Runtime Configuration Validation
# ============================================================

def validate_runtime_config():
    """
    ตรวจรูปแบบ ช่วงค่า และความสัมพันธ์ของ Runtime Configuration

    ฟังก์ชันนี้ไม่ได้:
    - โหลด Model
    - ตรวจ Model SHA256 จริง
    - ตรวจ model.names จริง
    - เชื่อม Camera
    - เชื่อม Telegram
    - ตรวจ Calibration Production

    Production readiness เป็นหน้าที่ของ preflight.py
    """

    # ========================================================
    # Network ports
    # ========================================================

    _require_config(
        1
        <= CAMERA_PORT
        <= 65535,
        (
            "CAMERA_PORT must be between "
            "1 and 65535"
        ),
    )

    _require_config(
        1
        <= RTSP_PORT
        <= 65535,
        (
            "RTSP_PORT must be between "
            "1 and 65535"
        ),
    )


    # ========================================================
    # Camera frame geometry
    # ========================================================

    _require_config(
        FRAME_WIDTH > 0,
        "FRAME_WIDTH must be > 0",
    )

    _require_config(
        FRAME_HEIGHT > 0,
        "FRAME_HEIGHT must be > 0",
    )

    _require_config(
        (
            math.isfinite(
                HFOV_DEG
            )
            and
            0.0
            < HFOV_DEG
            < 180.0
        ),
        (
            "HFOV_DEG must be between "
            "0 and 180 degrees"
        ),
    )


    # ========================================================
    # PTZ preset consistency
    # ========================================================

    _require_config(
        (
            set(
                PRESET_PAN_DEG
            )
            ==
            set(
                PRESET_BEARING_DEG
            )
        ),
        (
            "PRESET_PAN_DEG and "
            "PRESET_BEARING_DEG must contain "
            "the same preset IDs"
        ),
    )

    _require_config(
        all(
            preset
            in PRESET_PAN_DEG
            for preset
            in SWEEP_SEQUENCE
        ),
        (
            "SWEEP_SEQUENCE contains "
            "an unknown preset"
        ),
    )


    # ========================================================
    # PTZ / Frame synchronization
    # ========================================================

    _require_config(
        (
            math.isfinite(
                DEG_PER_SEC
            )
            and
            DEG_PER_SEC > 0.0
        ),
        "DEG_PER_SEC must be > 0",
    )

    _require_config(
        (
            math.isfinite(
                PTZ_BUFFER_SEC
            )
            and
            PTZ_BUFFER_SEC >= 0.0
        ),
        "PTZ_BUFFER_SEC must be >= 0",
    )

    _require_config(
        (
            math.isfinite(
                INITIAL_PRESET_WAIT_SEC
            )
            and
            INITIAL_PRESET_WAIT_SEC >= 0.0
        ),
        (
            "INITIAL_PRESET_WAIT_SEC "
            "must be >= 0"
        ),
    )

    _require_config(
        (
            math.isfinite(
                STABLE_DIFF_THRESHOLD
            )
            and
            STABLE_DIFF_THRESHOLD >= 0.0
        ),
        (
            "STABLE_DIFF_THRESHOLD "
            "must be >= 0"
        ),
    )

    _require_config(
        STABLE_REQUIRED_PAIRS >= 1,
        (
            "STABLE_REQUIRED_PAIRS "
            "must be >= 1"
        ),
    )

    _require_config(
        (
            math.isfinite(
                STABLE_TIMEOUT_SEC
            )
            and
            STABLE_TIMEOUT_SEC > 0.0
        ),
        (
            "STABLE_TIMEOUT_SEC "
            "must be > 0"
        ),
    )

    _require_config(
        POST_MOVE_FRESH_FRAMES >= 1,
        (
            "POST_MOVE_FRESH_FRAMES "
            "must be >= 1"
        ),
    )


    # ========================================================
    # AI Backend
    # ========================================================

    _require_config(
        MODEL_BACKEND
        in {
            "pt",
            "openvino",
        },
        (
            "MODEL_BACKEND must be "
            "'pt' or 'openvino'"
        ),
    )

    _require_config(
        bool(
            INFERENCE_DEVICE
        ),
        (
            "INFERENCE_DEVICE "
            "must not be empty"
        ),
    )

    _require_config(
        IMGSZ >= 32,
        (
            "IMGSZ must be >= 32"
        ),
    )

    _require_config(
        (
            math.isfinite(
                MODEL_NMS_IOU
            )
            and
            0.0
            <= MODEL_NMS_IOU
            <= 1.0
        ),
        (
            "MODEL_NMS_IOU must be "
            "between 0 and 1"
        ),
    )

    _require_config(
        MODEL_MAX_DET >= 1,
        (
            "MODEL_MAX_DET "
            "must be >= 1"
        ),
    )

    _require_config(
        MODEL_BATCH >= 1,
        (
            "MODEL_BATCH "
            "must be >= 1"
        ),
    )

    _require_config(
        isinstance(
            MODEL_RECT,
            bool,
        ),
        (
            "MODEL_RECT "
            "must be boolean"
        ),
    )

    _require_config(
        STARTUP_WARMUP_RUNS >= 0,
        (
            "STARTUP_WARMUP_RUNS "
            "must be >= 0"
        ),
    )


    # ========================================================
    # Multi-frame detection
    # ========================================================

    _require_config(
        FRAMES_PER_SCAN >= 1,
        (
            "FRAMES_PER_SCAN "
            "must be >= 1"
        ),
    )

    _require_config(
        (
            1
            <= MIN_CONFIRM_FRAMES
            <= FRAMES_PER_SCAN
        ),
        (
            "MIN_CONFIRM_FRAMES must be "
            "between 1 and FRAMES_PER_SCAN"
        ),
    )

    _require_config(
        (
            math.isfinite(
                FRAME_SAMPLE_GAP_SEC
            )
            and
            FRAME_SAMPLE_GAP_SEC >= 0.0
        ),
        (
            "FRAME_SAMPLE_GAP_SEC "
            "must be >= 0"
        ),
    )


    # ========================================================
    # Detection thresholds
    # ========================================================

    _require_config(
        set(
            CLASS_THRESHOLDS
        )
        == {
            "fire",
            "smoke",
        },
        (
            "CLASS_THRESHOLDS must contain "
            "exactly fire and smoke"
        ),
    )

    for (
        class_name,
        threshold,
    ) in CLASS_THRESHOLDS.items():

        _require_config(
            (
                math.isfinite(
                    threshold
                )
                and
                0.0
                <= threshold
                <= 1.0
            ),
            (
                f"{class_name.upper()} "
                f"threshold must be "
                f"between 0 and 1"
            ),
        )


    # ========================================================
    # Consensus
    # ========================================================

    _require_config(
        (
            math.isfinite(
                CONSENSUS_IOU_THRESHOLD
            )
            and
            0.0
            <= CONSENSUS_IOU_THRESHOLD
            <= 1.0
        ),
        (
            "CONSENSUS_IOU_THRESHOLD "
            "must be between 0 and 1"
        ),
    )


    # ========================================================
    # Distance
    # ========================================================

    _require_config(
        (
            math.isfinite(
                MIN_VALID_DISTANCE_M
            )
            and
            MIN_VALID_DISTANCE_M > 0.0
        ),
        (
            "MIN_VALID_DISTANCE_M "
            "must be > 0"
        ),
    )

    _require_config(
        (
            math.isfinite(
                MAX_VALID_DISTANCE_M
            )
            and
            MAX_VALID_DISTANCE_M
            > MIN_VALID_DISTANCE_M
        ),
        (
            "MAX_VALID_DISTANCE_M must be "
            "greater than "
            "MIN_VALID_DISTANCE_M"
        ),
    )


    # ========================================================
    # Site coordinates
    # ========================================================

    lat_is_nan = math.isnan(
        CAMERA_LAT
    )

    lon_is_nan = math.isnan(
        CAMERA_LON
    )

    _require_config(
        lat_is_nan
        ==
        lon_is_nan,
        (
            "CAMERA_LAT and CAMERA_LON "
            "must either both be nan or "
            "both contain numeric coordinates"
        ),
    )

    if not lat_is_nan:

        _require_config(
            (
                math.isfinite(
                    CAMERA_LAT
                )
                and
                -90.0
                <= CAMERA_LAT
                <= 90.0
            ),
            (
                "CAMERA_LAT must be "
                "between -90 and 90"
            ),
        )

        _require_config(
            (
                math.isfinite(
                    CAMERA_LON
                )
                and
                -180.0
                <= CAMERA_LON
                <= 180.0
            ),
            (
                "CAMERA_LON must be "
                "between -180 and 180"
            ),
        )


    # ========================================================
    # Alert
    # ========================================================

    _require_config(
        (
            math.isfinite(
                ALERT_COOLDOWN_SEC
            )
            and
            ALERT_COOLDOWN_SEC >= 0.0
        ),
        (
            "ALERT_COOLDOWN_SEC "
            "must be >= 0"
        ),
    )

    _require_config(
        (
            math.isfinite(
                ALERT_DEDUP_IOU_THRESHOLD
            )
            and
            0.0
            <= ALERT_DEDUP_IOU_THRESHOLD
            <= 1.0
        ),
        (
            "ALERT_DEDUP_IOU_THRESHOLD "
            "must be between 0 and 1"
        ),
    )


    # ========================================================
    # Dashboard
    # ========================================================

    _require_config(
        (
            math.isfinite(
                DASHBOARD_WRITE_INTERVAL_SEC
            )
            and
            DASHBOARD_WRITE_INTERVAL_SEC > 0.0
        ),
        (
            "DASHBOARD_WRITE_INTERVAL_SEC "
            "must be > 0"
        ),
    )


    # ========================================================
    # Static Model Contract metadata sanity
    # ========================================================

    _require_config(
        (
            len(
                EXPECTED_MODEL_SHA256
            )
            == 64
            and
            all(
                char
                in "0123456789abcdef"
                for char
                in EXPECTED_MODEL_SHA256.lower()
            )
        ),
        (
            "EXPECTED_MODEL_SHA256 "
            "must contain exactly "
            "64 hexadecimal characters"
        ),
    )

    _require_config(
        EXPECTED_MODEL_CLASSES
        == {
            0: "fire",
            1: "smoke",
        },
        (
            "EXPECTED_MODEL_CLASSES "
            "must be exactly "
            "{0: 'fire', 1: 'smoke'}"
        ),
    )

    _require_config(
        bool(
            EXPECTED_ULTRALYTICS_VERSION
        ),
        (
            "EXPECTED_ULTRALYTICS_VERSION "
            "must not be empty"
        ),
    )


# ============================================================
# FINAL R3-E6 MODEL CONTRACT VALIDATION
# ============================================================

def validate_final_model_contract():
    """
    ตรวจว่า Software Configuration
    ตรง Final AI Model R3-E6 Release V1

    ฟังก์ชันนี้ตรวจ Operating Point เท่านั้น

    ยังไม่ตรวจ:
    - SHA256 ของไฟล์จริง
    - model.names จริง
    - installed package version จริง

    สิ่งเหล่านั้นต้องตรวจใน preflight.py
    """

    validate_runtime_config()


    # ========================================================
    # Approved Production Backend
    # ========================================================

    _require_config(
        MODEL_BACKEND == "pt",
        (
            "Final R3-E6 Release V1 requires "
            "MODEL_BACKEND=pt; "
            "OpenVINO is not Production-approved yet"
        ),
    )

    _require_config(
        INFERENCE_DEVICE
        .strip()
        .lower()
        == "cpu",
        (
            "Final R3-E6 Production baseline requires "
            "INFERENCE_DEVICE=cpu"
        ),
    )


    # ========================================================
    # Runtime Model Path
    # ========================================================

    _require_config(
        Path(
            MODEL_PATH_PT
        ).resolve()
        ==
        FINAL_MODEL_RUNTIME_PATH,
        (
            "Final R3-E6 Runtime Model must be "
            f"{FINAL_MODEL_RUNTIME_PATH}"
        ),
    )


    # ========================================================
    # Model inference contract
    # ========================================================

    _require_config(
        IMGSZ == 768,
        (
            "Final R3-E6 requires "
            "IMGSZ=768"
        ),
    )

    _require_config(
        math.isclose(
            CLASS_THRESHOLDS["fire"],
            0.25,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        (
            "Final R3-E6 requires "
            "FIRE_THRESHOLD=0.25"
        ),
    )

    _require_config(
        math.isclose(
            CLASS_THRESHOLDS["smoke"],
            0.25,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        (
            "Final R3-E6 requires "
            "SMOKE_THRESHOLD=0.25"
        ),
    )

    _require_config(
        math.isclose(
            MODEL_NMS_IOU,
            0.70,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        (
            "Final R3-E6 requires "
            "MODEL_NMS_IOU=0.70"
        ),
    )

    _require_config(
        MODEL_MAX_DET == 300,
        (
            "Final R3-E6 requires "
            "MODEL_MAX_DET=300"
        ),
    )

    _require_config(
        MODEL_RECT is False,
        (
            "Final R3-E6 requires "
            "MODEL_RECT=false"
        ),
    )

    _require_config(
        MODEL_BATCH == 1,
        (
            "Final R3-E6 requires "
            "MODEL_BATCH=1"
        ),
    )


    # ========================================================
    # System confirmation contract
    # ========================================================

    _require_config(
        FRAMES_PER_SCAN == 3,
        (
            "Final R3-E6 integration requires "
            "FRAMES_PER_SCAN=3"
        ),
    )

    _require_config(
        MIN_CONFIRM_FRAMES == 2,
        (
            "Final R3-E6 integration requires "
            "MIN_CONFIRM_FRAMES=2"
        ),
    )

    _require_config(
        math.isclose(
            FRAME_SAMPLE_GAP_SEC,
            0.15,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        (
            "Final R3-E6 integration requires "
            "FRAME_SAMPLE_GAP_SEC=0.15"
        ),
    )

    _require_config(
        math.isclose(
            CONSENSUS_IOU_THRESHOLD,
            0.30,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        (
            "Final R3-E6 integration requires "
            "CONSENSUS_IOU_THRESHOLD=0.30"
        ),
    )

    _require_config(
        STARTUP_WARMUP_RUNS == 3,
        (
            "Final R3-E6 integration requires "
            "STARTUP_WARMUP_RUNS=3"
        ),
    )


    # ========================================================
    # Frozen metadata contract
    # ========================================================

    _require_config(
        EXPECTED_MODEL_SHA256
        ==
        (
            "49dc0464d99a6c250cf3c3e305d4149c"
            "3d4ce3ee354d9d7a5ae1cb8c53a22183"
        ),
        (
            "Final R3-E6 expected SHA256 "
            "has been modified"
        ),
    )

    _require_config(
        EXPECTED_MODEL_CLASSES
        == {
            0: "fire",
            1: "smoke",
        },
        (
            "Final R3-E6 Class Contract "
            "has been modified"
        ),
    )

    _require_config(
        EXPECTED_ULTRALYTICS_VERSION
        == "8.4.95",
        (
            "Final R3-E6 requires "
            "Ultralytics 8.4.95"
        ),
    )

    return True


# ============================================================
# Validate generic configuration on import
# ============================================================
#
# ไม่เรียก validate_final_model_contract() ตอน import
#
# เหตุผล:
# - Benchmark / Development tools อาจทดลอง Backend อื่น
# - OpenVINO equivalence tools ยังต้องรันได้
#
# Production preflight ต้องเรียก:
#
#     validate_final_model_contract()
#
# ก่อนอนุญาต Detection Service
#
# ============================================================

validate_runtime_config()


# ============================================================
# Runtime directories
# ============================================================

for path in (
    CALIBRATION_DIR,
    STATIC_DIR,
    BASE_DIR / "models",
    BASE_DIR / "models" / "final",
):

    path.mkdir(
        parents=True,
        exist_ok=True,
    )
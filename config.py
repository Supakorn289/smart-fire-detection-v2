#!/usr/bin/env python3

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

def env_text(
    name,
    default="",
):
    """
    อ่าน Environment Variable แบบข้อความ

    ใช้ strip() กับค่าทั่วไป
    แต่ไม่ควรใช้กับ Password
    """

    return (
        os.getenv(
            name,
            default,
        )
        .strip()
    )


def env_int(
    name,
    default,
):

    return int(
        os.getenv(
            name,
            str(default),
        )
    )


def env_float(
    name,
    default,
):

    return float(
        os.getenv(
            name,
            str(default),
        )
    )


def env_path(
    name,
    default,
):
    """
    Path จาก Environment

    ถ้าเป็น Relative Path:
        models/fire.pt

    จะ Resolve จาก BASE_DIR เป็น:
        <project>/models/fire.pt

    ทำให้ไม่ขึ้นกับ Current Working Directory
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
#
# ไม่มี IP / Username / Password จริงเป็น Default
#
# Production ต้องส่งค่าผ่าน Environment
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
# เพื่อไม่เปลี่ยน Password ที่ผู้ใช้กำหนด
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
#
# สามารถกำหนด CAMERA_ID เองได้
#
# เช่น:
# CAMERA_ID=rtsp://...
#
# ถ้าไม่ได้กำหนด
# ระบบจะประกอบจากค่าด้านบน
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

        # ปล่อยว่างแทนการฝัง IP จริงใน Source
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
# ค่านี้เป็น Camera Geometry
# ไม่ใช่ Secret
#
# แต่ถ้าเปลี่ยน:
# - Camera
# - Lens
# - Optical Zoom
# - Crop
# - Resolution
#
# ต้องตรวจ Calibration ใหม่
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
# PTZ timing
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
        BASE_DIR
        / "models"
        / "fire.pt",
    )
)


MODEL_PATH_OPENVINO = str(
    env_path(
        "MODEL_PATH_OPENVINO",
        BASE_DIR
        / "models"
        / "fire_openvino_model",
    )
)


INFERENCE_DEVICE = env_text(
    "INFERENCE_DEVICE",
    "cpu",
)


IMGSZ = env_int(
    "IMGSZ",
    640,
)


# ============================================================
# Detection
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
        0.50,
    ),

    "smoke": env_float(
        "SMOKE_THRESHOLD",
        0.60,
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

CONSENSUS_IOU_THRESHOLD = env_float(
    "CONSENSUS_IOU_THRESHOLD",
    0.30,
)


# ============================================================
# Calibration
# ============================================================

CALIBRATION_DIR = env_path(
    "CALIBRATION_DIR",
    BASE_DIR
    / "calibration",
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
# Camera site coordinates
# ============================================================
#
# ไม่มี GPS จริงเป็น Default
#
# float("nan") ทำให้:
#
# - config.py ยัง Import ได้
# - Offline tools ยังทำงานได้
# - preflight.py สามารถตรวจพบว่า
#   Production GPS ยังไม่ได้ตั้ง
#
# ห้ามใช้ NaN ใน Production
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
# Output
# ============================================================

STATIC_DIR = env_path(
    "STATIC_DIR",
    BASE_DIR
    / "static",
)


DASHBOARD_WRITE_INTERVAL_SEC = env_float(
    "DASHBOARD_WRITE_INTERVAL_SEC",
    1.0,
)


# ============================================================
# Server
# ============================================================

HEADLESS_MODE = (
    env_text(
        "HEADLESS_MODE",
        "1",
    )
    != "0"
)


# ============================================================
# Runtime directories
# ============================================================

for path in (
    CALIBRATION_DIR,
    STATIC_DIR,
    BASE_DIR / "models",
):

    path.mkdir(
        parents=True,
        exist_ok=True,
    )
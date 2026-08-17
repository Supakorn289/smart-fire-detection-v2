#!/usr/bin/env python3

import argparse
import importlib.util
import ipaddress
import json
import math
import os
import platform
import stat
import sys
import time
from pathlib import Path

from config import (
    BASE_DIR,
    CALIBRATION_DIR,

    CAMERA_IP,
    CAMERA_PORT,
    CAMERA_USER,
    CAMERA_PWD,

    RTSP_PORT,
    RTSP_PATH,

    FRAME_WIDTH,
    FRAME_HEIGHT,
    HFOV_DEG,

    CAMERA_LAT,
    CAMERA_LON,

    PRESET_PAN_DEG,
    PRESET_BEARING_DEG,

    MODEL_BACKEND,
    MODEL_PATH_PT,
    MODEL_PATH_OPENVINO,
    INFERENCE_DEVICE,
    IMGSZ,

    FRAMES_PER_SCAN,
    MIN_CONFIRM_FRAMES,
    CLASS_THRESHOLDS,

    GLOBAL_DISTANCE_CALIBRATION,
    SITE_CALIBRATION_FILE,

    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
)


# ============================================================
# Smart Fire Detection v2
# Production Preflight Checker
# ============================================================
#
# OFFLINE:
#
# - ตรวจ Software
# - ตรวจ Configuration ที่ตรวจได้
# - ไม่โหลด AI Model จริง
# - ไม่เชื่อม RTSP
# - ไม่บังคับ Camera/Site
#
#
# FULL:
#
# - ตรวจ Production Environment
# - ตรวจ Camera credentials
# - ตรวจ Backend / Device
# - ตรวจ Model
# - ตรวจ Calibration
# - ตรวจ Camera
#
# ไฟล์นี้:
#
# - ไม่สั่ง PTZ
# - ไม่แก้ Calibration
# - ไม่แก้ Environment
# - ไม่พิมพ์ Password / Token
#
# ============================================================


# ============================================================
# Constants
# ============================================================

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


PRODUCTION_ENV_FILE = Path(
    "/etc/smart-fire-detection/production.env"
)


# Environment ที่ Production ต้องกำหนดเอง
#
# แม้ config.py จะมี safe default บางค่า
# Production ต้องกำหนดค่าหลักแบบ Explicit
# เพื่อป้องกันการใช้ Default โดยไม่รู้ตัว

REQUIRED_PRODUCTION_ENV = [

    # Camera
    "CAMERA_IP",
    "CAMERA_PORT",
    "CAMERA_USER",
    "CAMERA_PWD",

    # RTSP
    "RTSP_PORT",
    "RTSP_PATH",

    # Frame / Geometry
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "HFOV_DEG",

    # Site
    "CAMERA_LAT",
    "CAMERA_LON",

    # AI
    "MODEL_BACKEND",
    "INFERENCE_DEVICE",
    "IMGSZ",

    # Detection
    "FIRE_THRESHOLD",
    "SMOKE_THRESHOLD",
    "FRAMES_PER_SCAN",
    "MIN_CONFIRM_FRAMES",
]


# ============================================================
# Production AI policy
# ============================================================
#
# Production Server ของ Project นี้ใช้ CPU inference
#
# PyTorch:
#     INFERENCE_DEVICE=cpu
#
# OpenVINO:
#     INFERENCE_DEVICE=intel:cpu
#
# ถ้าในอนาคตเปลี่ยน Hardware Policy
# ให้แก้ส่วนนี้ด้วย
# ============================================================

PRODUCTION_DEVICE_POLICY = {

    "pt": {
        "cpu",
    },

    "openvino": {
        "intel:cpu",
    },
}


# ============================================================
# Results
# ============================================================

results = []


# ============================================================
# Result helper
# ============================================================

def add(
    status,
    name,
    detail="",
):

    results.append(
        (
            status,
            name,
            detail,
        )
    )

    if detail:

        print(
            f"[{status:<4}] "
            f"{name} - {detail}"
        )

    else:

        print(
            f"[{status:<4}] "
            f"{name}"
        )


# ============================================================
# Generic helpers
# ============================================================

def finite(
    value,
):

    try:

        return math.isfinite(
            float(
                value
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        return False


def load_json(
    path,
):

    path = Path(
        path
    )

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        add(
            FAIL,
            path.name,
            (
                "อ่าน JSON ไม่ได้: "
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return None


def env_exists(
    name,
):

    return (
        name in os.environ
    )


def env_has_value(
    name,
):

    if name not in os.environ:

        return False

    return bool(
        str(
            os.environ.get(
                name,
                "",
            )
        ).strip()
    )


def looks_like_placeholder(
    value,
):
    """
    ตรวจ Placeholder ทั่วไป

    ไม่พิมพ์ค่าจริงออกหน้าจอ
    """

    text = str(
        value
    ).strip().lower()

    if not text:

        return True

    exact_placeholders = {

        "change_me",
        "changeme",

        "replace_me",
        "replaceme",

        "your_value",
        "your_value_here",

        "example",
        "example_value",

        "todo",

        "password",

        "null",
        "none",
    }

    if text in exact_placeholders:

        return True

    fragments = [

        "change_me",
        "replace_me",

        "<change",
        "<replace",

        "your_",
    ]

    return any(
        fragment in text
        for fragment in fragments
    )


# ============================================================
# Python
# ============================================================

def check_python():

    version = (
        sys.version_info
    )

    version_text = (
        f"{version.major}."
        f"{version.minor}."
        f"{version.micro}"
    )

    if (
        version.major == 3
        and
        version.minor == 12
    ):

        add(
            PASS,
            "Python",
            version_text,
        )

    else:

        add(
            FAIL,
            "Python",
            (
                f"{version_text} "
                "| Project baseline="
                "Python 3.12"
            ),
        )


# ============================================================
# Dependencies
# ============================================================

def check_dependencies():

    packages = {

        "numpy":
            "numpy",

        "OpenCV":
            "cv2",

        "requests":
            "requests",

        "Ultralytics":
            "ultralytics",

        "psutil":
            "psutil",

        "Flask":
            "flask",
    }

    missing = []

    for (
        display_name,
        module_name,
    ) in packages.items():

        if (
            importlib.util.find_spec(
                module_name
            )
            is None
        ):

            missing.append(
                display_name
            )

    if missing:

        add(
            FAIL,
            "Dependencies",
            (
                "ขาด: "
                + ", ".join(
                    missing
                )
            ),
        )

    else:

        add(
            PASS,
            "Dependencies",
            "Runtime packages พร้อม",
        )


# ============================================================
# Production Environment Variables
# ============================================================

def check_environment(
    offline=False,
):

    missing = [

        name

        for name
        in REQUIRED_PRODUCTION_ENV

        if not env_exists(
            name
        )
    ]

    empty = [

        name

        for name
        in REQUIRED_PRODUCTION_ENV

        if (
            env_exists(
                name
            )
            and
            not env_has_value(
                name
            )
        )
    ]

    # ========================================================
    # ทุกค่าถูกกำหนด
    # ========================================================

    if (
        not missing
        and
        not empty
    ):

        add(
            PASS,
            "Environment",
            (
                "Production variables "
                "หลักถูกกำหนดแบบ explicit"
            ),
        )

    # ========================================================
    # Offline
    # ========================================================

    elif offline:

        detail_parts = []

        if missing:

            detail_parts.append(
                (
                    "ยังไม่ได้กำหนด: "
                    + ", ".join(
                        missing
                    )
                )
            )

        if empty:

            detail_parts.append(
                (
                    "ค่าว่าง: "
                    + ", ".join(
                        empty
                    )
                )
            )

        detail_parts.append(
            "Offline mode ยังทดสอบต่อได้"
        )

        add(
            WARN,
            "Environment",
            " | ".join(
                detail_parts
            ),
        )

    # ========================================================
    # FULL
    # ========================================================

    else:

        detail_parts = []

        if missing:

            detail_parts.append(
                (
                    "Missing: "
                    + ", ".join(
                        missing
                    )
                )
            )

        if empty:

            detail_parts.append(
                (
                    "Empty: "
                    + ", ".join(
                        empty
                    )
                )
            )

        add(
            FAIL,
            "Production environment",
            " | ".join(
                detail_parts
            ),
        )

    # ========================================================
    # Local .env warning
    # ========================================================

    env_file = (
        BASE_DIR
        / ".env"
    )

    if env_file.exists():

        add(
            WARN,
            ".env",
            (
                "พบ .env แต่ config.py "
                "ไม่ได้โหลดอัตโนมัติ "
                "| ต้อง Load ผ่าน "
                "Shell / IDE / systemd"
            ),
        )


# ============================================================
# Production Environment File
# ============================================================

def check_production_environment_file(
    offline=False,
):

    # ========================================================
    # Offline ไม่ต้องมี Production file
    # ========================================================

    if offline:

        add(
            SKIP,
            "Production env file",
            "Offline mode",
        )

        return

    # ========================================================
    # Windows / Development machine
    # ========================================================

    if (
        platform.system()
        != "Linux"
    ):

        add(
            SKIP,
            "Production env file",
            (
                "Non-Linux host "
                "| ตรวจจริงเมื่อ Deploy Debian"
            ),
        )

        return

    # ========================================================
    # Linux Production
    # ========================================================

    path = (
        PRODUCTION_ENV_FILE
    )

    if not path.exists():

        add(
            FAIL,
            "Production env file",
            (
                "ไม่พบ "
                f"{path}"
            ),
        )

        return

    if not path.is_file():

        add(
            FAIL,
            "Production env file",
            (
                f"{path} "
                "ไม่ใช่ไฟล์"
            ),
        )

        return

    try:

        info = (
            path.stat()
        )

    except OSError as exc:

        add(
            FAIL,
            "Production env file",
            (
                "stat() ไม่สำเร็จ: "
                f"{exc}"
            ),
        )

        return

    mode = stat.S_IMODE(
        info.st_mode
    )

    # ========================================================
    # Group / Others ต้องไม่มี permission
    # ========================================================

    if (
        mode
        & 0o077
    ):

        add(
            FAIL,
            "Production env permission",
            (
                f"permission="
                f"{mode:04o} "
                "| ต้องไม่เปิดสิทธิ์ "
                "Group/Others"
            ),
        )

    else:

        add(
            PASS,
            "Production env permission",
            (
                f"permission="
                f"{mode:04o}"
            ),
        )

    # ========================================================
    # Root ownership
    # ========================================================

    if (
        hasattr(
            info,
            "st_uid",
        )
        and
        info.st_uid == 0
    ):

        add(
            PASS,
            "Production env owner",
            "root",
        )

    else:

        add(
            WARN,
            "Production env owner",
            (
                "ไม่ใช่ root "
                "| ตรวจ ownership ก่อน Production"
            ),
        )


# ============================================================
# Camera Credentials
# ============================================================

def check_camera_credentials(
    offline=False,
):

    user_ready = bool(
        str(
            CAMERA_USER
        ).strip()
    )

    password_ready = bool(
        str(
            CAMERA_PWD
        )
    )

    # ========================================================
    # ยังไม่ได้กำหนด
    # ========================================================

    if (
        not user_ready
        or
        not password_ready
    ):

        if offline:

            add(
                SKIP,
                "Camera credentials",
                (
                    "ยังไม่ได้กำหนด "
                    "Camera username/password "
                    "| Offline mode"
                ),
            )

        else:

            add(
                FAIL,
                "Camera credentials",
                (
                    "CAMERA_USER / CAMERA_PWD "
                    "ต้องถูกกำหนดก่อน Production"
                ),
            )

        return

    # ========================================================
    # Placeholder
    # ========================================================

    user_placeholder = (
        looks_like_placeholder(
            CAMERA_USER
        )
    )

    password_placeholder = (
        looks_like_placeholder(
            CAMERA_PWD
        )
    )

    if (
        user_placeholder
        or
        password_placeholder
    ):

        if offline:

            add(
                WARN,
                "Camera credentials",
                (
                    "พบค่าที่ดูเหมือน Placeholder "
                    "| Offline mode"
                ),
            )

        else:

            add(
                FAIL,
                "Camera credentials",
                (
                    "พบ Placeholder "
                    "ใน CAMERA_USER/CAMERA_PWD"
                ),
            )

        return

    # ========================================================
    # PASS
    # ========================================================

    add(
        PASS,
        "Camera credentials",
        (
            "Configured "
            "| values hidden"
        ),
    )


# ============================================================
# Backend / Device
# ============================================================

def check_backend_device():

    backend = (
        str(
            MODEL_BACKEND
        )
        .strip()
        .lower()
    )

    device = (
        str(
            INFERENCE_DEVICE
        )
        .strip()
        .lower()
    )

    # ========================================================
    # Backend
    # ========================================================

    if backend not in {
        "pt",
        "openvino",
    }:

        add(
            FAIL,
            "AI backend",
            (
                f"ไม่รองรับ backend="
                f"{backend!r}"
            ),
        )

        return False

    add(
        PASS,
        "AI backend",
        backend,
    )

    # ========================================================
    # Device empty
    # ========================================================

    if not device:

        add(
            FAIL,
            "Inference device",
            "INFERENCE_DEVICE ว่าง",
        )

        return False

    # ========================================================
    # Production policy
    # ========================================================

    allowed = (
        PRODUCTION_DEVICE_POLICY[
            backend
        ]
    )

    if device not in allowed:

        add(
            FAIL,
            "Inference device",
            (
                f"backend={backend} "
                f"| device={device} "
                "| ไม่ตรง Production CPU policy"
            ),
        )

        return False

    add(
        PASS,
        "Inference device",
        (
            f"{backend} -> "
            f"{device}"
        ),
    )

    return True


# ============================================================
# Runtime parameters
# ============================================================

def check_runtime_parameters():

    # ========================================================
    # Camera HTTP port
    # ========================================================

    if (
        1
        <= CAMERA_PORT
        <= 65535
    ):

        add(
            PASS,
            "Camera HTTP port",
            str(
                CAMERA_PORT
            ),
        )

    else:

        add(
            FAIL,
            "Camera HTTP port",
            (
                f"ค่าผิดปกติ: "
                f"{CAMERA_PORT}"
            ),
        )

    # ========================================================
    # RTSP port
    # ========================================================

    if (
        1
        <= RTSP_PORT
        <= 65535
    ):

        add(
            PASS,
            "RTSP port",
            str(
                RTSP_PORT
            ),
        )

    else:

        add(
            FAIL,
            "RTSP port",
            (
                f"ค่าผิดปกติ: "
                f"{RTSP_PORT}"
            ),
        )

    # ========================================================
    # RTSP path
    # ========================================================

    if (
        str(
            RTSP_PATH
        ).startswith(
            "/"
        )
    ):

        add(
            PASS,
            "RTSP path",
            "Format OK",
        )

    else:

        add(
            FAIL,
            "RTSP path",
            (
                "RTSP_PATH "
                "ควรขึ้นต้นด้วย /"
            ),
        )

    # ========================================================
    # IMGSZ
    # ========================================================

    if IMGSZ > 0:

        add(
            PASS,
            "AI image size",
            str(
                IMGSZ
            ),
        )

    else:

        add(
            FAIL,
            "AI image size",
            str(
                IMGSZ
            ),
        )

    # ========================================================
    # Frames / Scan
    # ========================================================

    if FRAMES_PER_SCAN < 1:

        add(
            FAIL,
            "Frames per scan",
            (
                "FRAMES_PER_SCAN "
                "ต้อง >= 1"
            ),
        )

    else:

        add(
            PASS,
            "Frames per scan",
            str(
                FRAMES_PER_SCAN
            ),
        )

    # ========================================================
    # Consensus confirm frames
    # ========================================================

    if (
        1
        <= MIN_CONFIRM_FRAMES
        <= FRAMES_PER_SCAN
    ):

        add(
            PASS,
            "Confirmation frames",
            (
                f"{MIN_CONFIRM_FRAMES}"
                f"/"
                f"{FRAMES_PER_SCAN}"
            ),
        )

    else:

        add(
            FAIL,
            "Confirmation frames",
            (
                f"{MIN_CONFIRM_FRAMES}"
                f"/"
                f"{FRAMES_PER_SCAN}"
                " ไม่ถูกต้อง"
            ),
        )

    # ========================================================
    # Class thresholds
    # ========================================================

    for (
        class_name,
        threshold,
    ) in CLASS_THRESHOLDS.items():

        if (
            finite(
                threshold
            )
            and
            0.0
            <= float(
                threshold
            )
            <= 1.0
        ):

            add(
                PASS,
                (
                    f"{class_name} "
                    "threshold"
                ),
                (
                    f"{float(threshold):.2f}"
                ),
            )

        else:

            add(
                FAIL,
                (
                    f"{class_name} "
                    "threshold"
                ),
                str(
                    threshold
                ),
            )


# ============================================================
# Basic Camera / Site configuration
# ============================================================

def check_config(
    offline=False,
):

    # ========================================================
    # Resolution
    # ========================================================

    if (
        FRAME_WIDTH > 0
        and
        FRAME_HEIGHT > 0
    ):

        add(
            PASS,
            "Resolution",
            (
                f"{FRAME_WIDTH}"
                f"x"
                f"{FRAME_HEIGHT}"
            ),
        )

    else:

        add(
            FAIL,
            "Resolution",
            (
                f"{FRAME_WIDTH}"
                f"x"
                f"{FRAME_HEIGHT}"
            ),
        )

    # ========================================================
    # HFOV
    # ========================================================

    if (
        finite(
            HFOV_DEG
        )
        and
        0
        < HFOV_DEG
        < 180
    ):

        add(
            PASS,
            "HFOV",
            (
                f"{HFOV_DEG:.6f}°"
            ),
        )

    else:

        add(
            FAIL,
            "HFOV",
            str(
                HFOV_DEG
            ),
        )

    # ========================================================
    # Camera coordinates
    # ========================================================

    coordinates_valid = (

        finite(
            CAMERA_LAT
        )

        and

        finite(
            CAMERA_LON
        )

        and

        -90
        <= CAMERA_LAT
        <= 90

        and

        -180
        <= CAMERA_LON
        <= 180
    )

    if coordinates_valid:

        add(
            PASS,
            "Camera coordinates",
            (
                "Configured "
                "| values hidden"
            ),
        )

    else:

        if offline:

            add(
                SKIP,
                "Camera coordinates",
                (
                    "ยังไม่ได้กำหนด Site GPS "
                    "| ต้องตั้งเมื่อ Deploy Site จริง"
                ),
            )

        else:

            add(
                FAIL,
                "Camera coordinates",
                (
                    "CAMERA_LAT / CAMERA_LON "
                    "ยังไม่ถูกต้อง"
                ),
            )

    # ========================================================
    # PTZ Presets
    # ========================================================

    expected_presets = set(
        range(
            1,
            10,
        )
    )

    pan_ok = (
        set(
            PRESET_PAN_DEG
        )
        == expected_presets
    )

    bearing_ok = (
        set(
            PRESET_BEARING_DEG
        )
        == expected_presets
    )

    if (
        pan_ok
        and
        bearing_ok
    ):

        add(
            PASS,
            "PTZ preset config",
            "Preset 1-9 ครบ",
        )

    else:

        add(
            FAIL,
            "PTZ preset config",
            "Preset 1-9 ไม่ครบ",
        )

    # ========================================================
    # Camera IP
    # ========================================================

    camera_ip_text = (
        str(
            CAMERA_IP
        ).strip()
    )

    if not camera_ip_text:

        if offline:

            add(
                SKIP,
                "Camera IP",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด"
                ),
            )

        else:

            add(
                FAIL,
                "Camera IP",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด"
                ),
            )

        camera_ip_valid = False

    else:

        try:

            ipaddress.ip_address(
                camera_ip_text
            )

            camera_ip_valid = True

            add(
                PASS,
                "Camera IP",
                (
                    "Configured "
                    "| value hidden"
                ),
            )

        except ValueError:

            camera_ip_valid = False

            add(
                FAIL,
                "Camera IP",
                (
                    "รูปแบบ IP "
                    "ไม่ถูกต้อง"
                ),
            )

    # ========================================================
    # RTSP config
    # ========================================================

    if camera_ip_valid:

        add(
            PASS,
            "RTSP config",
            (
                f"port={RTSP_PORT} "
                f"| path={RTSP_PATH}"
            ),
        )

    elif offline:

        add(
            SKIP,
            "RTSP config",
            (
                "Camera IP "
                "ยังไม่พร้อม "
                "| Offline mode"
            ),
        )

    else:

        add(
            FAIL,
            "RTSP config",
            "Camera IP ไม่พร้อม",
        )

    # ========================================================
    # PTZ HTTP config
    # ========================================================

    if camera_ip_valid:

        add(
            PASS,
            "PTZ HTTP config",
            (
                f"port="
                f"{CAMERA_PORT}"
            ),
        )

    elif offline:

        add(
            SKIP,
            "PTZ HTTP config",
            (
                "Camera IP "
                "ยังไม่พร้อม "
                "| Offline mode"
            ),
        )

    else:

        add(
            FAIL,
            "PTZ HTTP config",
            "Camera IP ไม่พร้อม",
        )


# ============================================================
# Camera Intrinsics
# ============================================================

def check_intrinsics():

    path = (
        CALIBRATION_DIR
        / "camera_intrinsics.json"
    )

    if not path.exists():

        add(
            WARN,
            "Camera intrinsics",
            (
                "ไม่พบ "
                "camera_intrinsics.json "
                "| ต้องตรวจ HFOV ให้ถูกต้อง"
            ),
        )

        return

    data = load_json(
        path
    )

    if data is None:

        return

    valid_for_production = bool(
        data.get(
            "valid_for_production",
            False,
        )
    )

    calibrated_hfov = (
        data.get(
            "effective_hfov_deg"
        )
    )

    if not valid_for_production:

        add(
            WARN,
            "Camera intrinsics",
            (
                "valid_for_production="
                "false"
            ),
        )

        return

    if not finite(
        calibrated_hfov
    ):

        add(
            FAIL,
            "Camera intrinsics",
            (
                "effective_hfov_deg "
                "ไม่ถูกต้อง"
            ),
        )

        return

    calibrated_hfov = float(
        calibrated_hfov
    )

    difference = abs(
        calibrated_hfov
        - HFOV_DEG
    )

    if difference <= 0.20:

        add(
            PASS,
            "Camera intrinsics",
            (
                "Calibrated HFOV="
                f"{calibrated_hfov:.6f}° "
                "| Runtime="
                f"{HFOV_DEG:.6f}°"
            ),
        )

    else:

        add(
            FAIL,
            "Camera intrinsics",
            (
                "HFOV mismatch "
                "| Calibration="
                f"{calibrated_hfov:.6f}° "
                "| Runtime="
                f"{HFOV_DEG:.6f}°"
            ),
        )


# ============================================================
# Bearing Calibration
# ============================================================

def check_bearing(
    offline=False,
):

    path = (
        SITE_CALIBRATION_FILE
    )

    if not path.exists():

        if offline:

            add(
                SKIP,
                "Bearing calibration",
                (
                    "ยังไม่มี site.json "
                    "| ต้อง Calibration "
                    "เมื่อเชื่อมกล้อง/"
                    "ติดตั้ง Site จริง"
                ),
            )

        else:

            add(
                FAIL,
                "Bearing calibration",
                (
                    "ไม่พบ site.json "
                    "-> รัน "
                    "calibrate_bearing.py"
                ),
            )

        return

    data = load_json(
        path
    )

    if data is None:

        return

    offset = (
        data.get(
            "north_offset_deg"
        )
    )

    if not finite(
        offset
    ):

        add(
            FAIL,
            "Bearing calibration",
            (
                "north_offset_deg "
                "ไม่ถูกต้อง"
            ),
        )

        return

    saved_width = (
        data.get(
            "frame_width"
        )
    )

    saved_height = (
        data.get(
            "frame_height"
        )
    )

    if (
        saved_width is not None
        and
        saved_height is not None
    ):

        try:

            saved_width = int(
                saved_width
            )

            saved_height = int(
                saved_height
            )

        except (
            TypeError,
            ValueError,
        ):

            add(
                FAIL,
                "Bearing calibration",
                (
                    "Resolution "
                    "ใน site.json "
                    "ไม่ถูกต้อง"
                ),
            )

            return

        if (
            saved_width
            != FRAME_WIDTH

            or

            saved_height
            != FRAME_HEIGHT
        ):

            add(
                FAIL,
                "Bearing calibration",
                (
                    "Resolution "
                    "ไม่ตรง Runtime"
                ),
            )

            return

    add(
        PASS,
        "Bearing calibration",
        (
            "site.json "
            "| north_offset="
            f"{float(offset):+.3f}°"
        ),
    )


# ============================================================
# Distance Calibration
# ============================================================

def check_distance(
    offline=False,
):

    path = (
        GLOBAL_DISTANCE_CALIBRATION
    )

    if not path.exists():

        if offline:

            add(
                SKIP,
                "Distance calibration",
                (
                    "ยังไม่มี "
                    "distance_global.json "
                    "| ต้อง Calibration "
                    "เมื่อเชื่อมกล้อง/"
                    "มีพื้นที่ทดสอบจริง"
                ),
            )

        else:

            add(
                FAIL,
                "Distance calibration",
                (
                    "ไม่พบ "
                    "distance_global.json "
                    "-> รัน "
                    "calibrate_distance.py"
                ),
            )

        return

    data = load_json(
        path
    )

    if data is None:

        return

    required = [

        "H",
        "K",
        "frame_width",
        "frame_height",
        "points",
    ]

    missing = [

        key

        for key
        in required

        if key not in data
    ]

    if missing:

        add(
            FAIL,
            "Distance calibration",
            (
                "ข้อมูลไม่ครบ: "
                + ", ".join(
                    missing
                )
            ),
        )

        return

    # ========================================================
    # H / K
    # ========================================================

    if not finite(
        data.get(
            "H"
        )
    ):

        add(
            FAIL,
            "Distance calibration",
            "ค่า H ไม่ถูกต้อง",
        )

        return

    if not finite(
        data.get(
            "K"
        )
    ):

        add(
            FAIL,
            "Distance calibration",
            "ค่า K ไม่ถูกต้อง",
        )

        return

    # ========================================================
    # Resolution
    # ========================================================

    try:

        saved_width = int(
            data[
                "frame_width"
            ]
        )

        saved_height = int(
            data[
                "frame_height"
            ]
        )

    except (
        TypeError,
        ValueError,
    ):

        add(
            FAIL,
            "Distance calibration",
            (
                "Resolution "
                "ใน Calibration "
                "ไม่ถูกต้อง"
            ),
        )

        return

    if (
        saved_width
        != FRAME_WIDTH

        or

        saved_height
        != FRAME_HEIGHT
    ):

        add(
            FAIL,
            "Distance calibration",
            (
                "Resolution "
                "ไม่ตรง Runtime"
            ),
        )

        return

    # ========================================================
    # Points
    # ========================================================

    try:

        points = int(
            data[
                "points"
            ]
        )

    except (
        TypeError,
        ValueError,
    ):

        add(
            FAIL,
            "Distance calibration",
            (
                "จำนวน Calibration "
                "points ไม่ถูกต้อง"
            ),
        )

        return

    if points < 3:

        add(
            FAIL,
            "Distance calibration",
            (
                f"มีเพียง "
                f"{points} points"
            ),
        )

        return

    # ========================================================
    # Detail
    # ========================================================

    detail = (
        f"{points} points"
    )

    min_distance = (
        data.get(
            "min_distance_m"
        )
    )

    max_distance = (
        data.get(
            "max_distance_m"
        )
    )

    if (
        finite(
            min_distance
        )
        and
        finite(
            max_distance
        )
    ):

        detail += (
            " | range="
            f"{float(min_distance):.2f}"
            "-"
            f"{float(max_distance):.2f}"
            "m"
        )

    pixel_rmse = (
        data.get(
            "pixel_rmse"
        )
    )

    if finite(
        pixel_rmse
    ):

        detail += (
            " | pixel_RMSE="
            f"{float(pixel_rmse):.3f}px"
        )

    add(
        PASS,
        "Distance calibration",
        detail,
    )


# ============================================================
# Telegram
# ============================================================

def check_telegram():

    token_ready = bool(
        str(
            TELEGRAM_TOKEN
        ).strip()
    )

    chat_ready = bool(
        str(
            TELEGRAM_CHAT_ID
        ).strip()
    )

    if (
        token_ready
        and
        chat_ready
    ):

        add(
            PASS,
            "Telegram",
            (
                "Configured "
                "| values hidden"
            ),
        )

    elif (
        not token_ready
        and
        not chat_ready
    ):

        add(
            WARN,
            "Telegram",
            (
                "ยังไม่ได้ตั้งค่า "
                "| Local alert "
                "ยังทำงานได้"
            ),
        )

    else:

        add(
            WARN,
            "Telegram",
            (
                "ตั้งค่าไม่ครบ "
                "| ต้องมีทั้ง Token "
                "และ Chat ID"
            ),
        )


# ============================================================
# AI Model
# ============================================================

def check_model(
    load_model=True,
):

    backend = (
        str(
            MODEL_BACKEND
        )
        .strip()
        .lower()
    )

    if backend not in {
        "pt",
        "openvino",
    }:

        # Backend ถูก Report ไปแล้ว
        # ใน check_backend_device()
        return

    # ========================================================
    # Model path
    # ========================================================

    if backend == "pt":

        model_path = Path(
            MODEL_PATH_PT
        )

    else:

        model_path = Path(
            MODEL_PATH_OPENVINO
        )

        if (
            importlib.util.find_spec(
                "openvino"
            )
            is None
        ):

            add(
                FAIL,
                "OpenVINO package",
                "ยังไม่ได้ติดตั้ง",
            )

            return

        add(
            PASS,
            "OpenVINO package",
            "Available",
        )

    # ========================================================
    # Path exists
    # ========================================================

    if not model_path.exists():

        add(
            FAIL,
            "AI model",
            (
                "ไม่พบ Model Path"
            ),
        )

        return

    add(
        PASS,
        "AI model",
        (
            f"{backend} "
            "| path exists"
        ),
    )

    # ========================================================
    # Offline
    # ========================================================

    if not load_model:

        add(
            SKIP,
            "AI model load",
            "Offline mode",
        )

        return

    # ========================================================
    # Load Model
    # ========================================================

    try:

        from ultralytics import (
            YOLO
        )

        model = YOLO(
            str(
                model_path
            )
        )

        names_object = (
            model.names
        )

        if isinstance(
            names_object,
            dict,
        ):

            names = {
                str(
                    value
                ).strip().lower()
                for value
                in names_object.values()
            }

        else:

            names = {
                str(
                    value
                ).strip().lower()
                for value
                in names_object
            }

        has_fire = any(

            (
                "fire" in name
                or
                "flame" in name
            )

            for name
            in names
        )

        has_smoke = any(

            "smoke" in name

            for name
            in names
        )

        if (
            has_fire
            and
            has_smoke
        ):

            add(
                PASS,
                "AI model classes",
                "Fire + Smoke พร้อม",
            )

        else:

            add(
                FAIL,
                "AI model classes",
                (
                    "Model ต้องรองรับ "
                    "Fire และ Smoke"
                ),
            )

    except Exception as exc:

        add(
            FAIL,
            "AI model load",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )


# ============================================================
# RTSP Camera
# ============================================================

def check_camera(
    timeout=10,
):

    if not str(
        CAMERA_IP
    ).strip():

        add(
            FAIL,
            "RTSP camera",
            (
                "CAMERA_IP "
                "ยังไม่ได้กำหนด"
            ),
        )

        return

    if (
        not str(
            CAMERA_USER
        ).strip()

        or

        not str(
            CAMERA_PWD
        )
    ):

        add(
            FAIL,
            "RTSP camera",
            (
                "Camera credentials "
                "ยังไม่พร้อม"
            ),
        )

        return

    try:

        from camera import (
            LatestFrameCamera
        )

        camera = (
            LatestFrameCamera()
            .start()
        )

        try:

            deadline = (
                time.monotonic()
                + timeout
            )

            packet = None

            while (
                time.monotonic()
                < deadline
            ):

                packet = (
                    camera.latest(
                        copy=False
                    )
                )

                if (
                    packet
                    is not None
                ):

                    break

                time.sleep(
                    0.1
                )

            # =================================================
            # Timeout
            # =================================================

            if packet is None:

                add(
                    FAIL,
                    "RTSP camera",
                    (
                        "ไม่ได้รับ Frame "
                        f"ภายใน {timeout}s"
                    ),
                )

                return

            # =================================================
            # Resolution
            # =================================================

            height, width = (
                packet.frame.shape[
                    :2
                ]
            )

            if (
                width
                != FRAME_WIDTH

                or

                height
                != FRAME_HEIGHT
            ):

                add(
                    FAIL,
                    "RTSP camera",
                    (
                        f"{width}x{height} "
                        "ไม่ตรง Runtime "
                        f"{FRAME_WIDTH}x"
                        f"{FRAME_HEIGHT}"
                    ),
                )

                return

            # =================================================
            # Frame age
            # =================================================

            try:

                frame_age = max(
                    0.0,
                    time.time()
                    - float(
                        packet.timestamp
                    ),
                )

                age_text = (
                    f"{frame_age:.3f}s"
                )

            except Exception:

                age_text = "unknown"

            add(
                PASS,
                "RTSP camera",
                (
                    f"{width}x{height} "
                    f"| seq={packet.seq} "
                    f"| age={age_text}"
                ),
            )

        finally:

            camera.stop()

    except Exception as exc:

        add(
            FAIL,
            "RTSP camera",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )


# ============================================================
# Summary
# ============================================================

def summary(
    offline=False,
):

    pass_count = sum(

        status == PASS

        for (
            status,
            _,
            _,
        )
        in results
    )

    warn_count = sum(

        status == WARN

        for (
            status,
            _,
            _,
        )
        in results
    )

    fail_count = sum(

        status == FAIL

        for (
            status,
            _,
            _,
        )
        in results
    )

    skip_count = sum(

        status == SKIP

        for (
            status,
            _,
            _,
        )
        in results
    )

    print()

    print(
        "=" * 72
    )

    print(
        "PREFLIGHT SUMMARY"
    )

    print(
        "=" * 72
    )

    print(
        f"PASS : {pass_count}"
    )

    print(
        f"WARN : {warn_count}"
    )

    print(
        f"FAIL : {fail_count}"
    )

    print(
        f"SKIP : {skip_count}"
    )

    print(
        "-" * 72
    )

    # ========================================================
    # FAIL
    # ========================================================

    if fail_count:

        if offline:

            print(
                "OFFLINE STATUS: FAILED"
            )

            print(
                (
                    "พบ Software/Configuration "
                    "ที่ต้องแก้ก่อนขั้นถัดไป"
                )
            )

        else:

            print(
                "SYSTEM STATUS: NOT READY"
            )

            print(
                (
                    "แก้รายการ FAIL "
                    "ก่อนรัน main.py"
                )
            )

        return 1

    # ========================================================
    # OFFLINE
    # ========================================================

    if offline:

        if warn_count:

            print(
                (
                    "OFFLINE STATUS: "
                    "SOFTWARE CHECK PASSED "
                    "WITH WARNINGS"
                )
            )

        else:

            print(
                (
                    "OFFLINE STATUS: "
                    "SOFTWARE CHECK PASSED"
                )
            )

        print(
            (
                "รายการ SKIP ต้องตรวจอีกครั้ง "
                "เมื่อมี Production Hardware "
                "/ Site จริง"
            )
        )

        return 0

    # ========================================================
    # FULL on non-Linux
    # ========================================================

    if (
        platform.system()
        != "Linux"
    ):

        if warn_count:

            print(
                (
                    "FULL STATUS: "
                    "FIELD TEST CHECK PASSED "
                    "WITH WARNINGS"
                )
            )

        else:

            print(
                (
                    "FULL STATUS: "
                    "FIELD TEST CHECK PASSED"
                )
            )

        print(
            (
                "Production READY "
                "จะประเมินบน Linux "
                "Production Server เท่านั้น"
            )
        )

        return 0

    # ========================================================
    # FULL on Linux Production
    # ========================================================

    if warn_count:

        print(
            (
                "SYSTEM STATUS: "
                "READY WITH WARNINGS"
            )
        )

        return 0

    print(
        "SYSTEM STATUS: READY"
    )

    return 0


# ============================================================
# Main
# ============================================================

def main():

    results.clear()

    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- Production Preflight"
        )
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "ตรวจ Software โดยไม่โหลด "
            "AI Model จริงและไม่เชื่อม RTSP"
        ),
    )

    args = (
        parser.parse_args()
    )

    # ========================================================
    # Header
    # ========================================================

    print(
        "=" * 72
    )

    print(
        "Smart Fire Detection v2 "
        "- Preflight"
    )

    print(
        "=" * 72
    )

    print(
        f"OS      : "
        f"{platform.system()} "
        f"{platform.release()}"
    )

    print(
        f"Project : "
        f"{BASE_DIR}"
    )

    print(
        "Mode    : "
        + (
            "OFFLINE"
            if args.offline
            else "FULL"
        )
    )

    print(
        "PTZ     : "
        "ไม่สั่งกล้องหมุน"
    )

    print(
        "=" * 72
    )

    # ========================================================
    # Software
    # ========================================================

    check_python()

    check_dependencies()

    # ========================================================
    # Production Environment
    # ========================================================

    check_environment(
        offline=args.offline
    )

    check_production_environment_file(
        offline=args.offline
    )

    # ========================================================
    # Credentials
    # ========================================================

    check_camera_credentials(
        offline=args.offline
    )

    # ========================================================
    # AI Backend / Device
    # ========================================================

    check_backend_device()

    # ========================================================
    # Runtime Parameters
    # ========================================================

    check_runtime_parameters()

    # ========================================================
    # Basic Config
    # ========================================================

    check_config(
        offline=args.offline
    )

    # ========================================================
    # Camera Geometry
    # ========================================================

    check_intrinsics()

    # ========================================================
    # Site Calibration
    # ========================================================

    check_bearing(
        offline=args.offline
    )

    check_distance(
        offline=args.offline
    )

    # ========================================================
    # Notification
    # ========================================================

    check_telegram()

    # ========================================================
    # AI Model
    # ========================================================

    check_model(
        load_model=(
            not args.offline
        )
    )

    # ========================================================
    # RTSP
    # ========================================================

    if args.offline:

        add(
            SKIP,
            "RTSP camera",
            "Offline mode",
        )

    else:

        check_camera()

    # ========================================================
    # Summary
    # ========================================================

    return summary(
        offline=args.offline
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
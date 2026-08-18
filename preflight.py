#!/usr/bin/env python3
# preflight.py

import argparse
import importlib.metadata
import importlib.util
import ipaddress
import json
import math
import os
import platform
import shutil
import stat
import subprocess
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
    SWEEP_SEQUENCE,

    DEG_PER_SEC,
    PTZ_BUFFER_SEC,
    INITIAL_PRESET_WAIT_SEC,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    POST_MOVE_FRESH_FRAMES,

    MODEL_BACKEND,
    MODEL_PATH_PT,
    MODEL_PATH_OPENVINO,
    INFERENCE_DEVICE,
    IMGSZ,
    STARTUP_WARMUP_RUNS,

    FRAMES_PER_SCAN,
    MIN_CONFIRM_FRAMES,
    FRAME_SAMPLE_GAP_SEC,
    CLASS_THRESHOLDS,
    CONSENSUS_IOU_THRESHOLD,

    GLOBAL_DISTANCE_CALIBRATION,
    SITE_CALIBRATION_FILE,
    MIN_VALID_DISTANCE_M,
    MAX_VALID_DISTANCE_M,

    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,

    ALERT_COOLDOWN_SEC,
    ALERT_DEDUP_IOU_THRESHOLD,

    DASHBOARD_WRITE_INTERVAL_SEC,
    HEADLESS_MODE,

    validate_runtime_config,
)


# ============================================================
# Smart Fire Detection v2
# Production Preflight Checker
# ============================================================
#
# OFFLINE:
#
# - ตรวจ Python / Dependencies
# - ตรวจ Configuration
# - ตรวจ Deployment files
# - ตรวจ Calibration files ที่มีอยู่
# - ไม่โหลด AI Model จริง
# - ไม่เชื่อม RTSP
# - ไม่สั่ง PTZ
#
#
# FULL:
#
# - ตรวจ Production Environment
# - ตรวจ Camera credentials
# - ตรวจ Backend / Device
# - โหลด AI Model
# - ทดสอบ Inference ด้วย Blank Frame
# - ตรวจ Calibration
# - เชื่อม RTSP และตรวจ Frame
#
#
# ไฟล์นี้:
#
# - ไม่สั่ง PTZ หมุน
# - ไม่บันทึก Preset
# - ไม่สร้าง Calibration ใหม่
# - ไม่แก้ Environment
# - ไม่ Start systemd service
# - ไม่พิมพ์ Password / Token
#
# ============================================================


# ============================================================
# Result constants
# ============================================================

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


# ============================================================
# Production paths
# ============================================================

PRODUCTION_ENV_FILE = Path(
    "/etc/smart-fire-detection/production.env"
)

SYSTEMD_DIR = Path(
    "/etc/systemd/system"
)

DEPLOY_DIR = (
    BASE_DIR
    / "deploy"
)

DETECTION_UNIT_NAME = (
    "smart-fire-detection.service"
)

DASHBOARD_UNIT_NAME = (
    "smart-fire-dashboard.service"
)


# ============================================================
# Required Production Environment Variables
# ============================================================
#
# ค่ากลุ่มนี้ต้องถูกกำหนด Explicit
# บน Production Server
#
# CAMERA_ID ไม่บังคับ
# เพราะ config.py สามารถประกอบ RTSP URL
# จาก Camera configuration ได้
#
# ============================================================

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

    # PTZ / Frame synchronization
    "DEG_PER_SEC",
    "PTZ_BUFFER_SEC",
    "INITIAL_PRESET_WAIT_SEC",
    "STABLE_DIFF_THRESHOLD",
    "STABLE_REQUIRED_PAIRS",
    "STABLE_TIMEOUT_SEC",
    "POST_MOVE_FRESH_FRAMES",

    # AI
    "MODEL_BACKEND",
    "MODEL_PATH_PT",
    "MODEL_PATH_OPENVINO",
    "INFERENCE_DEVICE",
    "IMGSZ",
    "STARTUP_WARMUP_RUNS",

    # Detection
    "FIRE_THRESHOLD",
    "SMOKE_THRESHOLD",
    "FRAMES_PER_SCAN",
    "MIN_CONFIRM_FRAMES",
    "FRAME_SAMPLE_GAP_SEC",
    "CONSENSUS_IOU_THRESHOLD",

    # Distance
    "MIN_VALID_DISTANCE_M",
    "MAX_VALID_DISTANCE_M",

    # Site
    "CAMERA_LAT",
    "CAMERA_LON",

    # Alert
    "ALERT_COOLDOWN_SEC",
    "ALERT_DEDUP_IOU_THRESHOLD",

    # Dashboard
    "DASHBOARD_WRITE_INTERVAL_SEC",

    # Server
    "HEADLESS_MODE",
]


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

    ไม่แสดงค่าจริงออกหน้าจอ
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
# Host / Operating System
# ============================================================

def check_host(
    offline=False,
):

    system = (
        platform.system()
    )

    machine = (
        platform.machine()
        .lower()
    )

    # --------------------------------------------------------
    # Non-Linux development host
    # --------------------------------------------------------

    if system != "Linux":

        if offline:

            add(
                SKIP,
                "Production OS",
                (
                    f"{system} development host "
                    "| ตรวจ Debian 13 ตอน Deploy"
                ),
            )

        else:

            add(
                WARN,
                "Production OS",
                (
                    f"{system} "
                    "| Full run นี้เป็น Field Test "
                    "ไม่ใช่ Production READY"
                ),
            )

        return


    # --------------------------------------------------------
    # Linux architecture
    # --------------------------------------------------------

    if machine in {
        "x86_64",
        "amd64",
    }:

        add(
            PASS,
            "Architecture",
            machine,
        )

    else:

        status = (
            WARN
            if offline
            else FAIL
        )

        add(
            status,
            "Architecture",
            (
                f"{machine} "
                "| Production target=x86_64"
            ),
        )


    # --------------------------------------------------------
    # Linux distribution
    # --------------------------------------------------------

    os_release = Path(
        "/etc/os-release"
    )

    if not os_release.exists():

        status = (
            WARN
            if offline
            else FAIL
        )

        add(
            status,
            "Production OS",
            "/etc/os-release not found",
        )

        return

    values = {}

    try:

        for line in (
            os_release
            .read_text(
                encoding="utf-8"
            )
            .splitlines()
        ):

            if (
                "="
                not in line
            ):
                continue

            key, value = (
                line.split(
                    "=",
                    1,
                )
            )

            values[
                key.strip()
            ] = (
                value
                .strip()
                .strip('"')
            )

    except OSError as exc:

        add(
            FAIL,
            "Production OS",
            str(
                exc
            ),
        )

        return

    distro_id = (
        values
        .get(
            "ID",
            "",
        )
        .lower()
    )

    version_id = (
        values
        .get(
            "VERSION_ID",
            "",
        )
    )

    if (
        distro_id == "debian"
        and
        version_id == "13"
    ):

        add(
            PASS,
            "Production OS",
            "Debian 13",
        )

    else:

        status = (
            WARN
            if offline
            else FAIL
        )

        add(
            status,
            "Production OS",
            (
                f"{distro_id or 'unknown'} "
                f"{version_id or 'unknown'} "
                "| Production baseline=Debian 13"
            ),
        )


# ============================================================
# Config validation
# ============================================================

def check_config_validation():

    try:

        validate_runtime_config()

    except Exception as exc:

        add(
            FAIL,
            "Runtime config validation",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return

    add(
        PASS,
        "Runtime config validation",
        "config.py validation passed",
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

        "PyTorch":
            "torch",

        "torchvision":
            "torchvision",

        "Ultralytics":
            "ultralytics",

        "psutil":
            "psutil",

        "Flask":
            "flask",

        "Waitress":
            "waitress",
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

        return

    add(
        PASS,
        "Dependencies",
        "Runtime packages พร้อม",
    )


# ============================================================
# Waitress
# ============================================================

def check_waitress():

    # --------------------------------------------------------
    # Python package
    # --------------------------------------------------------

    if (
        importlib.util.find_spec(
            "waitress"
        )
        is None
    ):

        add(
            FAIL,
            "Waitress",
            "Python package not found",
        )

        return

    try:

        version = (
            importlib.metadata.version(
                "waitress"
            )
        )

    except Exception:

        version = "unknown"

    add(
        PASS,
        "Waitress package",
        version,
    )


    # --------------------------------------------------------
    # Console launcher
    # --------------------------------------------------------

    python_dir = (
        Path(
            sys.executable
        )
        .resolve()
        .parent
    )

    candidates = [

        python_dir
        / "waitress-serve",

        python_dir
        / "waitress-serve.exe",
    ]

    launcher = next(
        (
            candidate
            for candidate
            in candidates
            if candidate.exists()
        ),
        None,
    )

    if launcher is None:

        which_path = (
            shutil.which(
                "waitress-serve"
            )
        )

        if which_path:

            launcher = Path(
                which_path
            )

    if launcher is None:

        add(
            FAIL,
            "Waitress launcher",
            (
                "ไม่พบ waitress-serve "
                "ใน Python environment"
            ),
        )

        return

    add(
        PASS,
        "Waitress launcher",
        launcher.name,
    )


# ============================================================
# Dashboard WSGI
# ============================================================

def check_dashboard_wsgi():

    try:

        from app import (
            app as flask_app
        )

    except Exception as exc:

        add(
            FAIL,
            "Dashboard WSGI",
            (
                "โหลด app:app ไม่สำเร็จ "
                f"| {type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    # --------------------------------------------------------
    # Flask object
    # --------------------------------------------------------

    if not hasattr(
        flask_app,
        "wsgi_app",
    ):

        add(
            FAIL,
            "Dashboard WSGI",
            (
                "app object "
                "ไม่ใช่ Flask WSGI application"
            ),
        )

        return


    # --------------------------------------------------------
    # Required routes
    # --------------------------------------------------------

    routes = {
        rule.rule
        for rule
        in flask_app.url_map.iter_rules()
    }

    required_routes = {
        "/",
        "/api/status",
    }

    missing_routes = (
        required_routes
        - routes
    )

    if missing_routes:

        add(
            FAIL,
            "Dashboard routes",
            (
                "ขาด: "
                + ", ".join(
                    sorted(
                        missing_routes
                    )
                )
            ),
        )

        return

    add(
        PASS,
        "Dashboard WSGI",
        "app:app",
    )

    add(
        PASS,
        "Dashboard routes",
        "/ + /api/status",
    )


# ============================================================
# Deployment files
# ============================================================

def check_deployment_files():

    required = [

        DEPLOY_DIR
        / "install.sh",

        DEPLOY_DIR
        / "production.env.example",

        DEPLOY_DIR
        / DETECTION_UNIT_NAME,

        DEPLOY_DIR
        / DASHBOARD_UNIT_NAME,
    ]

    missing = [

        path.name

        for path
        in required

        if not path.is_file()
    ]

    if missing:

        add(
            FAIL,
            "Deployment files",
            (
                "ขาด: "
                + ", ".join(
                    missing
                )
            ),
        )

        return

    add(
        PASS,
        "Deployment files",
        "ครบ",
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


    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Offline
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Full
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Local .env warning
    # --------------------------------------------------------

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

    if offline:

        add(
            SKIP,
            "Production env file",
            "Offline mode",
        )

        return


    # --------------------------------------------------------
    # Development / non-Linux
    # --------------------------------------------------------

    if (
        platform.system()
        != "Linux"
    ):

        add(
            SKIP,
            "Production env file",
            (
                "Non-Linux host "
                "| ตรวจจริงบน Debian"
            ),
        )

        return


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


    # --------------------------------------------------------
    # Permissions
    # --------------------------------------------------------

    mode = stat.S_IMODE(
        info.st_mode
    )

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
                "| Group/Others "
                "ต้องไม่มีสิทธิ์"
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


    # --------------------------------------------------------
    # Root ownership
    # --------------------------------------------------------

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
            FAIL,
            "Production env owner",
            (
                "ต้องเป็น root "
                "บน Production"
            ),
        )


# ============================================================
# systemd units
# ============================================================

def check_systemd_units(
    offline=False,
):

    if offline:

        add(
            SKIP,
            "Installed systemd units",
            "Offline mode",
        )

        return

    if (
        platform.system()
        != "Linux"
    ):

        add(
            SKIP,
            "Installed systemd units",
            "Non-Linux host",
        )

        return


    detection_unit = (
        SYSTEMD_DIR
        / DETECTION_UNIT_NAME
    )

    dashboard_unit = (
        SYSTEMD_DIR
        / DASHBOARD_UNIT_NAME
    )

    missing = [

        path.name

        for path
        in (
            detection_unit,
            dashboard_unit,
        )

        if not path.is_file()
    ]

    if missing:

        add(
            FAIL,
            "Installed systemd units",
            (
                "ขาด: "
                + ", ".join(
                    missing
                )
            ),
        )

        return

    add(
        PASS,
        "Installed systemd units",
        "Detection + Dashboard",
    )


    # --------------------------------------------------------
    # systemd-analyze verify
    # --------------------------------------------------------

    executable = (
        shutil.which(
            "systemd-analyze"
        )
    )

    if not executable:

        add(
            WARN,
            "systemd unit validation",
            "ไม่พบ systemd-analyze",
        )

        return

    try:

        result = subprocess.run(
            [
                executable,
                "verify",
                str(
                    detection_unit
                ),
                str(
                    dashboard_unit
                ),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
        )

    except Exception as exc:

        add(
            FAIL,
            "systemd unit validation",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return

    if result.returncode == 0:

        add(
            PASS,
            "systemd unit validation",
            "systemd-analyze verify passed",
        )

        return

    detail = (
        result.stderr.strip()
        or result.stdout.strip()
        or (
            f"returncode="
            f"{result.returncode}"
        )
    )

    first_line = (
        detail.splitlines()[0]
        if detail
        else "validation failed"
    )

    add(
        FAIL,
        "systemd unit validation",
        first_line,
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


    # --------------------------------------------------------
    # Backend
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Device empty
    # --------------------------------------------------------

    if not device:

        add(
            FAIL,
            "Inference device",
            "INFERENCE_DEVICE ว่าง",
        )

        return False


    # --------------------------------------------------------
    # PyTorch production baseline
    # --------------------------------------------------------

    if backend == "pt":

        if device != "cpu":

            add(
                FAIL,
                "Inference device",
                (
                    f"pt -> {device} "
                    "| Production baseline "
                    "ต้องใช้ CPU"
                ),
            )

            return False

        add(
            PASS,
            "Inference device",
            "pt -> cpu",
        )

        return True


    # --------------------------------------------------------
    # OpenVINO
    # --------------------------------------------------------
    #
    # ไม่ hard-code Device String
    # เป็น intel:cpu
    #
    # Preferred baseline:
    #
    #     INFERENCE_DEVICE=cpu
    #
    # หากใช้รูปแบบอื่นที่มีคำว่า cpu
    # จะให้ Full AI inference เป็นตัวตัดสิน
    #
    # --------------------------------------------------------

    if device == "cpu":

        add(
            PASS,
            "Inference device",
            (
                "openvino -> cpu "
                "| validate again by inference"
            ),
        )

        return True

    if "cpu" in device:

        add(
            WARN,
            "Inference device",
            (
                f"openvino -> {device} "
                "| exact syntax จะถูกตรวจ "
                "ด้วย Full AI inference"
            ),
        )

        return True

    add(
        FAIL,
        "Inference device",
        (
            f"openvino -> {device} "
            "| Production baseline "
            "ต้องใช้ CPU"
        ),
    )

    return False


# ============================================================
# Runtime Parameters
# ============================================================

def check_runtime_parameters(
    offline=False,
):

    # --------------------------------------------------------
    # Camera HTTP port
    # --------------------------------------------------------

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
            str(
                CAMERA_PORT
            ),
        )


    # --------------------------------------------------------
    # RTSP port
    # --------------------------------------------------------

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
            str(
                RTSP_PORT
            ),
        )


    # --------------------------------------------------------
    # RTSP path
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # AI image size
    # --------------------------------------------------------

    if IMGSZ >= 32:

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
            (
                f"{IMGSZ} "
                "| ต้อง >= 32"
            ),
        )


    # --------------------------------------------------------
    # AI warm-up
    # --------------------------------------------------------

    if STARTUP_WARMUP_RUNS >= 0:

        add(
            PASS,
            "AI startup warm-up",
            str(
                STARTUP_WARMUP_RUNS
            ),
        )

    else:

        add(
            FAIL,
            "AI startup warm-up",
            (
                "STARTUP_WARMUP_RUNS "
                "ต้อง >= 0"
            ),
        )


    # --------------------------------------------------------
    # Frames / scan
    # --------------------------------------------------------

    if FRAMES_PER_SCAN >= 1:

        add(
            PASS,
            "Frames per scan",
            str(
                FRAMES_PER_SCAN
            ),
        )

    else:

        add(
            FAIL,
            "Frames per scan",
            (
                "FRAMES_PER_SCAN "
                "ต้อง >= 1"
            ),
        )


    # --------------------------------------------------------
    # Confirmation frames
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Frame sample gap
    # --------------------------------------------------------

    if (
        finite(
            FRAME_SAMPLE_GAP_SEC
        )
        and
        FRAME_SAMPLE_GAP_SEC >= 0.0
    ):

        add(
            PASS,
            "Frame sample gap",
            (
                f"{FRAME_SAMPLE_GAP_SEC:.3f}s"
            ),
        )

    else:

        add(
            FAIL,
            "Frame sample gap",
            str(
                FRAME_SAMPLE_GAP_SEC
            ),
        )


    # --------------------------------------------------------
    # Fire / Smoke thresholds
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Consensus IoU
    # --------------------------------------------------------

    if (
        finite(
            CONSENSUS_IOU_THRESHOLD
        )
        and
        0.0
        <= CONSENSUS_IOU_THRESHOLD
        <= 1.0
    ):

        add(
            PASS,
            "Consensus IoU",
            (
                f"{CONSENSUS_IOU_THRESHOLD:.2f}"
            ),
        )

    else:

        add(
            FAIL,
            "Consensus IoU",
            str(
                CONSENSUS_IOU_THRESHOLD
            ),
        )


    # --------------------------------------------------------
    # PTZ / Frame synchronization
    # --------------------------------------------------------

    ptz_timing_ok = (

        finite(
            DEG_PER_SEC
        )
        and
        DEG_PER_SEC > 0.0

        and

        finite(
            PTZ_BUFFER_SEC
        )
        and
        PTZ_BUFFER_SEC >= 0.0

        and

        finite(
            INITIAL_PRESET_WAIT_SEC
        )
        and
        INITIAL_PRESET_WAIT_SEC >= 0.0

        and

        finite(
            STABLE_DIFF_THRESHOLD
        )
        and
        STABLE_DIFF_THRESHOLD >= 0.0

        and

        STABLE_REQUIRED_PAIRS >= 1

        and

        finite(
            STABLE_TIMEOUT_SEC
        )
        and
        STABLE_TIMEOUT_SEC > 0.0

        and

        POST_MOVE_FRESH_FRAMES >= 1
    )

    if ptz_timing_ok:

        add(
            PASS,
            "PTZ/frame timing",
            (
                f"speed="
                f"{DEG_PER_SEC:.2f}deg/s "
                f"| buffer="
                f"{PTZ_BUFFER_SEC:.2f}s "
                f"| stablePairs="
                f"{STABLE_REQUIRED_PAIRS}"
            ),
        )

    else:

        add(
            FAIL,
            "PTZ/frame timing",
            (
                "PTZ / stability "
                "configuration ไม่ถูกต้อง"
            ),
        )


    # --------------------------------------------------------
    # Valid distance range
    # --------------------------------------------------------

    if (
        finite(
            MIN_VALID_DISTANCE_M
        )
        and
        finite(
            MAX_VALID_DISTANCE_M
        )
        and
        MIN_VALID_DISTANCE_M > 0.0
        and
        MAX_VALID_DISTANCE_M
        > MIN_VALID_DISTANCE_M
    ):

        add(
            PASS,
            "Valid distance range",
            (
                f"{MIN_VALID_DISTANCE_M:.2f}"
                "-"
                f"{MAX_VALID_DISTANCE_M:.2f}m"
            ),
        )

    else:

        add(
            FAIL,
            "Valid distance range",
            (
                "MIN/MAX_VALID_DISTANCE_M "
                "ไม่ถูกต้อง"
            ),
        )


    # --------------------------------------------------------
    # Alert cooldown
    # --------------------------------------------------------

    if (
        finite(
            ALERT_COOLDOWN_SEC
        )
        and
        ALERT_COOLDOWN_SEC >= 0.0
    ):

        add(
            PASS,
            "Alert cooldown",
            (
                f"{ALERT_COOLDOWN_SEC:.1f}s"
            ),
        )

    else:

        add(
            FAIL,
            "Alert cooldown",
            str(
                ALERT_COOLDOWN_SEC
            ),
        )


    # --------------------------------------------------------
    # Alert dedup IoU
    # --------------------------------------------------------

    if (
        finite(
            ALERT_DEDUP_IOU_THRESHOLD
        )
        and
        0.0
        <= ALERT_DEDUP_IOU_THRESHOLD
        <= 1.0
    ):

        add(
            PASS,
            "Alert dedup IoU",
            (
                f"{ALERT_DEDUP_IOU_THRESHOLD:.2f}"
            ),
        )

    else:

        add(
            FAIL,
            "Alert dedup IoU",
            str(
                ALERT_DEDUP_IOU_THRESHOLD
            ),
        )


    # --------------------------------------------------------
    # Dashboard write interval
    # --------------------------------------------------------

    if (
        finite(
            DASHBOARD_WRITE_INTERVAL_SEC
        )
        and
        DASHBOARD_WRITE_INTERVAL_SEC > 0.0
    ):

        add(
            PASS,
            "Dashboard write interval",
            (
                f"{DASHBOARD_WRITE_INTERVAL_SEC:.2f}s"
            ),
        )

    else:

        add(
            FAIL,
            "Dashboard write interval",
            str(
                DASHBOARD_WRITE_INTERVAL_SEC
            ),
        )


    # --------------------------------------------------------
    # Headless
    # --------------------------------------------------------

    if HEADLESS_MODE:

        add(
            PASS,
            "Headless mode",
            "Enabled",
        )

    elif offline:

        add(
            WARN,
            "Headless mode",
            (
                "Disabled "
                "| Production Server "
                "ควรใช้ HEADLESS_MODE=1"
            ),
        )

    else:

        add(
            FAIL,
            "Headless mode",
            (
                "Production Server "
                "ต้องใช้ HEADLESS_MODE=1"
            ),
        )


# ============================================================
# Camera / Site configuration
# ============================================================

def check_config(
    offline=False,
):

    # --------------------------------------------------------
    # Resolution
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # HFOV
    # --------------------------------------------------------

    if (
        finite(
            HFOV_DEG
        )
        and
        0.0
        < HFOV_DEG
        < 180.0
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


    # --------------------------------------------------------
    # Camera coordinates
    # --------------------------------------------------------

    coordinates_valid = (

        finite(
            CAMERA_LAT
        )

        and

        finite(
            CAMERA_LON
        )

        and

        -90.0
        <= CAMERA_LAT
        <= 90.0

        and

        -180.0
        <= CAMERA_LON
        <= 180.0
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

    elif offline:

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


    # --------------------------------------------------------
    # PTZ preset config
    # --------------------------------------------------------

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

    sweep_ok = all(
        preset
        in expected_presets

        for preset
        in SWEEP_SEQUENCE
    )

    if (
        pan_ok
        and
        bearing_ok
        and
        sweep_ok
    ):

        add(
            PASS,
            "PTZ preset config",
            (
                "Preset 1-9 ครบ "
                "| Sweep valid"
            ),
        )

    else:

        add(
            FAIL,
            "PTZ preset config",
            (
                "Preset / Sweep "
                "configuration ไม่ถูกต้อง"
            ),
        )


    # --------------------------------------------------------
    # Camera IP
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # RTSP config
    # --------------------------------------------------------

    if camera_ip_valid:

        add(
            PASS,
            "RTSP config",
            (
                f"port="
                f"{RTSP_PORT} "
                f"| path="
                f"{RTSP_PATH}"
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


    # --------------------------------------------------------
    # PTZ HTTP config
    # --------------------------------------------------------

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
                    "ที่ Site จริง"
                ),
            )

        else:

            add(
                FAIL,
                "Bearing calibration",
                (
                    "ไม่พบ site.json "
                    "-> รัน calibrate_bearing.py"
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


    # --------------------------------------------------------
    # Saved resolution
    # --------------------------------------------------------

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
                    "ที่ Site จริง"
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


    # --------------------------------------------------------
    # H / K
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Resolution
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Points
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Detail
    # --------------------------------------------------------

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

        return


    # --------------------------------------------------------
    # Model path
    # --------------------------------------------------------

    if backend == "pt":

        model_path = Path(
            MODEL_PATH_PT
        )

    else:

        model_path = Path(
            MODEL_PATH_OPENVINO
        )


        # ----------------------------------------------------
        # OpenVINO package
        # ----------------------------------------------------

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

        try:

            openvino_version = (
                importlib.metadata.version(
                    "openvino"
                )
            )

        except Exception:

            openvino_version = (
                "available"
            )

        add(
            PASS,
            "OpenVINO package",
            openvino_version,
        )


    # --------------------------------------------------------
    # Model path exists
    # --------------------------------------------------------

    if not model_path.exists():

        add(
            FAIL,
            "AI model",
            (
                "ไม่พบ Model Path "
                f"| backend={backend}"
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


    # --------------------------------------------------------
    # Offline
    # --------------------------------------------------------

    if not load_model:

        add(
            SKIP,
            "AI model load",
            "Offline mode",
        )

        add(
            SKIP,
            "AI inference",
            "Offline mode",
        )

        return


    # --------------------------------------------------------
    # Load + class validation + inference
    # --------------------------------------------------------

    try:

        import numpy as np

        from ultralytics import (
            YOLO
        )


        # ----------------------------------------------------
        # Model load
        # ----------------------------------------------------

        load_start = (
            time.perf_counter()
        )

        model = YOLO(
            str(
                model_path
            )
        )

        load_ms = (
            time.perf_counter()
            - load_start
        ) * 1000.0

        add(
            PASS,
            "AI model load",
            (
                f"{load_ms:.1f} ms"
            ),
        )


        # ----------------------------------------------------
        # Classes
        # ----------------------------------------------------

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

            return


        # ----------------------------------------------------
        # Safe synthetic inference smoke test
        # ----------------------------------------------------
        #
        # ใช้ภาพดำที่สร้างใน Memory เท่านั้น
        #
        # ทดสอบเฉพาะว่า:
        #
        # Model + Backend + Device + IMGSZ
        #
        # สามารถ Inference ได้จริง
        #
        # ไม่ใช่ Accuracy Test
        #
        # ----------------------------------------------------

        frame = np.zeros(
            (
                FRAME_HEIGHT,
                FRAME_WIDTH,
                3,
            ),
            dtype=np.uint8,
        )

        confidence = min(
            float(
                value
            )

            for value
            in CLASS_THRESHOLDS.values()
        )

        inference_start = (
            time.perf_counter()
        )

        prediction = model.predict(
            source=frame,
            imgsz=IMGSZ,
            conf=confidence,
            device=INFERENCE_DEVICE,
            verbose=False,
        )

        inference_ms = (
            time.perf_counter()
            - inference_start
        ) * 1000.0

        if prediction is None:

            add(
                FAIL,
                "AI inference",
                (
                    "model.predict() "
                    "ไม่คืนผลลัพธ์"
                ),
            )

            return

        add(
            PASS,
            "AI inference",
            (
                f"backend={backend} "
                f"| device={INFERENCE_DEVICE} "
                f"| {inference_ms:.1f} ms"
            ),
        )


    except Exception as exc:

        add(
            FAIL,
            "AI model/inference",
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


    # --------------------------------------------------------
    # Connect without PTZ movement
    # --------------------------------------------------------

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


            # ------------------------------------------------
            # Timeout
            # ------------------------------------------------

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


            # ------------------------------------------------
            # Resolution
            # ------------------------------------------------

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


            # ------------------------------------------------
            # Frame age
            # ------------------------------------------------

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


    # --------------------------------------------------------
    # Fail
    # --------------------------------------------------------

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
                    "ก่อนรัน Production Runtime"
                )
            )

        return 1


    # --------------------------------------------------------
    # Offline
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Full on non-Linux
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Full on Linux Production
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # CLI
    # --------------------------------------------------------

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
            "ตรวจ Software/Configuration "
            "โดยไม่โหลด AI Model จริง "
            "และไม่เชื่อม RTSP"
        ),
    )

    parser.add_argument(
        "--camera-timeout",
        type=float,
        default=10.0,
        help=(
            "RTSP timeout สำหรับ Full mode "
            "(default: 10 seconds)"
        ),
    )

    args = (
        parser.parse_args()
    )

    if (
        not math.isfinite(
            args.camera_timeout
        )
        or
        args.camera_timeout <= 0
    ):

        parser.error(
            "--camera-timeout must be > 0"
        )


    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print(
        "=" * 72
    )

    print(
        "Smart Fire Detection v2 "
        "- Production Preflight"
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
        f"Python  : "
        f"{platform.python_version()}"
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
        "NO MOVEMENT"
    )

    print(
        "=" * 72
    )


    # ========================================================
    # Software / host
    # ========================================================

    check_python()

    check_host(
        offline=args.offline
    )

    check_config_validation()

    check_dependencies()

    check_waitress()

    check_dashboard_wsgi()

    check_deployment_files()


    # ========================================================
    # Production Environment
    # ========================================================

    check_environment(
        offline=args.offline
    )

    check_production_environment_file(
        offline=args.offline
    )

    check_systemd_units(
        offline=args.offline
    )


    # ========================================================
    # Credentials
    # ========================================================

    check_camera_credentials(
        offline=args.offline
    )


    # ========================================================
    # Backend / Device
    # ========================================================

    check_backend_device()


    # ========================================================
    # Runtime Parameters
    # ========================================================

    check_runtime_parameters(
        offline=args.offline
    )


    # ========================================================
    # Basic Configuration
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
    # Camera / RTSP
    # ========================================================

    if args.offline:

        add(
            SKIP,
            "RTSP camera",
            "Offline mode",
        )

    else:

        check_camera(
            timeout=(
                args.camera_timeout
            )
        )


    # ========================================================
    # Summary
    # ========================================================

    return summary(
        offline=args.offline
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
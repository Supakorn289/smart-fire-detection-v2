#!/usr/bin/env python3
# preflight.py

"""
Smart Fire Detection v2
Production Preflight Checker

Final AI Model:
    R3-E6 Release V1

OFFLINE MODE
------------
- ตรวจ Python
- ตรวจ Dependencies
- ตรวจ Dependency conflict
- ตรวจ Runtime Configuration
- ตรวจ Final Model Contract
- ตรวจ Model Path
- ตรวจ SHA256 ของ Final PT
- ตรวจ Deployment files
- ตรวจ Calibration files ที่มีอยู่
- ไม่โหลด YOLO Model
- ไม่เชื่อม RTSP
- ไม่สั่ง PTZ

FULL MODE
---------
- ทำทุกอย่างจาก OFFLINE
- ตรวจ Production Environment
- ตรวจ systemd
- โหลด Final Model หลัง SHA PASS
- ตรวจ Exact Class Contract
- ทดสอบ Final Inference Contract
- ตรวจ RTSP Camera
- ไม่สั่ง PTZ หมุน

ไฟล์นี้จะไม่:
- Train Model
- Fine-tune Model
- Quantize Model
- Save Model
- แก้ Model Artifact
- สร้าง Calibration ใหม่
- แก้ Environment
- Start systemd service
- พิมพ์ Password / Token
"""

import argparse
import hashlib
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

    FINAL_MODEL_RELEASE,
    EXPECTED_MODEL_SHA256,
    EXPECTED_MODEL_CLASSES,
    EXPECTED_ULTRALYTICS_VERSION,
    REFERENCE_PYTORCH_VERSION,

    MODEL_BACKEND,
    MODEL_PATH_PT,
    INFERENCE_DEVICE,

    IMGSZ,
    MODEL_NMS_IOU,
    MODEL_MAX_DET,
    MODEL_RECT,
    MODEL_BATCH,
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
    validate_final_model_contract,
)


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
# Project dependency contract
# ============================================================

EXPECTED_OPENCV_DISTRIBUTION = (
    "opencv-python"
)

EXPECTED_OPENCV_VERSION = (
    "4.12.0.88"
)

PROJECT_TORCHVISION_VERSION = (
    "0.26.0"
)


OPENCV_DISTRIBUTIONS = (
    "opencv-python",
    "opencv-python-headless",
    "opencv-contrib-python",
    "opencv-contrib-python-headless",
)


# ============================================================
# Production Environment Variables
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

    # Camera Geometry
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "HFOV_DEG",

    # PTZ / Frame sync
    "DEG_PER_SEC",
    "PTZ_BUFFER_SEC",
    "INITIAL_PRESET_WAIT_SEC",
    "STABLE_DIFF_THRESHOLD",
    "STABLE_REQUIRED_PAIRS",
    "STABLE_TIMEOUT_SEC",
    "POST_MOVE_FRESH_FRAMES",

    # Final AI Runtime
    "MODEL_BACKEND",
    "MODEL_PATH_PT",
    "INFERENCE_DEVICE",

    "IMGSZ",
    "MODEL_NMS_IOU",
    "MODEL_MAX_DET",
    "MODEL_RECT",
    "MODEL_BATCH",

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

    # Telegram
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",

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


def exact_float(
    value,
    expected,
    tolerance=1e-12,
):

    try:

        return math.isclose(
            float(
                value
            ),
            float(
                expected
            ),
            rel_tol=0.0,
            abs_tol=tolerance,
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
        name
        in os.environ
    )


def env_has_value(
    name,
):

    if (
        name
        not in os.environ
    ):

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

    text = (
        str(
            value
        )
        .strip()
        .lower()
    )

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


    if (
        text
        in exact_placeholders
    ):

        return True


    fragments = [

        "change_me",
        "replace_me",

        "<change",
        "<replace",

        "your_",
    ]


    return any(
        fragment
        in text
        for fragment
        in fragments
    )


def sha256_file(
    path,
):

    path = Path(
        path
    )

    digest = (
        hashlib.sha256()
    )


    with path.open(
        "rb"
    ) as handle:

        while True:

            chunk = (
                handle.read(
                    1024
                    * 1024
                )
            )

            if not chunk:

                break

            digest.update(
                chunk
            )


    return (
        digest.hexdigest()
    )


def distribution_version(
    name,
):

    try:

        return (
            importlib.metadata.version(
                name
            )
        )

    except (
        importlib.metadata.PackageNotFoundError,
    ):

        return None

    except Exception:

        return None


def normalize_model_names(
    names_object,
):

    if isinstance(
        names_object,
        dict,
    ):

        normalized = {}

        for (
            key,
            value,
        ) in names_object.items():

            normalized[
                int(
                    key
                )
            ] = (
                str(
                    value
                )
                .strip()
                .lower()
            )


        return normalized


    if isinstance(
        names_object,
        (
            list,
            tuple,
        ),
    ):

        return {

            index:
                (
                    str(
                        value
                    )
                    .strip()
                    .lower()
                )

            for (
                index,
                value,
            ) in enumerate(
                names_object
            )
        }


    raise TypeError(
        "Unsupported model.names type: "
        f"{type(names_object).__name__}"
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
    # Development host
    # --------------------------------------------------------

    if (
        system
        != "Linux"
    ):

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
    # Architecture
    # --------------------------------------------------------

    if (
        machine
        in {
            "x86_64",
            "amd64",
        }
    ):

        add(
            PASS,
            "Architecture",
            machine,
        )

    else:

        add(
            (
                WARN
                if offline
                else FAIL
            ),
            "Architecture",
            (
                f"{machine} "
                "| Production target=x86_64"
            ),
        )


    # --------------------------------------------------------
    # Debian version
    # --------------------------------------------------------

    os_release = Path(
        "/etc/os-release"
    )


    if not os_release.exists():

        add(
            (
                WARN
                if offline
                else FAIL
            ),
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
        distro_id
        == "debian"
        and
        version_id
        == "13"
    ):

        add(
            PASS,
            "Production OS",
            "Debian 13",
        )

    else:

        add(
            (
                WARN
                if offline
                else FAIL
            ),
            "Production OS",
            (
                f"{distro_id or 'unknown'} "
                f"{version_id or 'unknown'} "
                "| Production baseline=Debian 13"
            ),
        )


# ============================================================
# Configuration Validation
# ============================================================

def check_config_validation():

    # --------------------------------------------------------
    # Generic Runtime Configuration
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Final Model R3-E6 Contract
    # --------------------------------------------------------

    try:

        validate_final_model_contract()

    except Exception as exc:

        add(
            FAIL,
            "Final model contract",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    add(
        PASS,
        "Final model contract",
        (
            f"{FINAL_MODEL_RELEASE} "
            "contract passed"
        ),
    )


# ============================================================
# Dependencies
# ============================================================

def check_dependencies():

    packages = {

        "NumPy":
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


    missing = [

        display_name

        for (
            display_name,
            module_name,
        ) in packages.items()

        if (
            importlib.util.find_spec(
                module_name
            )
            is None
        )
    ]


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


    # ========================================================
    # OpenCV distribution conflict
    # ========================================================

    installed_opencv = {}


    for distribution in (
        OPENCV_DISTRIBUTIONS
    ):

        version = (
            distribution_version(
                distribution
            )
        )

        if (
            version
            is not None
        ):

            installed_opencv[
                distribution
            ] = (
                version
            )


    if (
        len(
            installed_opencv
        )
        != 1
    ):

        if installed_opencv:

            detail = ", ".join(

                f"{name}={version}"

                for (
                    name,
                    version,
                ) in installed_opencv.items()
            )

        else:

            detail = (
                "ไม่พบ OpenCV distribution"
            )


        add(
            FAIL,
            "OpenCV distribution",
            (
                "ต้องมี OpenCV wheel family "
                "เพียง 1 ชุด | "
                f"{detail}"
            ),
        )


    else:

        (
            distribution,
            version,
        ) = next(
            iter(
                installed_opencv.items()
            )
        )


        if (
            distribution
            ==
            EXPECTED_OPENCV_DISTRIBUTION
            and
            version
            ==
            EXPECTED_OPENCV_VERSION
        ):

            add(
                PASS,
                "OpenCV distribution",
                (
                    f"{distribution}"
                    f"=={version}"
                ),
            )

        else:

            add(
                FAIL,
                "OpenCV distribution",
                (
                    f"พบ "
                    f"{distribution}"
                    f"=={version} "
                    "| ต้องใช้ "
                    f"{EXPECTED_OPENCV_DISTRIBUTION}"
                    f"=={EXPECTED_OPENCV_VERSION}"
                ),
            )


    # ========================================================
    # Ultralytics - STRICT Final Model Contract
    # ========================================================

    ultralytics_version = (
        distribution_version(
            "ultralytics"
        )
    )


    if (
        ultralytics_version
        ==
        EXPECTED_ULTRALYTICS_VERSION
    ):

        add(
            PASS,
            "Ultralytics version",
            ultralytics_version,
        )

    else:

        add(
            FAIL,
            "Ultralytics version",
            (
                "installed="
                f"{ultralytics_version or 'missing'} "
                "| required="
                f"{EXPECTED_ULTRALYTICS_VERSION}"
            ),
        )


    # ========================================================
    # PyTorch reference
    # ========================================================

    torch_version = (
        distribution_version(
            "torch"
        )
    )


    torch_base_version = (

        torch_version.split(
            "+",
            1,
        )[0]

        if torch_version

        else ""
    )


    if (
        torch_base_version
        ==
        REFERENCE_PYTORCH_VERSION
    ):

        add(
            PASS,
            "PyTorch reference",
            (
                torch_version
                or "unknown"
            ),
        )

    else:

        add(
            WARN,
            "PyTorch reference",
            (
                "installed="
                f"{torch_version or 'missing'} "
                "| reference="
                f"{REFERENCE_PYTORCH_VERSION}"
            ),
        )


    # ========================================================
    # torchvision
    # ========================================================
    #
    # Model Team ไม่มี authoritative exact version
    #
    # 0.26.0 ในส่วนนี้เป็น Project dependency
    # ไม่ใช่ Frozen Model Contract
    #
    # ========================================================

    torchvision_version = (
        distribution_version(
            "torchvision"
        )
    )


    if (
        torchvision_version
        ==
        PROJECT_TORCHVISION_VERSION
    ):

        add(
            PASS,
            "torchvision project version",
            torchvision_version,
        )

    else:

        add(
            WARN,
            "torchvision project version",
            (
                "installed="
                f"{torchvision_version or 'missing'} "
                "| project="
                f"{PROJECT_TORCHVISION_VERSION} "
                "| not a frozen Model Contract value"
            ),
        )


    # ========================================================
    # NumPy
    # ========================================================

    numpy_version = (
        distribution_version(
            "numpy"
        )
    )


    if numpy_version:

        add(
            PASS,
            "NumPy version",
            numpy_version,
        )


    # ========================================================
    # pip check
    # ========================================================

    try:

        completed = (
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "check",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                check=False,
            )
        )

    except Exception as exc:

        add(
            FAIL,
            "pip check",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    if (
        completed.returncode
        == 0
    ):

        add(
            PASS,
            "pip check",
            "No broken requirements",
        )

    else:

        detail = (
            completed.stdout.strip()
            or
            completed.stderr.strip()
            or
            (
                f"returncode="
                f"{completed.returncode}"
            )
        )


        add(
            FAIL,
            "pip check",
            (
                detail.splitlines()[0]
                if detail
                else "dependency check failed"
            ),
        )


# ============================================================
# Waitress
# ============================================================

def check_waitress():

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


    version = (
        distribution_version(
            "waitress"
        )
        or "unknown"
    )


    if (
        version
        == "3.0.2"
    ):

        add(
            PASS,
            "Waitress package",
            version,
        )

    else:

        add(
            FAIL,
            "Waitress package",
            (
                f"installed={version} "
                "| required=3.0.2"
            ),
        )


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


    if (
        launcher
        is None
    ):

        which_path = (
            shutil.which(
                "waitress-serve"
            )
        )


        if which_path:

            launcher = Path(
                which_path
            )


    if (
        launcher
        is None
    ):

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
                "ถูกกำหนดแบบ explicit"
            ),
        )


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
    # Local .env
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
    # Permission
    # --------------------------------------------------------

    mode = (
        stat.S_IMODE(
            info.st_mode
        )
    )


    if (
        mode
        & 0o077
    ):

        add(
            FAIL,
            "Production env permission",
            (
                f"permission={mode:04o} "
                "| Group/Others "
                "ต้องไม่มีสิทธิ์"
            ),
        )

    else:

        add(
            PASS,
            "Production env permission",
            (
                f"permission={mode:04o}"
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
# systemd
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

        completed = (
            subprocess.run(
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


    if (
        completed.returncode
        == 0
    ):

        add(
            PASS,
            "systemd unit validation",
            (
                "systemd-analyze "
                "verify passed"
            ),
        )

        return


    detail = (
        completed.stderr.strip()
        or
        completed.stdout.strip()
        or
        (
            f"returncode="
            f"{completed.returncode}"
        )
    )


    add(
        FAIL,
        "systemd unit validation",
        (
            detail.splitlines()[0]
            if detail
            else "validation failed"
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


    if (
        looks_like_placeholder(
            CAMERA_USER
        )
        or
        looks_like_placeholder(
            CAMERA_PWD
        )
    ):

        if offline:

            add(
                WARN,
                "Camera credentials",
                (
                    "พบค่าที่ดูเหมือน "
                    "Placeholder"
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
    # Final Release V1 = PT only
    # --------------------------------------------------------

    if (
        backend
        != "pt"
    ):

        add(
            FAIL,
            "AI backend",
            (
                f"{backend!r} "
                f"| Final {FINAL_MODEL_RELEASE} "
                "Production Runtime ต้องใช้ pt"
            ),
        )

        return False


    add(
        PASS,
        "AI backend",
        "pt",
    )


    # --------------------------------------------------------
    # CPU baseline
    # --------------------------------------------------------

    if (
        device
        != "cpu"
    ):

        add(
            FAIL,
            "Inference device",
            (
                f"pt -> "
                f"{device or '<empty>'} "
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


# ============================================================
# Runtime Parameters
# ============================================================

def check_runtime_parameters(
    offline=False,
):

    checks = [

        (
            1
            <= CAMERA_PORT
            <= 65535,
            "Camera HTTP port",
            str(
                CAMERA_PORT
            ),
        ),

        (
            1
            <= RTSP_PORT
            <= 65535,
            "RTSP port",
            str(
                RTSP_PORT
            ),
        ),

        (
            str(
                RTSP_PATH
            ).startswith(
                "/"
            ),
            "RTSP path",
            (
                "Format OK"
                if str(
                    RTSP_PATH
                ).startswith("/")
                else str(
                    RTSP_PATH
                )
            ),
        ),

        # Final Model Contract

        (
            IMGSZ == 768,
            "AI image size",
            (
                f"{IMGSZ} "
                "| required=768"
            ),
        ),

        (
            exact_float(
                MODEL_NMS_IOU,
                0.70,
            ),
            "Model NMS IoU",
            (
                f"{MODEL_NMS_IOU:.2f} "
                "| required=0.70"
            ),
        ),

        (
            MODEL_MAX_DET
            == 300,
            "Model max_det",
            (
                f"{MODEL_MAX_DET} "
                "| required=300"
            ),
        ),

        (
            MODEL_RECT
            is False,
            "Model rect",
            (
                f"{MODEL_RECT} "
                "| required=False"
            ),
        ),

        (
            MODEL_BATCH
            == 1,
            "Model batch",
            (
                f"{MODEL_BATCH} "
                "| required=1"
            ),
        ),

        (
            STARTUP_WARMUP_RUNS
            == 3,
            "AI startup warm-up",
            (
                f"{STARTUP_WARMUP_RUNS} "
                "| required=3"
            ),
        ),

        (
            FRAMES_PER_SCAN
            == 3,
            "Frames per scan",
            (
                f"{FRAMES_PER_SCAN} "
                "| required=3"
            ),
        ),

        (
            MIN_CONFIRM_FRAMES
            == 2,
            "Confirmation frames",
            (
                f"{MIN_CONFIRM_FRAMES}"
                f"/{FRAMES_PER_SCAN} "
                "| required=2/3"
            ),
        ),

        (
            exact_float(
                FRAME_SAMPLE_GAP_SEC,
                0.15,
            ),
            "Frame sample gap",
            (
                f"{FRAME_SAMPLE_GAP_SEC:.3f}s "
                "| required=0.150s"
            ),
        ),

        (
            exact_float(
                CLASS_THRESHOLDS.get(
                    "fire"
                ),
                0.25,
            ),
            "fire candidate threshold",
            (
                f"{CLASS_THRESHOLDS.get('fire')} "
                "| required=0.25"
            ),
        ),

        (
            exact_float(
                CLASS_THRESHOLDS.get(
                    "smoke"
                ),
                0.25,
            ),
            "smoke candidate threshold",
            (
                f"{CLASS_THRESHOLDS.get('smoke')} "
                "| required=0.25"
            ),
        ),

        (
            exact_float(
                CONSENSUS_IOU_THRESHOLD,
                0.30,
            ),
            "Consensus IoU",
            (
                f"{CONSENSUS_IOU_THRESHOLD:.2f} "
                "| required=0.30"
            ),
        ),
    ]


    for (
        okay,
        name,
        detail,
    ) in checks:

        add(
            (
                PASS
                if okay
                else FAIL
            ),
            name,
            detail,
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
    # Distance range
    # --------------------------------------------------------

    distance_range_ok = (

        finite(
            MIN_VALID_DISTANCE_M
        )

        and

        finite(
            MAX_VALID_DISTANCE_M
        )

        and

        MIN_VALID_DISTANCE_M
        > 0.0

        and

        MAX_VALID_DISTANCE_M
        > MIN_VALID_DISTANCE_M
    )


    if distance_range_ok:

        add(
            PASS,
            "Valid distance range",
            (
                f"{MIN_VALID_DISTANCE_M:.2f}"
                "-"
                f"{MAX_VALID_DISTANCE_M:.2f}"
                "m"
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

    cooldown_ok = (

        finite(
            ALERT_COOLDOWN_SEC
        )
        and
        ALERT_COOLDOWN_SEC >= 0.0
    )


    add(
        (
            PASS
            if cooldown_ok
            else FAIL
        ),
        "Alert cooldown",
        str(
            ALERT_COOLDOWN_SEC
        ),
    )


    # --------------------------------------------------------
    # Alert dedup
    # --------------------------------------------------------

    dedup_ok = (

        finite(
            ALERT_DEDUP_IOU_THRESHOLD
        )
        and
        0.0
        <= ALERT_DEDUP_IOU_THRESHOLD
        <= 1.0
    )


    add(
        (
            PASS
            if dedup_ok
            else FAIL
        ),
        "Alert dedup IoU",
        str(
            ALERT_DEDUP_IOU_THRESHOLD
        ),
    )


    # --------------------------------------------------------
    # Dashboard
    # --------------------------------------------------------

    dashboard_ok = (

        finite(
            DASHBOARD_WRITE_INTERVAL_SEC
        )
        and
        DASHBOARD_WRITE_INTERVAL_SEC
        > 0.0
    )


    add(
        (
            PASS
            if dashboard_ok
            else FAIL
        ),
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
# Camera / Site Configuration
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
    # PTZ presets
    # --------------------------------------------------------

    expected_presets = (
        set(
            range(
                1,
                10,
            )
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

        add(
            (
                SKIP
                if offline
                else FAIL
            ),
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
    # RTSP / PTZ configuration
    # --------------------------------------------------------

    if camera_ip_valid:

        add(
            PASS,
            "RTSP config",
            (
                f"port={RTSP_PORT} "
                f"| path={RTSP_PATH}"
            ),
        )

        add(
            PASS,
            "PTZ HTTP config",
            (
                f"port={CAMERA_PORT}"
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
            "RTSP config",
            "Camera IP ไม่พร้อม",
        )

        add(
            FAIL,
            "PTZ HTTP config",
            "Camera IP ไม่พร้อม",
        )


# ============================================================
# Camera Intrinsics
# ============================================================

def check_intrinsics(
    offline=False,
):

    path = (
        CALIBRATION_DIR
        / "camera_intrinsics.json"
    )


    if not path.exists():

        add(
            (
                WARN
                if offline
                else FAIL
            ),
            "Camera intrinsics",
            (
                "ไม่พบ "
                "camera_intrinsics.json"
            ),
        )

        return


    data = load_json(
        path
    )


    if (
        data
        is None
    ):

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
            (
                WARN
                if offline
                else FAIL
            ),
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


    if (
        difference
        <= 0.20
    ):

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


    if (
        data
        is None
    ):

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
        saved_width
        is not None
        and
        saved_height
        is not None
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


    if (
        data
        is None
    ):

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

        if (
            key
            not in data
        )
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


    if (
        points
        < 3
    ):

        add(
            FAIL,
            "Distance calibration",
            (
                f"มีเพียง "
                f"{points} points"
            ),
        )

        return


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

def check_telegram(
    offline=False,
):

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

        return


    if offline:

        add(
            WARN,
            "Telegram",
            (
                "ยังไม่ได้ตั้งค่าครบ "
                "| ต้องทดสอบจริง "
                "ก่อน Production"
            ),
        )

        return


    add(
        FAIL,
        "Telegram",
        (
            "Production ต้องมีทั้ง "
            "TELEGRAM_TOKEN และ "
            "TELEGRAM_CHAT_ID"
        ),
    )


# ============================================================
# Final AI Model R3-E6
# ============================================================

def check_model(
    load_model=True,
):

    # --------------------------------------------------------
    # Approved backend
    # --------------------------------------------------------

    if (
        str(
            MODEL_BACKEND
        )
        .strip()
        .lower()
        != "pt"
    ):

        add(
            FAIL,
            "AI model backend",
            (
                "Final Release V1 "
                "รองรับ Production PT เท่านั้น"
            ),
        )

        return


    # --------------------------------------------------------
    # Runtime artifact
    # --------------------------------------------------------

    model_path = (
        Path(
            MODEL_PATH_PT
        )
        .resolve()
    )


    if not model_path.is_file():

        add(
            FAIL,
            "AI model",
            (
                "ไม่พบ Final PT: "
                f"{model_path}"
            ),
        )

        return


    add(
        PASS,
        "AI model path",
        (
            "PT runtime artifact exists"
        ),
    )


    # ========================================================
    # SHA256 BEFORE YOLO LOAD
    # ========================================================

    try:

        actual_sha256 = (
            sha256_file(
                model_path
            )
        )

    except Exception as exc:

        add(
            FAIL,
            "AI model SHA256",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    if (
        actual_sha256.lower()
        !=
        EXPECTED_MODEL_SHA256.lower()
    ):

        add(
            FAIL,
            "AI model SHA256",
            (
                "HASH MISMATCH "
                "| expected="
                f"{EXPECTED_MODEL_SHA256} "
                "| actual="
                f"{actual_sha256}"
            ),
        )

        return


    add(
        PASS,
        "AI model SHA256",
        actual_sha256,
    )


    # --------------------------------------------------------
    # Offline
    # --------------------------------------------------------

    if not load_model:

        add(
            SKIP,
            "AI model class contract",
            (
                "Offline mode "
                "| SHA verified, "
                "model not loaded"
            ),
        )

        add(
            SKIP,
            "AI inference",
            "Offline mode",
        )

        return


    # ========================================================
    # Full load + exact class + inference
    # ========================================================

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


        model = (
            YOLO(
                str(
                    model_path
                )
            )
        )


        load_ms = (
            (
                time.perf_counter()
                - load_start
            )
            * 1000.0
        )


        add(
            PASS,
            "AI model load",
            (
                f"{load_ms:.1f} ms"
            ),
        )


        # ====================================================
        # Exact Class Contract
        # ====================================================

        names = (
            normalize_model_names(
                model.names
            )
        )


        if (
            names
            !=
            EXPECTED_MODEL_CLASSES
        ):

            add(
                FAIL,
                "AI model class contract",
                (
                    "expected="
                    f"{EXPECTED_MODEL_CLASSES} "
                    "| actual="
                    f"{names}"
                ),
            )

            return


        add(
            PASS,
            "AI model class contract",
            str(
                names
            ),
        )


        # ====================================================
        # Blank-frame Final Inference Contract
        # ====================================================

        frame = (
            np.zeros(
                (
                    FRAME_HEIGHT,
                    FRAME_WIDTH,
                    3,
                ),
                dtype=np.uint8,
            )
        )


        candidate_confidence = min(

            float(
                value
            )

            for value
            in CLASS_THRESHOLDS.values()
        )


        inference_start = (
            time.perf_counter()
        )


        prediction = (
            model.predict(
                source=frame,

                imgsz=IMGSZ,

                conf=(
                    candidate_confidence
                ),

                iou=(
                    MODEL_NMS_IOU
                ),

                max_det=(
                    MODEL_MAX_DET
                ),

                rect=(
                    MODEL_RECT
                ),

                device=(
                    INFERENCE_DEVICE
                ),

                verbose=False,
            )
        )


        inference_ms = (
            (
                time.perf_counter()
                - inference_start
            )
            * 1000.0
        )


        if (
            prediction
            is None
        ):

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
                "pt/cpu "
                f"| imgsz={IMGSZ} "
                f"| conf={candidate_confidence:.2f} "
                f"| iou={MODEL_NMS_IOU:.2f} "
                f"| max_det={MODEL_MAX_DET} "
                f"| rect={MODEL_RECT} "
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
#
# ไม่สั่ง PTZ หมุน
#
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


            # ------------------------------------------------
            # Timeout
            # ------------------------------------------------

            if (
                packet
                is None
            ):

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

            (
                height,
                width,
            ) = (
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
                    (
                        time.time()
                        - float(
                            packet.timestamp
                        )
                    ),
                )


                age_text = (
                    f"{frame_age:.3f}s"
                )


            except Exception:

                age_text = (
                    "unknown"
                )


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
    # FAIL
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
    # OFFLINE
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
    # FULL - Development host
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
    # FULL - Production Linux
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


    parser = (
        argparse.ArgumentParser(
            description=(
                "Smart Fire Detection v2 "
                "- Production Preflight "
                f"Final Model "
                f"{FINAL_MODEL_RELEASE}"
            )
        )
    )


    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "ตรวจ Software/Configuration "
            "+ Final Model SHA256 "
            "โดยไม่โหลด YOLO "
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
        args.camera_timeout
        <= 0
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
        f"Model   : "
        f"Final {FINAL_MODEL_RELEASE}"
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
    # Software / Host
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
    # Credentials / Runtime
    # ========================================================

    check_camera_credentials(
        offline=args.offline
    )

    check_backend_device()

    check_runtime_parameters(
        offline=args.offline
    )

    check_config(
        offline=args.offline
    )


    # ========================================================
    # Camera Geometry / Site Calibration
    # ========================================================

    check_intrinsics(
        offline=args.offline
    )

    check_bearing(
        offline=args.offline
    )

    check_distance(
        offline=args.offline
    )


    # ========================================================
    # Notification
    # ========================================================

    check_telegram(
        offline=args.offline
    )


    # ========================================================
    # Final AI Model
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
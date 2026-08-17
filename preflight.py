#!/usr/bin/env python3

import argparse
import importlib.util
import json
import math
import os
import platform
import sys
import time
from pathlib import Path

from config import (
    BASE_DIR,
    CALIBRATION_DIR,
    CAMERA_IP,
    CAMERA_LAT,
    CAMERA_LON,
    CAMERA_PORT,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    GLOBAL_DISTANCE_CALIBRATION,
    HFOV_DEG,
    MODEL_BACKEND,
    MODEL_PATH_OPENVINO,
    MODEL_PATH_PT,
    PRESET_BEARING_DEG,
    PRESET_PAN_DEG,
    RTSP_PATH,
    RTSP_PORT,
    SITE_CALIBRATION_FILE,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)


# ============================================================
# Result status
# ============================================================

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

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
# JSON helper
# ============================================================

def load_json(
    path,
):

    try:

        return json.loads(
            Path(
                path
            ).read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        add(
            FAIL,
            Path(
                path
            ).name,
            (
                "อ่าน JSON ไม่ได้: "
                f"{exc}"
            ),
        )

        return None


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


# ============================================================
# Python
# ============================================================

def check_python():

    version = (
        sys.version_info
    )

    text = (
        f"{version.major}."
        f"{version.minor}."
        f"{version.micro}"
    )

    # Project baseline = Python 3.12
    if (
        version.major == 3
        and
        version.minor == 12
    ):

        add(
            PASS,
            "Python",
            text,
        )

    else:

        add(
            FAIL,
            "Python",
            (
                f"{text} "
                "| ต้องการ Python 3.12"
            ),
        )


# ============================================================
# Dependencies
# ============================================================

def check_dependencies():

    packages = {
        "numpy": "numpy",
        "OpenCV": "cv2",
        "requests": "requests",
        "Ultralytics": "ultralytics",
        "psutil": "psutil",
        "Flask": "flask",
    }

    missing = []

    for (
        name,
        module,
    ) in packages.items():

        if (
            importlib.util.find_spec(
                module
            )
            is None
        ):

            missing.append(
                name
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
# Environment
# ============================================================

def check_environment(
    offline=False,
):

    # --------------------------------------------------------
    # Environment ที่ควรกำหนดบน Production
    # --------------------------------------------------------

    production_keys = [
        "CAMERA_IP",
        "CAMERA_USER",
        "CAMERA_PWD",
        "CAMERA_PORT",
        "RTSP_PORT",
        "RTSP_PATH",
        "HFOV_DEG",
        "CAMERA_LAT",
        "CAMERA_LON",
        "MODEL_BACKEND",
    ]

    missing = [
        key
        for key in production_keys
        if key not in os.environ
    ]

    # --------------------------------------------------------
    # Environment variables
    # --------------------------------------------------------

    if missing:

        if offline:

            add(
                WARN,
                "Environment",
                (
                    "Environment บางค่ายังไม่ได้กำหนด: "
                    + ", ".join(
                        missing
                    )
                    + " | Offline mode ยังทดสอบต่อได้"
                ),
            )

        else:

            add(
                WARN,
                "Environment",
                (
                    "Environment บางค่ายังไม่ได้กำหนด: "
                    + ", ".join(
                        missing
                    )
                ),
            )

    else:

        add(
            PASS,
            "Environment",
            (
                "Production variables "
                "หลักถูกกำหนดแล้ว"
            ),
        )

    # --------------------------------------------------------
    # .env check
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
                "ไม่ได้โหลด .env อัตโนมัติ "
                "| ต้อง Load ผ่าน "
                "Shell / IDE / systemd"
            ),
        )


# ============================================================
# Basic configuration
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
        0 < HFOV_DEG < 180
    ):

        add(
            PASS,
            "HFOV",
            f"{HFOV_DEG:.6f}°",
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
                "Latitude/Longitude "
                "format OK"
            ),
        )

    else:

        if offline:

            add(
                SKIP,
                "Camera coordinates",
                (
                    "ยังไม่ได้กำหนด Site GPS "
                    "| ต้องตั้งเมื่อ Deploy "
                    "Site จริง"
                ),
            )

        else:

            add(
                FAIL,
                "Camera coordinates",
                (
                    "ยังไม่ได้กำหนด "
                    "CAMERA_LAT / CAMERA_LON "
                    "หรือค่าพิกัดไม่ถูกต้อง"
                ),
            )

    # ========================================================
    # PTZ preset configuration
    # ========================================================

    expected = set(
        range(
            1,
            10,
        )
    )

    if (
        set(
            PRESET_PAN_DEG
        )
        == expected
        and
        set(
            PRESET_BEARING_DEG
        )
        == expected
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

    camera_ip_ready = bool(
        str(
            CAMERA_IP
        ).strip()
    )

    # ========================================================
    # RTSP config
    # ========================================================

    if camera_ip_ready:

        add(
            PASS,
            "RTSP config",
            (
                f"{CAMERA_IP}:"
                f"{RTSP_PORT}"
                f"{RTSP_PATH}"
            ),
        )

    else:

        if offline:

            add(
                SKIP,
                "RTSP config",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด "
                    "| Offline mode"
                ),
            )

        else:

            add(
                FAIL,
                "RTSP config",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด"
                ),
            )

    # ========================================================
    # PTZ HTTP config
    # ========================================================

    if camera_ip_ready:

        add(
            PASS,
            "PTZ HTTP config",
            (
                f"{CAMERA_IP}:"
                f"{CAMERA_PORT}"
            ),
        )

    else:

        if offline:

            add(
                SKIP,
                "PTZ HTTP config",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด "
                    "| Offline mode"
                ),
            )

        else:

            add(
                FAIL,
                "PTZ HTTP config",
                (
                    "CAMERA_IP "
                    "ยังไม่ได้กำหนด"
                ),
            )


# ============================================================
# Camera Intrinsics / FOV
# ============================================================

def check_intrinsics():

    path = (
        CALIBRATION_DIR
        / "camera_intrinsics.json"
    )

    # --------------------------------------------------------
    # Intrinsics file missing
    # --------------------------------------------------------

    if not path.exists():

        add(
            WARN,
            "Camera intrinsics",
            (
                "ไม่พบ "
                "camera_intrinsics.json "
                "| ต้องแน่ใจว่า "
                "HFOV_DEG ถูกต้อง"
            ),
        )

        return

    # --------------------------------------------------------
    # Load JSON
    # --------------------------------------------------------

    data = load_json(
        path
    )

    if data is None:

        return

    valid = bool(
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

    # --------------------------------------------------------
    # Production validation
    # --------------------------------------------------------

    if not valid:

        add(
            WARN,
            "Camera intrinsics",
            (
                "valid_for_production="
                "false"
            ),
        )

        return

    # --------------------------------------------------------
    # HFOV inside calibration
    # --------------------------------------------------------

    if not finite(
        calibrated_hfov
    ):

        add(
            WARN,
            "Camera intrinsics",
            (
                "ไม่พบ "
                "effective_hfov_deg"
            ),
        )

        return

    calibrated_hfov = float(
        calibrated_hfov
    )

    diff = abs(
        calibrated_hfov
        - HFOV_DEG
    )

    # --------------------------------------------------------
    # Allow small rounding difference
    # --------------------------------------------------------

    if diff <= 0.20:

        add(
            PASS,
            "Camera intrinsics",
            (
                f"Calibrated HFOV="
                f"{calibrated_hfov:.6f}° "
                f"| Runtime="
                f"{HFOV_DEG:.6f}°"
            ),
        )

    else:

        add(
            WARN,
            "Camera intrinsics",
            (
                f"Calibration="
                f"{calibrated_hfov:.6f}° "
                f"แต่ Runtime="
                f"{HFOV_DEG:.6f}°"
            ),
        )


# ============================================================
# Bearing calibration
# ============================================================

def check_bearing(
    offline=False,
):

    path = (
        SITE_CALIBRATION_FILE
    )

    # --------------------------------------------------------
    # Calibration file missing
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Load calibration
    # --------------------------------------------------------

    data = load_json(
        path
    )

    if data is None:

        return

    offset = data.get(
        "north_offset_deg"
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
    # Resolution check
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

            resolution_match = (
                int(
                    saved_width
                )
                == FRAME_WIDTH
                and
                int(
                    saved_height
                )
                == FRAME_HEIGHT
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

        if not resolution_match:

            add(
                FAIL,
                "Bearing calibration",
                (
                    "Resolution "
                    "ไม่ตรงกับ Runtime"
                ),
            )

            return

    # --------------------------------------------------------
    # PASS
    # --------------------------------------------------------

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
# Distance calibration
# ============================================================

def check_distance(
    offline=False,
):

    path = (
        GLOBAL_DISTANCE_CALIBRATION
    )

    # --------------------------------------------------------
    # Calibration file missing
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Load JSON
    # --------------------------------------------------------

    data = load_json(
        path
    )

    if data is None:

        return

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    required = [
        "H",
        "K",
        "frame_width",
        "frame_height",
        "points",
    ]

    missing = [
        key
        for key in required
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
    # Numeric calibration parameters
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
        saved_width != FRAME_WIDTH
        or
        saved_height != FRAME_HEIGHT
    ):

        add(
            FAIL,
            "Distance calibration",
            (
                "Resolution "
                "ไม่ตรงกับ Runtime"
            ),
        )

        return

    # --------------------------------------------------------
    # Calibration points
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
            f" | range="
            f"{float(min_distance):.2f}"
            f"-"
            f"{float(max_distance):.2f}"
            f"m"
        )

    rmse = data.get(
        "pixel_rmse"
    )

    if finite(
        rmse
    ):

        detail += (
            f" | pixel_RMSE="
            f"{float(rmse):.3f}px"
        )

    add(
        PASS,
        "Distance calibration",
        detail,
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

    # --------------------------------------------------------
    # Supported backend
    # --------------------------------------------------------

    if backend not in {
        "pt",
        "openvino",
    }:

        add(
            FAIL,
            "AI backend",
            (
                f"ไม่รองรับ: "
                f"{backend}"
            ),
        )

        return

    # --------------------------------------------------------
    # OpenVINO
    # --------------------------------------------------------

    if backend == "openvino":

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
                "OpenVINO",
                (
                    "ยังไม่ได้ติดตั้ง "
                    "package"
                ),
            )

            return

        add(
            PASS,
            "OpenVINO",
            "package พร้อม",
        )

    # --------------------------------------------------------
    # PyTorch
    # --------------------------------------------------------

    else:

        model_path = Path(
            MODEL_PATH_PT
        )

    # --------------------------------------------------------
    # Model path
    # --------------------------------------------------------

    if not model_path.exists():

        add(
            FAIL,
            "AI model",
            (
                f"ไม่พบ "
                f"{model_path}"
            ),
        )

        return

    add(
        PASS,
        "AI backend",
        (
            f"{backend} "
            f"| {model_path}"
        ),
    )

    # --------------------------------------------------------
    # Offline mode
    # --------------------------------------------------------

    if not load_model:

        add(
            SKIP,
            "AI model load",
            "Offline mode",
        )

        return

    # --------------------------------------------------------
    # Load model
    # --------------------------------------------------------

    try:

        from ultralytics import (
            YOLO
        )

        model = YOLO(
            str(
                model_path
            )
        )

        names = {
            str(
                value
            ).lower()
            for value
            in model.names.values()
        }

        has_fire = any(
            (
                "fire" in name
                or
                "flame" in name
            )
            for name in names
        )

        has_smoke = any(
            "smoke" in name
            for name in names
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
                    "Model ต้องมี "
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
# Telegram
# ============================================================

def check_telegram():

    token = bool(
        str(
            TELEGRAM_TOKEN
        ).strip()
    )

    chat = bool(
        str(
            TELEGRAM_CHAT_ID
        ).strip()
    )

    if (
        token
        and
        chat
    ):

        add(
            PASS,
            "Telegram",
            "Configured",
        )

    elif (
        not token
        and
        not chat
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
                "ตั้งค่า Telegram "
                "ไม่ครบ"
            ),
        )


# ============================================================
# RTSP Camera
# ============================================================

def check_camera(
    timeout=10,
):

    # --------------------------------------------------------
    # Camera IP must exist in Full mode
    # --------------------------------------------------------

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
            # Frame
            # ------------------------------------------------

            height, width = (
                packet.frame.shape[
                    :2
                ]
            )

            age = max(
                0,
                time.time()
                - packet.timestamp,
            )

            # ------------------------------------------------
            # Resolution
            # ------------------------------------------------

            if (
                width != FRAME_WIDTH
                or
                height != FRAME_HEIGHT
            ):

                add(
                    FAIL,
                    "RTSP camera",
                    (
                        f"{width}x{height} "
                        "ไม่ตรงกับ Runtime"
                    ),
                )

                return

            # ------------------------------------------------
            # PASS
            # ------------------------------------------------

            add(
                PASS,
                "RTSP camera",
                (
                    f"{width}x{height} "
                    f"| seq={packet.seq} "
                    f"| age={age:.3f}s"
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
        ) in results
    )

    warn_count = sum(
        status == WARN
        for (
            status,
            _,
            _,
        ) in results
    )

    fail_count = sum(
        status == FAIL
        for (
            status,
            _,
            _,
        ) in results
    )

    skip_count = sum(
        status == SKIP
        for (
            status,
            _,
            _,
        ) in results
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
    # Failure
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
                "SYSTEM STATUS: "
                "NOT READY"
            )

            print(
                (
                    "แก้รายการ FAIL "
                    "ก่อนรัน main.py"
                )
            )

        return 1

    # ========================================================
    # Offline result
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
    # Full result
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

    # ทำให้ปลอดภัยกรณี Module นี้ถูกเรียกซ้ำ
    results.clear()

    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- Preflight"
        )
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "ตรวจ Software โดยไม่เชื่อม RTSP "
            "และไม่โหลด Model จริง"
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

    check_environment(
        offline=(
            args.offline
        )
    )

    # ========================================================
    # Configuration
    # ========================================================

    check_config(
        offline=(
            args.offline
        )
    )

    # ========================================================
    # Camera geometry
    # ========================================================

    check_intrinsics()

    # ========================================================
    # Site calibration
    # ========================================================

    check_bearing(
        offline=(
            args.offline
        )
    )

    check_distance(
        offline=(
            args.offline
        )
    )

    # ========================================================
    # Notification
    # ========================================================

    check_telegram()

    # ========================================================
    # AI
    # ========================================================

    check_model(
        load_model=(
            not args.offline
        )
    )

    # ========================================================
    # Camera
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
        offline=(
            args.offline
        )
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
#!/usr/bin/env python3
# calibrate_intrinsics.py

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from camera import LatestFrameCamera
from config import (
    CALIBRATION_DIR,
    HFOV_DEG,
)


# ============================================================
# Configuration
# ============================================================

# จำนวน "มุมด้านใน" ของ Checkerboard
PATTERN_COLS = 9
PATTERN_ROWS = 6

PATTERN_SIZE = (
    PATTERN_COLS,
    PATTERN_ROWS,
)

WORK_DIR = (
    CALIBRATION_DIR
    / "intrinsics_v1"
)

CAPTURE_DIR = (
    WORK_DIR
    / "captures"
)

CHECKERBOARD_FILE = (
    WORK_DIR
    / "checkerboard_9x6.png"
)

OUTPUT_FILE = (
    CALIBRATION_DIR
    / "camera_intrinsics.json"
)

REPORT_FILE = (
    WORK_DIR
    / "fit_report.json"
)


# ============================================================
# Directory helpers
# ============================================================

def ensure_dirs():
    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    CAPTURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def archive_existing_captures():
    """
    Archive old calibration captures instead of deleting them.

    Example:
        captures
            ->
        captures_archive_20260815_190500
    """

    ensure_dirs()

    existing = list(
        CAPTURE_DIR.glob(
            "calib_*.jpg"
        )
    )

    if not existing:
        return None

    stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    archive_dir = (
        WORK_DIR
        / f"captures_archive_{stamp}"
    )

    # ป้องกันชื่อซ้ำกรณีสั่งเร็วมาก
    if archive_dir.exists():
        archive_dir = (
            WORK_DIR
            / (
                f"captures_archive_"
                f"{stamp}_"
                f"{time.time_ns()}"
            )
        )

    CAPTURE_DIR.rename(
        archive_dir
    )

    CAPTURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"📦 Archived old captures -> "
        f"{archive_dir}"
    )

    return archive_dir


# ============================================================
# Checkerboard generator
# ============================================================

def generate_checkerboard(
    square_px=120,
    margin_px=80,
):
    """
    Generate 9x6 inner-corner checkerboard.

    9x6 inner corners
    =
    10x7 squares
    """

    ensure_dirs()

    squares_x = (
        PATTERN_COLS + 1
    )

    squares_y = (
        PATTERN_ROWS + 1
    )

    board_w = (
        squares_x
        * square_px
    )

    board_h = (
        squares_y
        * square_px
    )

    width = (
        board_w
        + margin_px * 2
    )

    height = (
        board_h
        + margin_px * 2
    )

    image = np.full(
        (
            height,
            width,
            3,
        ),
        255,
        dtype=np.uint8,
    )

    for row in range(
        squares_y
    ):
        for col in range(
            squares_x
        ):
            if (
                row + col
            ) % 2 == 0:

                x1 = (
                    margin_px
                    + col * square_px
                )

                y1 = (
                    margin_px
                    + row * square_px
                )

                x2 = (
                    x1 + square_px
                )

                y2 = (
                    y1 + square_px
                )

                cv2.rectangle(
                    image,
                    (x1, y1),
                    (x2, y2),
                    (0, 0, 0),
                    -1,
                )

    if not cv2.imwrite(
        str(
            CHECKERBOARD_FILE
        ),
        image,
    ):
        raise RuntimeError(
            "Cannot save checkerboard"
        )

    print(
        "=" * 72
    )

    print(
        "✅ Checkerboard generated"
    )

    print(
        f"File          : "
        f"{CHECKERBOARD_FILE}"
    )

    print(
        f"Inner corners : "
        f"{PATTERN_COLS}"
        f"x"
        f"{PATTERN_ROWS}"
    )

    print(
        f"Squares       : "
        f"{squares_x}"
        f"x"
        f"{squares_y}"
    )

    print(
        "=" * 72
    )


# ============================================================
# Checkerboard detector
# ============================================================

def find_corners(
    frame,
):
    """
    Detect checkerboard corners.

    Priority:
        1. findChessboardCornersSB
           - more robust
           - sub-pixel result
           - preferred for calibration

        2. Legacy findChessboardCorners
           + cornerSubPix
           - fallback for old OpenCV
    """

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY,
    )

    # ========================================================
    # Preferred: SB detector
    # ========================================================

    if hasattr(
        cv2,
        "findChessboardCornersSB",
    ):

        flags = (
            cv2.CALIB_CB_NORMALIZE_IMAGE
        )

        flags |= getattr(
            cv2,
            "CALIB_CB_EXHAUSTIVE",
            0,
        )

        flags |= getattr(
            cv2,
            "CALIB_CB_ACCURACY",
            0,
        )

        try:
            found, corners = (
                cv2.findChessboardCornersSB(
                    gray,
                    PATTERN_SIZE,
                    flags,
                )
            )

        except cv2.error:
            found = False
            corners = None

        if found and corners is not None:
            return corners.astype(
                np.float32
            )

    # ========================================================
    # Fallback: classic detector
    # ========================================================

    flags = (
        cv2.CALIB_CB_ADAPTIVE_THRESH
        |
        cv2.CALIB_CB_NORMALIZE_IMAGE
    )

    found, corners = (
        cv2.findChessboardCorners(
            gray,
            PATTERN_SIZE,
            flags,
        )
    )

    if not found:
        return None

    criteria = (
        cv2.TERM_CRITERIA_EPS
        |
        cv2.TERM_CRITERIA_MAX_ITER,
        50,
        0.0005,
    )

    corners = (
        cv2.cornerSubPix(
            gray,
            corners,
            (11, 11),
            (-1, -1),
            criteria,
        )
    )

    return corners.astype(
        np.float32
    )


# ============================================================
# Capture quality helpers
# ============================================================

def calculate_sharpness(
    frame,
):
    """
    Variance of Laplacian.

    ใช้เป็นตัวบอกคร่าว ๆ ว่าภาพเบลอมากหรือไม่
    """

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY,
    )

    return float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F,
        ).var()
    )


def calculate_board_coverage(
    corners,
    frame_width,
    frame_height,
):
    """
    Approximate checkerboard area / total image area.

    ใช้ตรวจว่า board เล็กหรือใหญ่เกินไปหรือไม่
    """

    if corners is None:
        return 0.0

    points = (
        corners
        .reshape(
            -1,
            2,
        )
        .astype(
            np.float32
        )
    )

    hull = cv2.convexHull(
        points
    )

    board_area = abs(
        cv2.contourArea(
            hull
        )
    )

    frame_area = float(
        frame_width
        * frame_height
    )

    if frame_area <= 0:
        return 0.0

    return float(
        board_area
        / frame_area
    )


def checkerboard_center(
    corners,
):
    if corners is None:
        return None

    points = (
        corners
        .reshape(
            -1,
            2,
        )
    )

    return (
        float(
            np.mean(
                points[:, 0]
            )
        ),
        float(
            np.mean(
                points[:, 1]
            )
        ),
    )


# ============================================================
# Capture
# ============================================================

def capture_frames(
    target_count,
    *,
    reset=False,
    min_sharpness=0.0,
):
    """
    Interactive calibration capture.

    SPACE = save
    Q     = finish

    Recommended:
        20-30 diverse views
    """

    ensure_dirs()

    if reset:
        archive_existing_captures()

    existing = list(
        CAPTURE_DIR.glob(
            "calib_*.jpg"
        )
    )

    if existing:
        print(
            f"ℹ️ Existing captures: "
            f"{len(existing)}"
        )

        print(
            "   ใช้ --reset "
            "ถ้าต้องการเริ่มชุดใหม่"
        )

    print(
        "=" * 72
    )

    print(
        "Camera Intrinsics - CAPTURE"
    )

    print(
        "=" * 72
    )

    print(
        "SPACE = save detected view"
    )

    print(
        "Q     = finish"
    )

    print()

    print(
        "เป้าหมาย:"
    )

    print(
        "- Checkerboard 20-30 ภาพ"
    )

    print(
        "- กระจาย กลาง / ซ้าย / ขวา"
    )

    print(
        "- กระจาย บน / ล่าง"
    )

    print(
        "- เอียง Checkerboard หลายมุม"
    )

    print(
        "- ขนาด Board ประมาณ "
        "10-60% ของภาพ"
    )

    print(
        "- หลีกเลี่ยงภาพเบลอ"
    )

    print(
        "- PTZ อยู่ Preset เดิมตลอด"
    )

    print(
        "=" * 72
    )

    camera = (
        LatestFrameCamera()
        .start()
    )

    saved = len(
        existing
    )

    try:
        # ----------------------------------------------------
        # Wait RTSP
        # ----------------------------------------------------

        deadline = (
            time.monotonic()
            + 10.0
        )

        while (
            camera.latest(
                copy=False
            )
            is None
        ):
            if (
                time.monotonic()
                >= deadline
            ):
                raise RuntimeError(
                    "RTSP timeout"
                )

            time.sleep(
                0.1
            )

        print(
            "✅ RTSP ready"
        )

        # ----------------------------------------------------
        # Interactive loop
        # ----------------------------------------------------

        while True:
            packet = (
                camera.latest(
                    copy=True
                )
            )

            if packet is None:
                time.sleep(
                    0.02
                )
                continue

            frame = (
                packet.frame
            )

            height, width = (
                frame.shape[:2]
            )

            display = (
                frame.copy()
            )

            corners = (
                find_corners(
                    frame
                )
            )

            found = (
                corners
                is not None
            )

            sharpness = (
                calculate_sharpness(
                    frame
                )
            )

            coverage = (
                calculate_board_coverage(
                    corners,
                    width,
                    height,
                )
            )

            center = (
                checkerboard_center(
                    corners
                )
            )

            # ------------------------------------------------
            # Draw corners
            # ------------------------------------------------

            if found:
                cv2.drawChessboardCorners(
                    display,
                    PATTERN_SIZE,
                    corners,
                    True,
                )

            # ------------------------------------------------
            # State
            # ------------------------------------------------

            if not found:
                state = (
                    "PATTERN NOT FOUND"
                )

                color = (
                    0,
                    0,
                    255,
                )

            elif (
                min_sharpness > 0
                and
                sharpness
                < min_sharpness
            ):
                state = (
                    "PATTERN FOUND | BLUR WARNING"
                )

                color = (
                    0,
                    165,
                    255,
                )

            else:
                state = (
                    "PATTERN FOUND"
                )

                color = (
                    0,
                    255,
                    0,
                )

            # ------------------------------------------------
            # HUD
            # ------------------------------------------------

            cv2.putText(
                display,
                (
                    f"{state} "
                    f"| saved="
                    f"{saved}/"
                    f"{target_count}"
                ),
                (
                    20,
                    32,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.70,
                color,
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                display,
                (
                    f"sharpness="
                    f"{sharpness:.1f} "
                    f"| coverage="
                    f"{coverage * 100.0:.1f}%"
                ),
                (
                    20,
                    62,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (
                    0,
                    255,
                    255,
                ),
                2,
                cv2.LINE_AA,
            )

            if center is not None:
                cv2.putText(
                    display,
                    (
                        f"board center="
                        f"({center[0]:.0f},"
                        f"{center[1]:.0f})"
                    ),
                    (
                        20,
                        90,
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (
                        0,
                        255,
                        255,
                    ),
                    2,
                    cv2.LINE_AA,
                )

            cv2.putText(
                display,
                (
                    "SPACE=save | "
                    "Q=finish"
                ),
                (
                    20,
                    118,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (
                    255,
                    255,
                    0,
                ),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(
                "Camera Intrinsics Capture",
                display,
            )

            key = (
                cv2.waitKey(1)
                & 0xFF
            )

            # =================================================
            # SAVE
            # =================================================

            if key == ord(" "):
                if not found:
                    print(
                        "⚠️ Checkerboard "
                        "not detected"
                    )
                    continue

                if (
                    min_sharpness > 0
                    and
                    sharpness
                    < min_sharpness
                ):
                    print(
                        "⚠️ Image too blurry "
                        f"| sharpness="
                        f"{sharpness:.1f} "
                        f"< "
                        f"{min_sharpness:.1f}"
                    )

                    continue

                if (
                    coverage
                    < 0.02
                ):
                    print(
                        "⚠️ Checkerboard "
                        "เล็กเกินไปในภาพ "
                        f"| coverage="
                        f"{coverage * 100:.1f}%"
                    )

                    continue

                saved += 1

                path = (
                    CAPTURE_DIR
                    / (
                        f"calib_"
                        f"{saved:03d}.jpg"
                    )
                )

                if not cv2.imwrite(
                    str(path),
                    frame,
                ):
                    raise RuntimeError(
                        f"Save failed: "
                        f"{path}"
                    )

                print(
                    f"💾 Saved "
                    f"{saved}/"
                    f"{target_count} "
                    f"| sharp="
                    f"{sharpness:.1f} "
                    f"| coverage="
                    f"{coverage * 100:.1f}% "
                    f"-> {path.name}"
                )

                if (
                    saved
                    >= target_count
                ):
                    print(
                        "✅ Target count "
                        "reached"
                    )
                    break

            # =================================================
            # QUIT
            # =================================================

            elif key in (
                ord("q"),
                ord("Q"),
                27,
            ):
                break

    finally:
        camera.stop()

        cv2.destroyAllWindows()

    print(
        f"\nCaptured total: "
        f"{saved}"
    )


# ============================================================
# Object points
# ============================================================

def create_object_points():
    """
    Checkerboard object coordinates.

    Square size = 1 arbitrary unit.

    Focal length in pixels / FOV do not require
    physical square size for this use case.
    """

    points = np.zeros(
        (
            PATTERN_ROWS
            * PATTERN_COLS,
            3,
        ),
        np.float32,
    )

    points[
        :,
        :2
    ] = (
        np.mgrid[
            0:PATTERN_COLS,
            0:PATTERN_ROWS
        ]
        .T
        .reshape(
            -1,
            2,
        )
    )

    return points


# ============================================================
# Calibration utilities
# ============================================================

def build_initial_camera_matrix(
    width,
    height,
):
    """
    Use configured HFOV only as an INITIAL GUESS.

    Optimizer is still free to adjust focal length.
    """

    hfov_rad = math.radians(
        float(
            HFOV_DEG
        )
    )

    fx = (
        width
        /
        (
            2.0
            * math.tan(
                hfov_rad
                / 2.0
            )
        )
    )

    fy = fx

    cx = (
        width - 1
    ) / 2.0

    cy = (
        height - 1
    ) / 2.0

    return np.array(
        [
            [
                fx,
                0.0,
                cx,
            ],
            [
                0.0,
                fy,
                cy,
            ],
            [
                0.0,
                0.0,
                1.0,
            ],
        ],
        dtype=np.float64,
    )


def reprojection_errors(
    object_points,
    image_points,
    rvecs,
    tvecs,
    matrix,
    distortion,
):
    """
    Return RMS reprojection error for each calibration view.
    """

    errors = []

    for (
        obj,
        observed,
        rvec,
        tvec,
    ) in zip(
        object_points,
        image_points,
        rvecs,
        tvecs,
    ):
        projected, _ = (
            cv2.projectPoints(
                obj,
                rvec,
                tvec,
                matrix,
                distortion,
            )
        )

        observed_xy = (
            observed
            .reshape(
                -1,
                2,
            )
        )

        projected_xy = (
            projected
            .reshape(
                -1,
                2,
            )
        )

        delta = (
            observed_xy
            -
            projected_xy
        )

        error = math.sqrt(
            float(
                np.mean(
                    np.sum(
                        delta ** 2,
                        axis=1,
                    )
                )
            )
        )

        errors.append(
            float(
                error
            )
        )

    return errors


# ============================================================
# One calibration fit
# ============================================================

def calibrate_once(
    records,
    image_size,
    *,
    free_k3=False,
    zero_tangent=False,
):
    """
    Run one OpenCV camera calibration.

    Default conservative model:
        k1, k2, p1, p2
        k3 fixed to zero

    Reason:
        previous calibration produced extreme k2/k3 values,
        which strongly suggested over-fitting.

    --free-k3 can be used later if data quality is excellent.
    """

    width, height = (
        image_size
    )

    object_template = (
        create_object_points()
    )

    object_points = [
        object_template.copy()
        for _ in records
    ]

    image_points = [
        item[
            "corners"
        ]
        for item in records
    ]

    camera_matrix = (
        build_initial_camera_matrix(
            width,
            height,
        )
    )

    distortion = np.zeros(
        (
            5,
            1,
        ),
        dtype=np.float64,
    )

    flags = (
        cv2.CALIB_USE_INTRINSIC_GUESS
    )

    if not free_k3:
        flags |= (
            cv2.CALIB_FIX_K3
        )

    if zero_tangent:
        flags |= (
            cv2.CALIB_ZERO_TANGENT_DIST
        )

    (
        rms,
        matrix,
        distortion,
        rvecs,
        tvecs,
    ) = cv2.calibrateCamera(
        object_points,
        image_points,
        image_size,
        camera_matrix,
        distortion,
        flags=flags,
    )

    errors = (
        reprojection_errors(
            object_points,
            image_points,
            rvecs,
            tvecs,
            matrix,
            distortion,
        )
    )

    return {
        "rms": float(
            rms
        ),

        "matrix": (
            matrix
        ),

        "distortion": (
            distortion
        ),

        "rvecs": (
            rvecs
        ),

        "tvecs": (
            tvecs
        ),

        "errors": (
            errors
        ),
    }


# ============================================================
# Robust outlier rejection
# ============================================================

def robust_calibrate(
    records,
    image_size,
    *,
    max_view_error,
    min_views,
    max_reject,
    free_k3=False,
    zero_tangent=False,
):
    """
    Iteratively remove the worst calibration view.

    Stop when:
        - every view <= max_view_error
        - minimum number of views reached
        - max_reject reached

    Important:
        Rejection cannot magically fix poor data.

        If final RMS is still bad,
        output remains intrinsics_unverified.
    """

    active = list(
        records
    )

    rejected = []

    iteration = 0

    while True:
        iteration += 1

        result = calibrate_once(
            active,
            image_size,
            free_k3=free_k3,
            zero_tangent=zero_tangent,
        )

        errors = (
            result[
                "errors"
            ]
        )

        worst_index = int(
            np.argmax(
                errors
            )
        )

        worst_error = float(
            errors[
                worst_index
            ]
        )

        worst_record = (
            active[
                worst_index
            ]
        )

        print(
            f"Fit #{iteration} "
            f"| views="
            f"{len(active)} "
            f"| RMS="
            f"{result['rms']:.4f}px "
            f"| worst="
            f"{worst_error:.4f}px "
            f"({worst_record['filename']})"
        )

        # ----------------------------------------------------
        # All views acceptable
        # ----------------------------------------------------

        if (
            worst_error
            <= max_view_error
        ):
            return (
                result,
                active,
                rejected,
            )

        # ----------------------------------------------------
        # Minimum views reached
        # ----------------------------------------------------

        if (
            len(active)
            <= min_views
        ):
            print(
                "⚠️ Stop outlier rejection: "
                "minimum view count reached"
            )

            return (
                result,
                active,
                rejected,
            )

        # ----------------------------------------------------
        # Maximum rejection reached
        # ----------------------------------------------------

        if (
            len(rejected)
            >= max_reject
        ):
            print(
                "⚠️ Stop outlier rejection: "
                "max rejection reached"
            )

            return (
                result,
                active,
                rejected,
            )

        # ----------------------------------------------------
        # Reject worst view
        # ----------------------------------------------------

        removed = (
            active.pop(
                worst_index
            )
        )

        rejected.append(
            {
                "filename": (
                    removed[
                        "filename"
                    ]
                ),

                "error_px": (
                    worst_error
                ),
            }
        )

        print(
            f"   ↳ reject "
            f"{removed['filename']} "
            f"({worst_error:.4f}px)"
        )


# ============================================================
# FOV calculation
# ============================================================

def calculate_fov(
    matrix,
    width,
    height,
):
    fx = float(
        matrix[
            0,
            0
        ]
    )

    fy = float(
        matrix[
            1,
            1
        ]
    )

    cx = float(
        matrix[
            0,
            2
        ]
    )

    cy = float(
        matrix[
            1,
            2
        ]
    )

    left_angle = math.degrees(
        math.atan2(
            cx,
            fx,
        )
    )

    right_angle = math.degrees(
        math.atan2(
            (
                width
                - 1
                - cx
            ),
            fx,
        )
    )

    top_angle = math.degrees(
        math.atan2(
            cy,
            fy,
        )
    )

    bottom_angle = math.degrees(
        math.atan2(
            (
                height
                - 1
                - cy
            ),
            fy,
        )
    )

    return {
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,

        "left": (
            left_angle
        ),

        "right": (
            right_angle
        ),

        "top": (
            top_angle
        ),

        "bottom": (
            bottom_angle
        ),

        "hfov": (
            left_angle
            + right_angle
        ),

        "vfov": (
            top_angle
            + bottom_angle
        ),
    }


# ============================================================
# Quality classification
# ============================================================

def classify_quality(
    rms,
    mean_error,
    max_error,
):
    """
    Conservative criteria for this project.

    excellent:
        RMS <= 0.50 px
        max <= 1.00 px

    good:
        RMS <= 1.00 px
        max <= 2.00 px

    needs_validation:
        RMS <= 1.50 px
        max <= 2.50 px

    otherwise:
        redo_recommended
    """

    if (
        rms <= 0.50
        and
        mean_error <= 0.70
        and
        max_error <= 1.00
    ):
        return "excellent"

    if (
        rms <= 1.00
        and
        mean_error <= 1.00
        and
        max_error <= 2.00
    ):
        return "good"

    if (
        rms <= 1.50
        and
        mean_error <= 1.50
        and
        max_error <= 2.50
    ):
        return (
            "needs_validation"
        )

    return (
        "redo_recommended"
    )


# ============================================================
# Sanity checks
# ============================================================

def build_sanity_warnings(
    *,
    width,
    height,
    fov,
    distortion,
):
    """
    These are warnings, not hard calibration constraints.
    """

    warnings = []

    cx = (
        fov[
            "cx"
        ]
    )

    cy = (
        fov[
            "cy"
        ]
    )

    center_x = (
        width - 1
    ) / 2.0

    center_y = (
        height - 1
    ) / 2.0

    cx_offset = abs(
        cx
        - center_x
    )

    cy_offset = abs(
        cy
        - center_y
    )

    if (
        cx_offset
        > width * 0.08
    ):
        warnings.append(
            (
                "Principal X is far from "
                "image center."
            )
        )

    if (
        cy_offset
        > height * 0.08
    ):
        warnings.append(
            (
                "Principal Y is far from "
                "image center."
            )
        )

    hfov = (
        fov[
            "hfov"
        ]
    )

    if not (
        20.0
        <= hfov
        <= 120.0
    ):
        warnings.append(
            (
                "HFOV is outside "
                "expected sanity range."
            )
        )

    values = (
        distortion
        .reshape(-1)
        .tolist()
    )

    # Standard 5-coefficient model:
    # k1, k2, p1, p2, k3

    if len(values) >= 1:
        if abs(
            values[0]
        ) > 1.0:
            warnings.append(
                "Large |k1| distortion."
            )

    if len(values) >= 2:
        if abs(
            values[1]
        ) > 3.0:
            warnings.append(
                "Large |k2| distortion."
            )

    if len(values) >= 5:
        if abs(
            values[4]
        ) > 5.0:
            warnings.append(
                "Large |k3| distortion."
            )

    return warnings


# ============================================================
# Fit
# ============================================================

def fit_intrinsics(
    *,
    max_view_error=1.5,
    min_views=12,
    max_reject=8,
    free_k3=False,
    zero_tangent=False,
):
    ensure_dirs()

    paths = sorted(
        CAPTURE_DIR.glob(
            "calib_*.jpg"
        )
    )

    if len(paths) < 10:
        raise SystemExit(
            "❌ ต้องมีอย่างน้อย "
            "10 calibration images\n"
            "แนะนำ 20-30 ภาพ"
        )

    records = []

    image_size = None

    print(
        "=" * 72
    )

    print(
        "Camera Intrinsics - FIT"
    )

    print(
        "=" * 72
    )

    print(
        f"Images found   : "
        f"{len(paths)}"
    )

    print(
        f"Max view error : "
        f"{max_view_error:.2f}px"
    )

    print(
        f"Minimum views  : "
        f"{min_views}"
    )

    print(
        f"Max rejection  : "
        f"{max_reject}"
    )

    print(
        f"K3             : "
        f"{'FREE' if free_k3 else 'FIXED=0'}"
    )

    print(
        f"Tangential     : "
        f"{'FIXED=0' if zero_tangent else 'FREE'}"
    )

    print(
        "=" * 72
    )

    # ========================================================
    # Detect corners from every capture
    # ========================================================

    for path in paths:
        frame = cv2.imread(
            str(path)
        )

        if frame is None:
            print(
                f"⚠️ Skip "
                f"{path.name}: "
                "cannot read"
            )
            continue

        height, width = (
            frame.shape[:2]
        )

        current_size = (
            width,
            height,
        )

        if image_size is None:
            image_size = (
                current_size
            )

        elif (
            current_size
            != image_size
        ):
            print(
                f"⚠️ Skip "
                f"{path.name}: "
                "resolution mismatch"
            )
            continue

        corners = (
            find_corners(
                frame
            )
        )

        if corners is None:
            print(
                f"⚠️ Skip "
                f"{path.name}: "
                "corners not found"
            )
            continue

        sharpness = (
            calculate_sharpness(
                frame
            )
        )

        coverage = (
            calculate_board_coverage(
                corners,
                width,
                height,
            )
        )

        center = (
            checkerboard_center(
                corners
            )
        )

        records.append(
            {
                "filename": (
                    path.name
                ),

                "path": (
                    str(path)
                ),

                "corners": (
                    corners
                ),

                "sharpness": (
                    sharpness
                ),

                "coverage": (
                    coverage
                ),

                "center_x": (
                    None
                    if center is None
                    else center[0]
                ),

                "center_y": (
                    None
                    if center is None
                    else center[1]
                ),
            }
        )

        print(
            f"✅ "
            f"{path.name} "
            f"| sharp="
            f"{sharpness:.1f} "
            f"| coverage="
            f"{coverage * 100:.1f}%"
        )

    if image_size is None:
        raise SystemExit(
            "❌ No valid images"
        )

    if len(
        records
    ) < 10:
        raise SystemExit(
            "❌ Valid checkerboard "
            "views < 10"
        )

    if (
        min_views
        > len(records)
    ):
        min_views = max(
            10,
            len(records)
            - 1,
        )

    # ========================================================
    # Robust calibration
    # ========================================================

    print(
        "\n"
        + "-" * 72
    )

    print(
        "ROBUST CALIBRATION"
    )

    print(
        "-" * 72
    )

    (
        fit,
        active_records,
        rejected_records,
    ) = robust_calibrate(
        records,
        image_size,
        max_view_error=(
            max_view_error
        ),
        min_views=(
            min_views
        ),
        max_reject=(
            max_reject
        ),
        free_k3=(
            free_k3
        ),
        zero_tangent=(
            zero_tangent
        ),
    )

    matrix = (
        fit[
            "matrix"
        ]
    )

    distortion = (
        fit[
            "distortion"
        ]
    )

    errors = (
        fit[
            "errors"
        ]
    )

    rms = float(
        fit[
            "rms"
        ]
    )

    width, height = (
        image_size
    )

    mean_error = float(
        np.mean(
            errors
        )
    )

    max_error = float(
        np.max(
            errors
        )
    )

    fov = calculate_fov(
        matrix,
        width,
        height,
    )

    quality = classify_quality(
        rms,
        mean_error,
        max_error,
    )

    # Production accepts only
    # excellent or good

    valid_for_production = (
        quality
        in {
            "excellent",
            "good",
        }
    )

    status = (
        "intrinsics_calibrated"
        if valid_for_production
        else "intrinsics_unverified"
    )

    warnings = (
        build_sanity_warnings(
            width=width,
            height=height,
            fov=fov,
            distortion=distortion,
        )
    )

    # ========================================================
    # Console result
    # ========================================================

    print(
        "\n"
        + "=" * 72
    )

    print(
        "INTRINSIC RESULT"
    )

    print(
        "=" * 72
    )

    print(
        f"Resolution     : "
        f"{width}x{height}"
    )

    print(
        f"Input views    : "
        f"{len(records)}"
    )

    print(
        f"Views used     : "
        f"{len(active_records)}"
    )

    print(
        f"Views rejected : "
        f"{len(rejected_records)}"
    )

    print()

    print(
        f"RMS            : "
        f"{rms:.6f} px"
    )

    print(
        f"Mean error     : "
        f"{mean_error:.6f} px"
    )

    print(
        f"Max error      : "
        f"{max_error:.6f} px"
    )

    print(
        f"Quality        : "
        f"{quality}"
    )

    print(
        f"Production     : "
        f"{'YES' if valid_for_production else 'NO'}"
    )

    print()

    print(
        f"fx             : "
        f"{fov['fx']:.6f} px"
    )

    print(
        f"fy             : "
        f"{fov['fy']:.6f} px"
    )

    print(
        f"cx             : "
        f"{fov['cx']:.6f} px"
    )

    print(
        f"cy             : "
        f"{fov['cy']:.6f} px"
    )

    print()

    print(
        f"HFOV           : "
        f"{fov['hfov']:.6f}°"
    )

    print(
        f"VFOV           : "
        f"{fov['vfov']:.6f}°"
    )

    print(
        f"Left half FOV  : "
        f"{fov['left']:.6f}°"
    )

    print(
        f"Right half FOV : "
        f"{fov['right']:.6f}°"
    )

    print()

    distortion_flat = (
        distortion
        .reshape(-1)
        .tolist()
    )

    distortion_names = [
        "k1",
        "k2",
        "p1",
        "p2",
        "k3",
    ]

    print(
        "Distortion:"
    )

    for index, value in enumerate(
        distortion_flat
    ):
        name = (
            distortion_names[index]
            if index
            < len(
                distortion_names
            )
            else f"d{index}"
        )

        print(
            f"  {name:<3s} = "
            f"{value:.10f}"
        )

    # ========================================================
    # Rejected views
    # ========================================================

    if rejected_records:
        print()

        print(
            "Rejected views:"
        )

        for item in rejected_records:
            print(
                f"  - "
                f"{item['filename']} "
                f"| error="
                f"{item['error_px']:.4f}px"
            )

    # ========================================================
    # Sanity warnings
    # ========================================================

    if warnings:
        print()

        print(
            "Sanity warnings:"
        )

        for warning in warnings:
            print(
                f"  ⚠️ {warning}"
            )

    # ========================================================
    # Per-view error
    # ========================================================

    per_view_error = {}

    for (
        record,
        error,
    ) in zip(
        active_records,
        errors,
    ):
        per_view_error[
            record[
                "filename"
            ]
        ] = float(
            error
        )

    # ========================================================
    # Calibration coverage summary
    # ========================================================

    center_points = [
        (
            record[
                "center_x"
            ],
            record[
                "center_y"
            ],
        )
        for record
        in active_records
        if (
            record[
                "center_x"
            ]
            is not None
            and
            record[
                "center_y"
            ]
            is not None
        )
    ]

    if center_points:
        center_x_values = [
            point[0]
            for point
            in center_points
        ]

        center_y_values = [
            point[1]
            for point
            in center_points
        ]

        center_range = {
            "min_x_px": float(
                min(
                    center_x_values
                )
            ),

            "max_x_px": float(
                max(
                    center_x_values
                )
            ),

            "min_y_px": float(
                min(
                    center_y_values
                )
            ),

            "max_y_px": float(
                max(
                    center_y_values
                )
            ),
        }

    else:
        center_range = None

    # ========================================================
    # Save result
    # ========================================================

    result = {
        "version": 2,

        "created_at": (
            time.time()
        ),

        "status": (
            status
        ),

        "valid_for_production": (
            valid_for_production
        ),

        "frame_width": (
            int(
                width
            )
        ),

        "frame_height": (
            int(
                height
            )
        ),

        "pattern_inner_corners": [
            PATTERN_COLS,
            PATTERN_ROWS,
        ],

        "input_views": (
            len(
                records
            )
        ),

        "views_used": (
            len(
                active_records
            )
        ),

        "views_rejected": (
            len(
                rejected_records
            )
        ),

        "camera_matrix": (
            matrix.tolist()
        ),

        "fx_px": (
            fov[
                "fx"
            ]
        ),

        "fy_px": (
            fov[
                "fy"
            ]
        ),

        "cx_px": (
            fov[
                "cx"
            ]
        ),

        "cy_px": (
            fov[
                "cy"
            ]
        ),

        "distortion_coefficients": (
            distortion_flat
        ),

        "distortion_model": {
            "k1": (
                distortion_flat[0]
                if len(
                    distortion_flat
                ) > 0
                else 0.0
            ),

            "k2": (
                distortion_flat[1]
                if len(
                    distortion_flat
                ) > 1
                else 0.0
            ),

            "p1": (
                distortion_flat[2]
                if len(
                    distortion_flat
                ) > 2
                else 0.0
            ),

            "p2": (
                distortion_flat[3]
                if len(
                    distortion_flat
                ) > 3
                else 0.0
            ),

            "k3": (
                distortion_flat[4]
                if len(
                    distortion_flat
                ) > 4
                else 0.0
            ),
        },

        "fit_model": {
            "use_intrinsic_guess": (
                True
            ),

            "initial_hfov_deg": (
                float(
                    HFOV_DEG
                )
            ),

            "k3_fixed": (
                not free_k3
            ),

            "zero_tangential_distortion": (
                zero_tangent
            ),

            "max_view_error_px": (
                float(
                    max_view_error
                )
            ),

            "min_views": (
                int(
                    min_views
                )
            ),

            "max_reject": (
                int(
                    max_reject
                )
            ),
        },

        "effective_hfov_deg": (
            fov[
                "hfov"
            ]
        ),

        "effective_vfov_deg": (
            fov[
                "vfov"
            ]
        ),

        "left_half_fov_deg": (
            fov[
                "left"
            ]
        ),

        "right_half_fov_deg": (
            fov[
                "right"
            ]
        ),

        "fit": {
            "opencv_rms_px": (
                rms
            ),

            "mean_reprojection_px": (
                mean_error
            ),

            "max_reprojection_px": (
                max_error
            ),

            "quality": (
                quality
            ),
        },

        "used_files": [
            record[
                "filename"
            ]
            for record
            in active_records
        ],

        "rejected_files": (
            rejected_records
        ),

        "per_view_error_px": (
            per_view_error
        ),

        "capture_coverage": {
            "board_center_range": (
                center_range
            ),

            "coverage_fraction": {
                record[
                    "filename"
                ]: float(
                    record[
                        "coverage"
                    ]
                )

                for record
                in active_records
            },

            "sharpness": {
                record[
                    "filename"
                ]: float(
                    record[
                        "sharpness"
                    ]
                )

                for record
                in active_records
            },
        },

        "sanity_warnings": (
            warnings
        ),

        "notes": [
            (
                "Use camera intrinsics "
                "for pixel-to-ray conversion."
            ),

            (
                "Distortion should be removed "
                "before pixel bearing calculation."
            ),

            (
                "This file does not define "
                "PTZ preset world bearings."
            ),

            (
                "This file does not define "
                "True North."
            ),

            (
                "Production use is allowed only "
                "when valid_for_production=true."
            ),
        ],
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Diagnostic report
    REPORT_FILE.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 72
    )

    print(
        f"Saved calibration: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Saved report     : "
        f"{REPORT_FILE}"
    )

    print(
        "=" * 72
    )

    if valid_for_production:
        print(
            "✅ Intrinsic calibration "
            "ผ่านเกณฑ์"
        )

        print(
            "✅ พร้อมสำหรับ "
            "Preset Geometry v3 validation"
        )

    else:
        print(
            "⚠️ Intrinsic calibration "
            "ยังไม่ผ่าน"
        )

        print(
            "⚠️ camera_intrinsics.json "
            "ถูกบันทึกเพื่อวิเคราะห์เท่านั้น"
        )

        print(
            "⚠️ ห้ามนำเข้า Production "
            "ในสถานะนี้"
        )


# ============================================================
# CLI
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- Camera Intrinsic Calibration"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # ========================================================
    # generate
    # ========================================================

    generate = sub.add_parser(
        "generate",
        help=(
            "Generate checkerboard image"
        ),
    )

    generate.add_argument(
        "--square-px",
        type=int,
        default=120,
    )

    generate.add_argument(
        "--margin-px",
        type=int,
        default=80,
    )

    # ========================================================
    # capture
    # ========================================================

    capture = sub.add_parser(
        "capture",
        help=(
            "Capture checkerboard views"
        ),
    )

    capture.add_argument(
        "--count",
        type=int,
        default=25,
        help=(
            "Target images "
            "(default: 25)"
        ),
    )

    capture.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Archive old captures "
            "and start a new set"
        ),
    )

    capture.add_argument(
        "--min-sharpness",
        type=float,
        default=0.0,
        help=(
            "Reject blurry frames below "
            "Laplacian variance. "
            "0=disable. "
            "Try 50-100 if needed."
        ),
    )

    # ========================================================
    # fit
    # ========================================================

    fit = sub.add_parser(
        "fit",
        help=(
            "Fit camera intrinsics"
        ),
    )

    fit.add_argument(
        "--max-view-error",
        type=float,
        default=1.5,
        help=(
            "Reject a calibration view "
            "above this RMS error "
            "(default: 1.5 px)"
        ),
    )

    fit.add_argument(
        "--min-views",
        type=int,
        default=12,
        help=(
            "Minimum views kept "
            "(default: 12)"
        ),
    )

    fit.add_argument(
        "--max-reject",
        type=int,
        default=8,
        help=(
            "Maximum automatically "
            "rejected views "
            "(default: 8)"
        ),
    )

    fit.add_argument(
        "--free-k3",
        action="store_true",
        help=(
            "Allow k3 radial distortion "
            "to be optimized. "
            "Default keeps k3=0 "
            "to reduce over-fitting."
        ),
    )

    fit.add_argument(
        "--zero-tangent",
        action="store_true",
        help=(
            "Force p1=p2=0. "
            "Normally leave disabled."
        ),
    )

    return parser


# ============================================================
# Main
# ============================================================

def main():
    parser = (
        build_parser()
    )

    args = (
        parser.parse_args()
    )

    if args.command == "generate":
        if args.square_px <= 0:
            raise SystemExit(
                "❌ --square-px "
                "must be > 0"
            )

        if args.margin_px < 0:
            raise SystemExit(
                "❌ --margin-px "
                "must be >= 0"
            )

        generate_checkerboard(
            square_px=(
                args.square_px
            ),
            margin_px=(
                args.margin_px
            ),
        )

    elif args.command == "capture":
        if args.count < 10:
            raise SystemExit(
                "❌ --count "
                "must be >= 10"
            )

        if args.min_sharpness < 0:
            raise SystemExit(
                "❌ --min-sharpness "
                "must be >= 0"
            )

        capture_frames(
            args.count,
            reset=(
                args.reset
            ),
            min_sharpness=(
                args.min_sharpness
            ),
        )

    elif args.command == "fit":
        if args.max_view_error <= 0:
            raise SystemExit(
                "❌ --max-view-error "
                "must be > 0"
            )

        if args.min_views < 10:
            raise SystemExit(
                "❌ --min-views "
                "must be >= 10"
            )

        if args.max_reject < 0:
            raise SystemExit(
                "❌ --max-reject "
                "must be >= 0"
            )

        fit_intrinsics(
            max_view_error=(
                args.max_view_error
            ),
            min_views=(
                args.min_views
            ),
            max_reject=(
                args.max_reject
            ),
            free_k3=(
                args.free_k3
            ),
            zero_tangent=(
                args.zero_tangent
            ),
        )


if __name__ == "__main__":
    main()
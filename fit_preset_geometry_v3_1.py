#!/usr/bin/env python3
# fit_preset_geometry_v3_1.py

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from config import (
    CALIBRATION_DIR,
    PRESET_PAN_DEG,
)


# ============================================================
# Files
# ============================================================

INTRINSICS_FILE = (
    CALIBRATION_DIR
    / "camera_intrinsics.json"
)

MARKS_FILE = (
    CALIBRATION_DIR
    / "bearing_v2"
    / "overlap_marks.json"
)

OUTPUT_FILE = (
    CALIBRATION_DIR
    / "preset_geometry_v3_1.json"
)


# ============================================================
# Geometry configuration
# ============================================================

PRESETS = list(
    range(1, 10)
)

ANCHOR_PRESET = 1


# ============================================================
# Full physical loop
# ============================================================
#
# เดินรอบกล้อง:
#
# P1
#  ↓
# P2
#  ↓
# P3
#  ↓
# P4
#  ↓
# P5
#  ↓
# P9
#  ↓
# P8
#  ↓
# P7
#  ↓
# P6
#  ↓
# P1
#
# ผลรวมควรใกล้ +360°
#
# ============================================================

LOOP_ROUTE = [
    1,
    2,
    3,
    4,
    5,
    9,
    8,
    7,
    6,
    1,
]


# ============================================================
# Quality thresholds
# ============================================================

PAIR_MAD_OUTLIER_SCALE = 3.5

MIN_PAIR_POINTS = 3

# loop closure:
# <= 1°   excellent
# <= 2°   good
# <= 5°   validation
# > 5°    reject

LOOP_EXCELLENT_DEG = 1.0
LOOP_GOOD_DEG = 2.0
LOOP_VALIDATE_DEG = 5.0


# ============================================================
# JSON
# ============================================================

def load_json(
    path: Path,
):
    if not path.exists():

        raise SystemExit(
            f"❌ Missing file:\n"
            f"{path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


# ============================================================
# Angles
# ============================================================

def normalize_signed_deg(
    angle,
):
    """
    Normalize:
        [-180, 180)
    """

    return (
        (
            float(angle)
            + 180.0
        )
        % 360.0
    ) - 180.0


def circular_difference_deg(
    a,
    b,
):
    """
    Signed:
        a - b

    wrapped to [-180,180)
    """

    return normalize_signed_deg(
        float(a)
        - float(b)
    )


# ============================================================
# Intrinsics
# ============================================================

def load_intrinsics():

    data = load_json(
        INTRINSICS_FILE
    )

    if not data.get(
        "valid_for_production",
        False,
    ):

        raise SystemExit(
            "❌ Camera intrinsics "
            "ยังไม่ผ่าน Production validation"
        )

    if (
        data.get("status")
        != "intrinsics_calibrated"
    ):

        raise SystemExit(
            "❌ Camera intrinsics "
            "status ไม่ถูกต้อง"
        )

    matrix = np.asarray(
        data[
            "camera_matrix"
        ],
        dtype=np.float64,
    )

    distortion = np.asarray(
        data[
            "distortion_coefficients"
        ],
        dtype=np.float64,
    ).reshape(
        -1,
        1,
    )

    return (
        data,
        matrix,
        distortion,
    )


# ============================================================
# Pixel -> optical horizontal angle
# ============================================================

def pixel_horizontal_angle_deg(
    x_px,
    y_px,
    camera_matrix,
    distortion,
):

    point = np.asarray(
        [
            [
                [
                    float(x_px),
                    float(y_px),
                ]
            ]
        ],
        dtype=np.float64,
    )

    undistorted = (
        cv2.undistortPoints(
            point,
            camera_matrix,
            distortion,
        )
    )

    x_norm = float(
        undistorted[
            0,
            0,
            0,
        ]
    )

    return math.degrees(
        math.atan2(
            x_norm,
            1.0,
        )
    )


# ============================================================
# Robust statistics
# ============================================================

def robust_pair_statistics(
    values,
):
    """
    Median + MAD based filtering.

    ไม่ใช้ mean ตรง ๆ เพราะ point เดียว
    ที่คลิกคลาดสามารถดึงทั้ง pair ได้
    """

    values = np.asarray(
        values,
        dtype=np.float64,
    )

    if values.size == 0:

        raise ValueError(
            "No values"
        )

    median = float(
        np.median(
            values
        )
    )

    deviations = np.abs(
        values
        - median
    )

    mad = float(
        np.median(
            deviations
        )
    )

    # Gaussian-equivalent robust sigma
    robust_sigma = (
        1.4826
        * mad
    )

    # --------------------------------------------------------
    # MAD = 0
    # --------------------------------------------------------

    if robust_sigma < 1e-9:

        mask = np.ones(
            values.shape,
            dtype=bool,
        )

    else:

        threshold = (
            PAIR_MAD_OUTLIER_SCALE
            * robust_sigma
        )

        mask = (
            deviations
            <= threshold
        )

    filtered = (
        values[
            mask
        ]
    )

    # Safety:
    # อย่าตัดจนเหลือน้อยเกินไป
    if (
        filtered.size
        < MIN_PAIR_POINTS
    ):

        filtered = (
            values.copy()
        )

        mask = np.ones(
            values.shape,
            dtype=bool,
        )

    filtered_median = float(
        np.median(
            filtered
        )
    )

    filtered_mean = float(
        np.mean(
            filtered
        )
    )

    filtered_std = float(
        np.std(
            filtered
        )
    )

    filtered_range = float(
        np.max(
            filtered
        )
        -
        np.min(
            filtered
        )
    )

    return {
        "raw_values": (
            values.tolist()
        ),

        "raw_count": int(
            values.size
        ),

        "raw_median": (
            median
        ),

        "mad": (
            mad
        ),

        "robust_sigma": (
            robust_sigma
        ),

        "inlier_mask": (
            mask.tolist()
        ),

        "inlier_values": (
            filtered.tolist()
        ),

        "inlier_count": int(
            filtered.size
        ),

        "median": (
            filtered_median
        ),

        "mean": (
            filtered_mean
        ),

        "std": (
            filtered_std
        ),

        "range": (
            filtered_range
        ),

        "outliers_removed": int(
            values.size
            - filtered.size
        ),
    }


# ============================================================
# Build pair measurements
# ============================================================

def build_pair_measurements(
    marks,
    camera_matrix,
    distortion,
):

    pairs = marks.get(
        "pairs",
        {},
    )

    if not pairs:

        raise SystemExit(
            "❌ overlap_marks.json "
            "ไม่มีข้อมูล pairs"
        )

    results = {}

    for pair_name, pair in (
        pairs.items()
    ):

        preset_a = int(
            pair[
                "preset_a"
            ]
        )

        preset_b = int(
            pair[
                "preset_b"
            ]
        )

        matches = pair.get(
            "matches",
            [],
        )

        if (
            len(matches)
            < MIN_PAIR_POINTS
        ):

            print(
                f"⚠️ Skip "
                f"{pair_name}: "
                f"points="
                f"{len(matches)}"
            )

            continue

        values = []

        point_reports = []

        for index, match in enumerate(
            matches,
            start=1,
        ):

            angle_a = (
                pixel_horizontal_angle_deg(
                    match[
                        "x_a_px"
                    ],
                    match[
                        "y_a_px"
                    ],
                    camera_matrix,
                    distortion,
                )
            )

            angle_b = (
                pixel_horizontal_angle_deg(
                    match[
                        "x_b_px"
                    ],
                    match[
                        "y_b_px"
                    ],
                    camera_matrix,
                    distortion,
                )
            )

            # --------------------------------------------
            # Same real target:
            #
            # center_a + offset_a
            # =
            # center_b + offset_b
            #
            # center_b - center_a
            # =
            # offset_a - offset_b
            # --------------------------------------------

            measured_delta = (
                angle_a
                - angle_b
            )

            measured_delta = (
                normalize_signed_deg(
                    measured_delta
                )
            )

            values.append(
                measured_delta
            )

            point_reports.append(
                {
                    "index": (
                        index
                    ),

                    "offset_a_deg": (
                        angle_a
                    ),

                    "offset_b_deg": (
                        angle_b
                    ),

                    "delta_deg": (
                        measured_delta
                    ),
                }
            )

        stats = (
            robust_pair_statistics(
                values
            )
        )

        # annotate point inlier/outlier
        for (
            report,
            is_inlier,
        ) in zip(
            point_reports,
            stats[
                "inlier_mask"
            ],
        ):

            report[
                "inlier"
            ] = bool(
                is_inlier
            )

        key = (
            f"{preset_a}-{preset_b}"
        )

        results[
            key
        ] = {
            "preset_a": (
                preset_a
            ),

            "preset_b": (
                preset_b
            ),

            "delta_deg": (
                stats[
                    "median"
                ]
            ),

            "statistics": (
                stats
            ),

            "points": (
                point_reports
            ),
        }

    return results


# ============================================================
# Nominal winding
# ============================================================

def nominal_unwrapped_delta(
    preset_a,
    preset_b,
):
    """
    Nominal raw difference.

    Example:

        P5 = +177.5
        P9 = -177.5

        raw:
            -355°

    But physically:
            +5°

    We preserve winding information separately.
    """

    a = float(
        PRESET_PAN_DEG[
            preset_a
        ]
    )

    b = float(
        PRESET_PAN_DEG[
            preset_b
        ]
    )

    raw = (
        b - a
    )

    wrapped = (
        normalize_signed_deg(
            raw
        )
    )

    winding = int(
        round(
            (
                wrapped
                - raw
            )
            / 360.0
        )
    )

    return (
        raw,
        wrapped,
        winding,
    )


# ============================================================
# Edge linear delta
# ============================================================

def pair_linear_delta(
    pair,
):
    """
    Convert circular pair measurement
    into the unwrapped linear equation:

        C_b - C_a = RHS

    For P5 -> P9:

        measured ≈ +8°

        winding = +1

        C9 - C5
        =
        +8 - 360
        =
        -352°
    """

    a = (
        pair[
            "preset_a"
        ]
    )

    b = (
        pair[
            "preset_b"
        ]
    )

    measured = float(
        pair[
            "delta_deg"
        ]
    )

    (
        nominal_raw,
        nominal_wrapped,
        winding,
    ) = nominal_unwrapped_delta(
        a,
        b,
    )

    linear_delta = (
        measured
        - 360.0
        * winding
    )

    return {
        "nominal_raw_deg": (
            nominal_raw
        ),

        "nominal_wrapped_deg": (
            nominal_wrapped
        ),

        "winding": (
            winding
        ),

        "measured_circular_deg": (
            measured
        ),

        "linear_delta_deg": (
            linear_delta
        ),
    }


# ============================================================
# Weighted global solver
# ============================================================

def solve_global_geometry(
    pair_measurements,
):
    """
    Solve all pair relationships simultaneously.

    P1 = 0° anchor.

    IMPORTANT:
    This fit is diagnostic.

    It does NOT automatically mean
    the geometry is suitable for production.
    """

    unknown = [
        preset
        for preset
        in PRESETS
        if preset
        != ANCHOR_PRESET
    ]

    index_map = {
        preset: index
        for index, preset
        in enumerate(
            unknown
        )
    }

    rows = []

    rhs = []

    weights = []

    equations = []

    for pair_name, pair in (
        pair_measurements.items()
    ):

        a = (
            pair[
                "preset_a"
            ]
        )

        b = (
            pair[
                "preset_b"
            ]
        )

        linear = (
            pair_linear_delta(
                pair
            )
        )

        row = np.zeros(
            len(
                unknown
            ),
            dtype=np.float64,
        )

        if (
            b
            != ANCHOR_PRESET
        ):

            row[
                index_map[
                    b
                ]
            ] += 1.0

        if (
            a
            != ANCHOR_PRESET
        ):

            row[
                index_map[
                    a
                ]
            ] -= 1.0

        # ----------------------------------------------------
        # Conservative weight
        #
        # Better pair consistency gets somewhat higher weight,
        # but weight is capped to prevent one edge dominating.
        # ----------------------------------------------------

        std = float(
            pair[
                "statistics"
            ][
                "std"
            ]
        )

        sigma = max(
            std,
            0.25,
        )

        weight = min(
            1.0
            / (
                sigma
                ** 2
            ),
            16.0,
        )

        rows.append(
            row
        )

        rhs.append(
            linear[
                "linear_delta_deg"
            ]
        )

        weights.append(
            weight
        )

        equations.append(
            {
                "pair": (
                    pair_name
                ),

                "weight": (
                    weight
                ),

                **linear,
            }
        )

    A = np.vstack(
        rows
    )

    b = np.asarray(
        rhs,
        dtype=np.float64,
    )

    weights_array = np.asarray(
        weights,
        dtype=np.float64,
    )

    sqrt_w = np.sqrt(
        weights_array
    )

    Aw = (
        A
        * sqrt_w[
            :,
            None
        ]
    )

    bw = (
        b
        * sqrt_w
    )

    solution, _, rank, singular_values = (
        np.linalg.lstsq(
            Aw,
            bw,
            rcond=None,
        )
    )

    if (
        rank
        < len(
            unknown
        )
    ):

        raise SystemExit(
            "❌ Geometry system "
            "rank deficient"
        )

    centers = {
        ANCHOR_PRESET: (
            0.0
        )
    }

    for preset in unknown:

        centers[
            preset
        ] = float(
            solution[
                index_map[
                    preset
                ]
            ]
        )

    residuals = (
        A
        @ solution
        - b
    )

    weighted_residuals = (
        residuals
        * sqrt_w
    )

    for (
        equation,
        residual,
    ) in zip(
        equations,
        residuals,
    ):

        equation[
            "fit_residual_deg"
        ] = float(
            residual
        )

    return (
        centers,
        residuals,
        weighted_residuals,
        rank,
        singular_values,
        equations,
    )


# ============================================================
# Find pair orientation
# ============================================================

def find_directed_delta(
    pair_measurements,
    preset_from,
    preset_to,
):
    """
    Return local circular angle from
    preset_from -> preset_to.

    Automatically reverses pair when needed.
    """

    direct_key = (
        f"{preset_from}-"
        f"{preset_to}"
    )

    reverse_key = (
        f"{preset_to}-"
        f"{preset_from}"
    )

    if (
        direct_key
        in pair_measurements
    ):

        return float(
            pair_measurements[
                direct_key
            ][
                "delta_deg"
            ]
        )

    if (
        reverse_key
        in pair_measurements
    ):

        return -float(
            pair_measurements[
                reverse_key
            ][
                "delta_deg"
            ]
        )

    raise KeyError(
        f"No pair "
        f"P{preset_from}"
        f"↔P{preset_to}"
    )


# ============================================================
# Loop closure
# ============================================================

def calculate_loop_closure(
    pair_measurements,
):
    """
    Sum local physical rotations around the full loop.

    Expected:
        approximately +360°

    Example:

    P1 -> P2 -> P3 -> P4 -> P5
    -> P9 -> P8 -> P7 -> P6 -> P1
    """

    edge_reports = []

    total = 0.0

    for index in range(
        len(
            LOOP_ROUTE
        )
        - 1
    ):

        a = (
            LOOP_ROUTE[
                index
            ]
        )

        b = (
            LOOP_ROUTE[
                index + 1
            ]
        )

        delta = (
            find_directed_delta(
                pair_measurements,
                a,
                b,
            )
        )

        # We want clockwise accumulation
        # around approximately +360°.
        #
        # Some reverse pairs become positive
        # automatically because we reverse their sign.

        delta_positive = (
            delta
        )

        if (
            delta_positive
            < -180.0
        ):

            delta_positive += (
                360.0
            )

        elif (
            delta_positive
            > 180.0
        ):

            delta_positive -= (
                360.0
            )

        # Along this defined route,
        # expected each motion is positive.
        #
        # If numerical representation is negative,
        # convert equivalent local movement.
        if (
            delta_positive
            < 0.0
        ):

            delta_positive = abs(
                delta_positive
            )

        total += (
            delta_positive
        )

        edge_reports.append(
            {
                "from": (
                    a
                ),

                "to": (
                    b
                ),

                "delta_deg": (
                    delta_positive
                ),
            }
        )

    closure_error = (
        total
        - 360.0
    )

    abs_error = abs(
        closure_error
    )

    if (
        abs_error
        <= LOOP_EXCELLENT_DEG
    ):

        quality = (
            "excellent"
        )

    elif (
        abs_error
        <= LOOP_GOOD_DEG
    ):

        quality = (
            "good"
        )

    elif (
        abs_error
        <= LOOP_VALIDATE_DEG
    ):

        quality = (
            "needs_validation"
        )

    else:

        quality = (
            "failed"
        )

    return {
        "route": (
            LOOP_ROUTE
        ),

        "edges": (
            edge_reports
        ),

        "total_rotation_deg": (
            total
        ),

        "expected_rotation_deg": (
            360.0
        ),

        "closure_error_deg": (
            closure_error
        ),

        "abs_closure_error_deg": (
            abs_error
        ),

        "quality": (
            quality
        ),

        "passed": (
            quality
            in {
                "excellent",
                "good",
            }
        ),
    }


# ============================================================
# Pair quality
# ============================================================

def classify_pair(
    pair,
):
    std = float(
        pair[
            "statistics"
        ][
            "std"
        ]
    )

    value_range = float(
        pair[
            "statistics"
        ][
            "range"
        ]
    )

    if (
        std <= 0.35
        and
        value_range <= 1.0
    ):

        return (
            "excellent"
        )

    if (
        std <= 0.75
        and
        value_range <= 2.0
    ):

        return (
            "good"
        )

    if (
        std <= 1.25
        and
        value_range <= 3.5
    ):

        return (
            "needs_validation"
        )

    return (
        "poor"
    )


# ============================================================
# Main
# ============================================================

def main():

    print(
        "=" * 78
    )

    print(
        "Smart Fire Detection v2"
    )

    print(
        "Circular Preset Geometry Solver v3.1"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # Load
    # ========================================================

    (
        intrinsics,
        camera_matrix,
        distortion,
    ) = load_intrinsics()

    marks = load_json(
        MARKS_FILE
    )

    print(
        "✅ Intrinsics loaded"
    )

    print(
        f"   HFOV    : "
        f"{intrinsics['effective_hfov_deg']:.3f}°"
    )

    print(
        f"   Quality : "
        f"{intrinsics['fit']['quality']}"
    )

    # ========================================================
    # Measurements
    # ========================================================

    pair_measurements = (
        build_pair_measurements(
            marks,
            camera_matrix,
            distortion,
        )
    )

    print(
        f"✅ Pairs loaded: "
        f"{len(pair_measurements)}"
    )

    # required loop edges

    required = [
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 9),
        (8, 9),
        (7, 8),
        (6, 7),
        (1, 6),
    ]

    for a, b in required:

        key = (
            f"{a}-{b}"
        )

        reverse = (
            f"{b}-{a}"
        )

        if (
            key
            not in pair_measurements
            and
            reverse
            not in pair_measurements
        ):

            raise SystemExit(
                f"❌ Missing required pair "
                f"P{a}↔P{b}"
            )

    # ========================================================
    # Pair report
    # ========================================================

    print(
        "\n"
        + "-" * 78
    )

    print(
        "ROBUST PAIR MEASUREMENTS"
    )

    print(
        "-" * 78
    )

    for key in sorted(
        pair_measurements
    ):

        pair = (
            pair_measurements[
                key
            ]
        )

        stats = (
            pair[
                "statistics"
            ]
        )

        quality = (
            classify_pair(
                pair
            )
        )

        print(
            f"{key:<7s} "
            f"| delta="
            f"{pair['delta_deg']:+8.3f}° "
            f"| n="
            f"{stats['inlier_count']}/"
            f"{stats['raw_count']} "
            f"| std="
            f"{stats['std']:.3f}° "
            f"| range="
            f"{stats['range']:.3f}° "
            f"| {quality}"
        )

        if (
            stats[
                "outliers_removed"
            ]
            > 0
        ):

            print(
                f"         ↳ removed "
                f"{stats['outliers_removed']} "
                "outlier(s)"
            )

    # ========================================================
    # Loop closure BEFORE fitting
    # ========================================================

    loop = (
        calculate_loop_closure(
            pair_measurements
        )
    )

    print(
        "\n"
        + "-" * 78
    )

    print(
        "360° LOOP CLOSURE"
    )

    print(
        "-" * 78
    )

    for edge in (
        loop[
            "edges"
        ]
    ):

        print(
            f"P{edge['from']} "
            f"-> "
            f"P{edge['to']} "
            f": "
            f"{edge['delta_deg']:.4f}°"
        )

    print(
        "-" * 78
    )

    print(
        f"Measured total : "
        f"{loop['total_rotation_deg']:.6f}°"
    )

    print(
        f"Expected total : "
        f"{loop['expected_rotation_deg']:.6f}°"
    )

    print(
        f"Closure error  : "
        f"{loop['closure_error_deg']:+.6f}°"
    )

    print(
        f"Abs error      : "
        f"{loop['abs_closure_error_deg']:.6f}°"
    )

    print(
        f"Loop quality   : "
        f"{loop['quality']}"
    )

    # ========================================================
    # Global circular-aware fit
    # ========================================================

    (
        centers,
        residuals,
        weighted_residuals,
        rank,
        singular_values,
        equations,
    ) = solve_global_geometry(
        pair_measurements
    )

    rms = float(
        math.sqrt(
            float(
                np.mean(
                    residuals
                    ** 2
                )
            )
        )
    )

    mean_abs = float(
        np.mean(
            np.abs(
                residuals
            )
        )
    )

    max_abs = float(
        np.max(
            np.abs(
                residuals
            )
        )
    )

    print(
        "\n"
        + "-" * 78
    )

    print(
        "GLOBAL CIRCULAR FIT"
    )

    print(
        "-" * 78
    )

    print(
        f"Rank       : "
        f"{rank}"
    )

    print(
        f"RMS        : "
        f"{rms:.6f}°"
    )

    print(
        f"Mean abs   : "
        f"{mean_abs:.6f}°"
    )

    print(
        f"Max error  : "
        f"{max_abs:.6f}°"
    )

    # ========================================================
    # Presets
    # ========================================================

    print()

    print(
        "Preset | Nominal      Fitted       Correction"
    )

    print(
        "-" * 57
    )

    fitted_signed = {}

    for preset in PRESETS:

        fitted = (
            normalize_signed_deg(
                centers[
                    preset
                ]
            )
        )

        fitted_signed[
            preset
        ] = (
            fitted
        )

        nominal = float(
            PRESET_PAN_DEG[
                preset
            ]
        )

        correction = (
            circular_difference_deg(
                fitted,
                nominal,
            )
        )

        print(
            f"P{preset:<2d}    "
            f"{nominal:>+10.3f}° "
            f"{fitted:>+10.3f}° "
            f"{correction:>+10.3f}°"
        )

    # ========================================================
    # Equation residuals
    # ========================================================

    print(
        "\n"
        + "-" * 78
    )

    print(
        "EDGE FIT RESIDUAL"
    )

    print(
        "-" * 78
    )

    for equation in equations:

        print(
            f"{equation['pair']:<7s} "
            f"| measured="
            f"{equation['measured_circular_deg']:+8.3f}° "
            f"| residual="
            f"{equation['fit_residual_deg']:+8.3f}° "
            f"| weight="
            f"{equation['weight']:.2f}"
        )

    # ========================================================
    # Final validity
    # ========================================================

    pair_qualities = {
        key: classify_pair(
            pair
        )
        for key, pair
        in pair_measurements.items()
    }

    poor_pairs = [
        key
        for key, quality
        in pair_qualities.items()
        if quality == "poor"
    ]

    # Primary safety condition:
    # Full-circle closure must pass.

    valid_relative_geometry = (
        loop[
            "passed"
        ]
        and
        rms <= 1.0
        and
        max_abs <= 2.0
        and
        not poor_pairs
    )

    print(
        "\n"
        + "=" * 78
    )

    print(
        "FINAL VALIDATION"
    )

    print(
        "=" * 78
    )

    print(
        f"Loop closure : "
        f"{'PASS' if loop['passed'] else 'FAIL'}"
    )

    print(
        f"Global fit   : "
        f"{'PASS' if rms <= 1.0 and max_abs <= 2.0 else 'FAIL'}"
    )

    print(
        f"Poor pairs   : "
        f"{poor_pairs if poor_pairs else 'None'}"
    )

    print(
        f"Relative geometry: "
        f"{'PASS' if valid_relative_geometry else 'FAIL'}"
    )

    print(
        "World bearing     : "
        "NOT CALIBRATED"
    )

    print(
        "Production GPS    : "
        "DISABLED"
    )

    # ========================================================
    # Save diagnostic result
    # ========================================================

    output = {
        "version": "3.1",

        "created_at": (
            time.time()
        ),

        "status": (
            "relative_geometry_calibrated"
            if valid_relative_geometry
            else "relative_geometry_unverified"
        ),

        "valid_for_relative_geometry": (
            valid_relative_geometry
        ),

        "valid_for_world_bearing": (
            False
        ),

        "absolute_north_calibrated": (
            False
        ),

        "production_gps_allowed": (
            False
        ),

        "intrinsics": {
            "source": (
                str(
                    INTRINSICS_FILE
                )
            ),

            "quality": (
                intrinsics[
                    "fit"
                ][
                    "quality"
                ]
            ),

            "hfov_deg": (
                intrinsics[
                    "effective_hfov_deg"
                ]
            ),
        },

        "loop_closure": (
            loop
        ),

        "global_fit": {
            "rank": (
                int(
                    rank
                )
            ),

            "rms_residual_deg": (
                rms
            ),

            "mean_abs_residual_deg": (
                mean_abs
            ),

            "max_abs_residual_deg": (
                max_abs
            ),
        },

        "preset_relative_pan_deg": {
            str(preset): (
                float(
                    fitted_signed[
                        preset
                    ]
                )
            )

            for preset
            in PRESETS
        },

        "pair_measurements": (
            pair_measurements
        ),

        "pair_quality": (
            pair_qualities
        ),

        "edge_equations": (
            equations
        ),

        "poor_pairs": (
            poor_pairs
        ),

        "notes": [
            (
                "Circular loop closure is "
                "required before production use."
            ),

            (
                "A low least-squares residual "
                "cannot override failed "
                "360-degree loop closure."
            ),

            (
                "True North is not calibrated."
            ),

            (
                "GPS must remain disabled."
            ),
        ],
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()

    print(
        f"Saved:\n"
        f"{OUTPUT_FILE}"
    )

    print(
        "=" * 78
    )

    if valid_relative_geometry:

        print(
            "✅ Circular Relative Geometry "
            "ผ่าน"
        )

        print(
            "ขั้นต่อไป: "
            "Independent Overlap Validation"
        )

    else:

        print(
            "⚠️ Circular Relative Geometry "
            "ยังไม่ผ่าน"
        )

        print(
            "อย่าแก้ detection.py "
            "หรือเปิด World Bearing/GPS"
        )

        print(
            "ขั้นต่อไปต้องตรวจ "
            "PTZ repeatability / parallax "
            "ตามผล Loop Closure"
        )


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# test_ptz_repeatability_v1.py

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

from camera import (
    LatestFrameCamera,
    wait_until_stable,
)

from config import (
    CALIBRATION_DIR,
    INITIAL_PRESET_WAIT_SEC,
    POST_MOVE_FRESH_FRAMES,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
)

from ptz import PTZController


# ============================================================
# Files
# ============================================================

INTRINSICS_FILE = (
    CALIBRATION_DIR
    / "camera_intrinsics.json"
)

WORK_DIR = (
    CALIBRATION_DIR
    / "ptz_repeatability_v1"
)


# ============================================================
# Test geometry
# ============================================================
#
# target:
#     (approach from side A,
#      approach from side B)
#
# ตัวอย่าง:
#
#     P3 -> P4
#     P5 -> P4
#
# ถ้า P4 เป็น preset ที่ repeatable จริง
# ภาพสุดท้ายทั้งสองแบบควรเกือบตรงกัน
#
# ============================================================

APPROACH_MAP = {
    1: (2, 6),
    4: (3, 5),
    7: (6, 8),
    8: (7, 9),
}


# ============================================================
# Diagnostic thresholds
# ============================================================
#
# นี่คือเกณฑ์ภายในของโปรเจกต์เรา
# ไม่ใช่ specification จากผู้ผลิตกล้อง
#
# ============================================================

EXCELLENT_BIAS_DEG = 0.25
GOOD_BIAS_DEG = 0.50
VALIDATION_BIAS_DEG = 1.00

GOOD_MAX_DEG = 1.00
VALIDATION_MAX_DEG = 2.00


# ============================================================
# JSON
# ============================================================

def load_json(
    path: Path,
):
    if not path.exists():
        raise SystemExit(
            f"❌ Missing file:\n{path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(
    path: Path,
    data,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_suffix(
        ".tmp"
    )

    temp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp.replace(
        path
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
            "ยังไม่ผ่าน validation"
        )

    if (
        data.get("status")
        != "intrinsics_calibrated"
    ):
        raise SystemExit(
            "❌ Intrinsics status invalid"
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
# Angle helpers
# ============================================================

def normalize_signed_deg(
    value,
):
    return (
        (
            float(value)
            + 180.0
        )
        % 360.0
    ) - 180.0


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
# Fresh frames
# ============================================================

def wait_fresh_frames(
    camera,
    after_seq,
    count,
):
    seq = int(
        after_seq
    )

    packet = None

    for _ in range(
        max(
            1,
            int(count),
        )
    ):
        packet = (
            camera.wait_for_newer(
                seq,
                timeout=2.0,
            )
        )

        if packet is None:
            return None

        seq = (
            packet.seq
        )

    return packet


# ============================================================
# PTZ move + stable frame
# ============================================================

def move_to_stable(
    camera,
    ptz,
    preset,
    *,
    first_move=False,
):
    print(
        f"🔄 Move -> P{preset}"
    )

    ok, wait_sec = (
        ptz.goto_preset(
            preset
        )
    )

    if not ok:
        raise RuntimeError(
            f"PTZ command failed "
            f"for P{preset}"
        )

    if first_move:
        wait_sec = max(
            float(wait_sec),
            float(
                INITIAL_PRESET_WAIT_SEC
            ),
        )

    print(
        f"   wait="
        f"{wait_sec:.2f}s"
    )

    time.sleep(
        wait_sec
    )

    # --------------------------------------------------------
    # Snapshot sequence AFTER movement delay
    # --------------------------------------------------------

    arrival_seq = (
        camera.sequence
    )

    fresh = wait_fresh_frames(
        camera,
        arrival_seq,
        POST_MOVE_FRESH_FRAMES,
    )

    if fresh is None:
        raise RuntimeError(
            f"No fresh frame "
            f"at P{preset}"
        )

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:
        raise RuntimeError(
            f"Image did not stabilize "
            f"at P{preset}"
        )

    age = (
        time.time()
        - stable.timestamp
    )

    print(
        f"   ✅ stable "
        f"seq={stable.seq} "
        f"age={age:.3f}s"
    )

    return stable


# ============================================================
# RTSP ready
# ============================================================

def wait_camera_ready(
    camera,
    timeout=10.0,
):
    deadline = (
        time.monotonic()
        + timeout
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


# ============================================================
# Robust stats
# ============================================================

def robust_stats(
    values,
):
    array = np.asarray(
        values,
        dtype=np.float64,
    )

    if array.size == 0:
        return None

    median = float(
        np.median(
            array
        )
    )

    deviation = np.abs(
        array
        - median
    )

    mad = float(
        np.median(
            deviation
        )
    )

    robust_sigma = (
        1.4826
        * mad
    )

    if (
        robust_sigma
        <= 1e-9
    ):
        mask = np.ones(
            array.shape,
            dtype=bool,
        )

    else:
        threshold = (
            3.5
            * robust_sigma
        )

        mask = (
            deviation
            <= threshold
        )

    filtered = (
        array[
            mask
        ]
    )

    # Do not over-filter
    if (
        filtered.size
        < 5
    ):
        filtered = (
            array.copy()
        )

        mask = np.ones(
            array.shape,
            dtype=bool,
        )

    return {
        "raw_count": int(
            array.size
        ),

        "inlier_count": int(
            filtered.size
        ),

        "outlier_count": int(
            array.size
            - filtered.size
        ),

        "median": float(
            np.median(
                filtered
            )
        ),

        "mean": float(
            np.mean(
                filtered
            )
        ),

        "std": float(
            np.std(
                filtered
            )
        ),

        "min": float(
            np.min(
                filtered
            )
        ),

        "max": float(
            np.max(
                filtered
            )
        ),

        "range": float(
            np.max(
                filtered
            )
            -
            np.min(
                filtered
            )
        ),

        "mad": (
            mad
        ),

        "robust_sigma": (
            robust_sigma
        ),

        "mask": (
            mask.tolist()
        ),
    }


# ============================================================
# ORB matching
# ============================================================

def compare_images(
    image_a,
    image_b,
    camera_matrix,
    distortion,
    *,
    ratio_threshold=0.75,
    min_matches=20,
):
    """
    Compare SAME preset captured after approaching
    from different directions.

    Workflow:
        ORB
          ↓
        KNN ratio matching
          ↓
        RANSAC Homography
          ↓
        Geometric inliers
          ↓
        pixel -> undistorted optical angle
          ↓
        same-feature bearing difference

    If target preset is repeatable:
        median difference ≈ 0°
    """

    gray_a = cv2.cvtColor(
        image_a,
        cv2.COLOR_BGR2GRAY,
    )

    gray_b = cv2.cvtColor(
        image_b,
        cv2.COLOR_BGR2GRAY,
    )

    orb = cv2.ORB_create(
        nfeatures=5000,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=19,
        fastThreshold=10,
    )

    key_a, des_a = (
        orb.detectAndCompute(
            gray_a,
            None,
        )
    )

    key_b, des_b = (
        orb.detectAndCompute(
            gray_b,
            None,
        )
    )

    if (
        des_a is None
        or
        des_b is None
    ):
        return {
            "ok": False,
            "reason": (
                "no_descriptors"
            ),
        }

    matcher = cv2.BFMatcher(
        cv2.NORM_HAMMING,
        crossCheck=False,
    )

    knn = matcher.knnMatch(
        des_a,
        des_b,
        k=2,
    )

    good = []

    for item in knn:
        if len(item) < 2:
            continue

        first, second = (
            item
        )

        if (
            first.distance
            <
            ratio_threshold
            * second.distance
        ):
            good.append(
                first
            )

    if (
        len(good)
        < min_matches
    ):
        return {
            "ok": False,

            "reason": (
                "insufficient_ratio_matches"
            ),

            "ratio_matches": (
                len(good)
            ),
        }

    points_a = np.float32(
        [
            key_a[
                match.queryIdx
            ].pt

            for match
            in good
        ]
    )

    points_b = np.float32(
        [
            key_b[
                match.trainIdx
            ].pt

            for match
            in good
        ]
    )

    homography, mask = (
        cv2.findHomography(
            points_a,
            points_b,
            cv2.RANSAC,
            3.0,
        )
    )

    if (
        homography is None
        or
        mask is None
    ):
        return {
            "ok": False,

            "reason": (
                "homography_failed"
            ),

            "ratio_matches": (
                len(good)
            ),
        }

    mask = (
        mask
        .reshape(-1)
        .astype(bool)
    )

    inlier_matches = [
        match
        for (
            match,
            keep,
        )
        in zip(
            good,
            mask,
        )
        if keep
    ]

    if (
        len(inlier_matches)
        < min_matches
    ):
        return {
            "ok": False,

            "reason": (
                "insufficient_ransac_inliers"
            ),

            "ratio_matches": (
                len(good)
            ),

            "ransac_inliers": (
                len(
                    inlier_matches
                )
            ),
        }

    # --------------------------------------------------------
    # Same matched world feature:
    #
    # center_b - center_a
    # =
    # optical_offset_a - optical_offset_b
    # --------------------------------------------------------

    angle_deltas = []

    feature_records = []

    for match in (
        inlier_matches
    ):
        xa, ya = (
            key_a[
                match.queryIdx
            ].pt
        )

        xb, yb = (
            key_b[
                match.trainIdx
            ].pt
        )

        angle_a = (
            pixel_horizontal_angle_deg(
                xa,
                ya,
                camera_matrix,
                distortion,
            )
        )

        angle_b = (
            pixel_horizontal_angle_deg(
                xb,
                yb,
                camera_matrix,
                distortion,
            )
        )

        delta = (
            normalize_signed_deg(
                angle_a
                - angle_b
            )
        )

        angle_deltas.append(
            delta
        )

        feature_records.append(
            {
                "x_a": float(
                    xa
                ),

                "y_a": float(
                    ya
                ),

                "x_b": float(
                    xb
                ),

                "y_b": float(
                    yb
                ),

                "delta_deg": float(
                    delta
                ),
            }
        )

    stats = robust_stats(
        angle_deltas
    )

    return {
        "ok": True,

        "reason": (
            "ok"
        ),

        "keypoints_a": (
            len(
                key_a
            )
        ),

        "keypoints_b": (
            len(
                key_b
            )
        ),

        "ratio_matches": (
            len(
                good
            )
        ),

        "ransac_inliers": (
            len(
                inlier_matches
            )
        ),

        "angle_stats": (
            stats
        ),

        "features": (
            feature_records
        ),

        "_debug": {
            "key_a": (
                key_a
            ),

            "key_b": (
                key_b
            ),

            "matches": (
                inlier_matches
            ),
        },
    }


# ============================================================
# Debug image
# ============================================================

def save_match_debug(
    path,
    image_a,
    image_b,
    comparison,
):
    debug = comparison.get(
        "_debug"
    )

    if not debug:
        return False

    matches = debug[
        "matches"
    ]

    if not matches:
        return False

    # Show strongest subset
    selected = sorted(
        matches,
        key=lambda m: m.distance,
    )[:80]

    output = cv2.drawMatches(
        image_a,
        debug[
            "key_a"
        ],
        image_b,
        debug[
            "key_b"
        ],
        selected,
        None,
        flags=(
            cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
        ),
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return bool(
        cv2.imwrite(
            str(path),
            output,
        )
    )


# ============================================================
# Clean private objects before JSON
# ============================================================

def clean_comparison(
    comparison,
):
    return {
        key: value
        for (
            key,
            value,
        )
        in comparison.items()
        if key != "_debug"
    }


# ============================================================
# Quality
# ============================================================

def classify_target(
    cross_values,
    same_values,
):
    if not cross_values:
        return (
            "insufficient_data"
        )

    cross_array = np.asarray(
        cross_values,
        dtype=np.float64,
    )

    cross_bias = abs(
        float(
            np.median(
                cross_array
            )
        )
    )

    cross_max = float(
        np.max(
            np.abs(
                cross_array
            )
        )
    )

    if same_values:
        same_max = float(
            np.max(
                np.abs(
                    np.asarray(
                        same_values,
                        dtype=np.float64,
                    )
                )
            )
        )

    else:
        same_max = 0.0

    if (
        cross_bias
        <= EXCELLENT_BIAS_DEG
        and
        cross_max
        <= 0.50
        and
        same_max
        <= 0.50
    ):
        return (
            "excellent"
        )

    if (
        cross_bias
        <= GOOD_BIAS_DEG
        and
        cross_max
        <= GOOD_MAX_DEG
        and
        same_max
        <= GOOD_MAX_DEG
    ):
        return (
            "good"
        )

    if (
        cross_bias
        <= VALIDATION_BIAS_DEG
        and
        cross_max
        <= VALIDATION_MAX_DEG
        and
        same_max
        <= VALIDATION_MAX_DEG
    ):
        return (
            "needs_validation"
        )

    return (
        "poor"
    )


# ============================================================
# Analyze capture set
# ============================================================

def analyze_run(
    run_dir,
    manifest,
    camera_matrix,
    distortion,
    *,
    ratio_threshold,
    min_matches,
):
    print(
        "\n"
        + "=" * 78
    )

    print(
        "PTZ REPEATABILITY ANALYSIS"
    )

    print(
        "=" * 78
    )

    captures = (
        manifest[
            "captures"
        ]
    )

    by_key = {}

    for item in captures:
        key = (
            int(
                item[
                    "target"
                ]
            ),
            int(
                item[
                    "approach"
                ]
            ),
            int(
                item[
                    "repeat"
                ]
            ),
        )

        by_key[
            key
        ] = item

    results = {}

    debug_dir = (
        run_dir
        / "debug_matches"
    )

    for target_str, approach_values in (
        manifest[
            "targets"
        ].items()
    ):
        target = int(
            target_str
        )

        approach_a = int(
            approach_values[0]
        )

        approach_b = int(
            approach_values[1]
        )

        cross_results = []

        cross_values = []

        same_results = []

        same_values = []

        print(
            "\n"
            + "-" * 78
        )

        print(
            f"TARGET P{target}"
        )

        print(
            f"Approach A: "
            f"P{approach_a} -> P{target}"
        )

        print(
            f"Approach B: "
            f"P{approach_b} -> P{target}"
        )

        print(
            "-" * 78
        )

        # ====================================================
        # Cross-direction comparisons
        # ====================================================

        for repeat in range(
            1,
            int(
                manifest[
                    "repeats"
                ]
            )
            + 1,
        ):
            item_a = by_key.get(
                (
                    target,
                    approach_a,
                    repeat,
                )
            )

            item_b = by_key.get(
                (
                    target,
                    approach_b,
                    repeat,
                )
            )

            if (
                item_a is None
                or
                item_b is None
            ):
                continue

            image_a = cv2.imread(
                item_a[
                    "path"
                ]
            )

            image_b = cv2.imread(
                item_b[
                    "path"
                ]
            )

            if (
                image_a is None
                or
                image_b is None
            ):
                continue

            comparison = compare_images(
                image_a,
                image_b,
                camera_matrix,
                distortion,
                ratio_threshold=(
                    ratio_threshold
                ),
                min_matches=(
                    min_matches
                ),
            )

            clean = (
                clean_comparison(
                    comparison
                )
            )

            clean[
                "repeat"
            ] = repeat

            cross_results.append(
                clean
            )

            if comparison[
                "ok"
            ]:
                value = float(
                    comparison[
                        "angle_stats"
                    ][
                        "median"
                    ]
                )

                cross_values.append(
                    value
                )

                print(
                    f"Cross R{repeat}: "
                    f"bias="
                    f"{value:+.4f}° "
                    f"| matches="
                    f"{comparison['ransac_inliers']} "
                    f"| feature std="
                    f"{comparison['angle_stats']['std']:.4f}°"
                )

                debug_path = (
                    debug_dir
                    / (
                        f"P{target}_"
                        f"A{approach_a}_"
                        f"B{approach_b}_"
                        f"R{repeat}.jpg"
                    )
                )

                save_match_debug(
                    debug_path,
                    image_a,
                    image_b,
                    comparison,
                )

            else:
                print(
                    f"Cross R{repeat}: "
                    f"❌ "
                    f"{comparison['reason']}"
                )

        # ====================================================
        # Same-direction repeatability
        # ====================================================

        for approach in (
            approach_a,
            approach_b,
        ):
            reference = by_key.get(
                (
                    target,
                    approach,
                    1,
                )
            )

            if reference is None:
                continue

            image_ref = cv2.imread(
                reference[
                    "path"
                ]
            )

            if image_ref is None:
                continue

            for repeat in range(
                2,
                int(
                    manifest[
                        "repeats"
                    ]
                )
                + 1,
            ):
                current = by_key.get(
                    (
                        target,
                        approach,
                        repeat,
                    )
                )

                if current is None:
                    continue

                image_current = (
                    cv2.imread(
                        current[
                            "path"
                        ]
                    )
                )

                if image_current is None:
                    continue

                comparison = compare_images(
                    image_ref,
                    image_current,
                    camera_matrix,
                    distortion,
                    ratio_threshold=(
                        ratio_threshold
                    ),
                    min_matches=(
                        min_matches
                    ),
                )

                clean = clean_comparison(
                    comparison
                )

                clean.update(
                    {
                        "approach": (
                            approach
                        ),

                        "reference_repeat": (
                            1
                        ),

                        "repeat": (
                            repeat
                        ),
                    }
                )

                same_results.append(
                    clean
                )

                if comparison[
                    "ok"
                ]:
                    value = float(
                        comparison[
                            "angle_stats"
                        ][
                            "median"
                        ]
                    )

                    same_values.append(
                        value
                    )

                    print(
                        f"Same P{approach} "
                        f"R1->R{repeat}: "
                        f"{value:+.4f}°"
                    )

                else:
                    print(
                        f"Same P{approach} "
                        f"R1->R{repeat}: "
                        f"❌ "
                        f"{comparison['reason']}"
                    )

        # ====================================================
        # Target summary
        # ====================================================

        if cross_values:
            cross_median = float(
                np.median(
                    cross_values
                )
            )

            cross_max = float(
                np.max(
                    np.abs(
                        cross_values
                    )
                )
            )

            cross_std = float(
                np.std(
                    cross_values
                )
            )

        else:
            cross_median = None
            cross_max = None
            cross_std = None

        if same_values:
            same_max = float(
                np.max(
                    np.abs(
                        same_values
                    )
                )
            )

            same_median_abs = float(
                np.median(
                    np.abs(
                        same_values
                    )
                )
            )

        else:
            same_max = None
            same_median_abs = None

        quality = classify_target(
            cross_values,
            same_values,
        )

        print()

        print(
            f"P{target} summary:"
        )

        if (
            cross_median
            is not None
        ):
            print(
                f"  Direction bias median : "
                f"{cross_median:+.4f}°"
            )

            print(
                f"  Direction bias max    : "
                f"{cross_max:.4f}°"
            )

            print(
                f"  Cross-repeat std      : "
                f"{cross_std:.4f}°"
            )

        if (
            same_max
            is not None
        ):
            print(
                f"  Same-direction max    : "
                f"{same_max:.4f}°"
            )

        print(
            f"  Quality               : "
            f"{quality}"
        )

        results[
            str(
                target
            )
        ] = {
            "target": (
                target
            ),

            "approach_a": (
                approach_a
            ),

            "approach_b": (
                approach_b
            ),

            "cross_direction": (
                cross_results
            ),

            "same_direction": (
                same_results
            ),

            "summary": {
                "cross_median_deg": (
                    cross_median
                ),

                "cross_max_abs_deg": (
                    cross_max
                ),

                "cross_std_deg": (
                    cross_std
                ),

                "same_median_abs_deg": (
                    same_median_abs
                ),

                "same_max_abs_deg": (
                    same_max
                ),

                "quality": (
                    quality
                ),
            },
        }

    qualities = [
        item[
            "summary"
        ][
            "quality"
        ]

        for item
        in results.values()
    ]

    overall_pass = (
        bool(
            qualities
        )
        and
        all(
            quality
            in {
                "excellent",
                "good",
            }
            for quality
            in qualities
        )
    )

    print(
        "\n"
        + "=" * 78
    )

    print(
        "FINAL PTZ REPEATABILITY"
    )

    print(
        "=" * 78
    )

    for target, result in (
        results.items()
    ):
        summary = (
            result[
                "summary"
            ]
        )

        print(
            f"P{target}: "
            f"{summary['quality']} "
            f"| cross median="
            f"{summary['cross_median_deg']} "
            f"| cross max="
            f"{summary['cross_max_abs_deg']} "
            f"| same max="
            f"{summary['same_max_abs_deg']}"
        )

    print(
        "-" * 78
    )

    print(
        f"PTZ repeatability: "
        f"{'PASS' if overall_pass else 'NOT PASSED'}"
    )

    return {
        "targets": (
            results
        ),

        "overall_pass": (
            overall_pass
        ),

        "criteria": {
            "excellent_bias_deg": (
                EXCELLENT_BIAS_DEG
            ),

            "good_bias_deg": (
                GOOD_BIAS_DEG
            ),

            "validation_bias_deg": (
                VALIDATION_BIAS_DEG
            ),

            "good_max_deg": (
                GOOD_MAX_DEG
            ),

            "validation_max_deg": (
                VALIDATION_MAX_DEG
            ),

            "note": (
                "Project diagnostic "
                "thresholds, not "
                "manufacturer specifications."
            ),
        },
    }


# ============================================================
# Main test
# ============================================================

def run_test(
    *,
    targets,
    repeats,
    ratio_threshold,
    min_matches,
):
    (
        intrinsics,
        camera_matrix,
        distortion,
    ) = load_intrinsics()

    invalid = [
        target
        for target
        in targets
        if target
        not in APPROACH_MAP
    ]

    if invalid:
        raise SystemExit(
            "❌ No approach mapping "
            f"for targets: {invalid}"
        )

    timestamp = (
        time.strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    run_dir = (
        WORK_DIR
        / f"run_{timestamp}"
    )

    images_dir = (
        run_dir
        / "images"
    )

    images_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "=" * 78
    )

    print(
        "Smart Fire Detection v2"
    )

    print(
        "PTZ Directional Repeatability v1"
    )

    print(
        "=" * 78
    )

    print(
        f"Targets : "
        f"{targets}"
    )

    print(
        f"Repeats : "
        f"{repeats}"
    )

    print(
        f"HFOV    : "
        f"{intrinsics['effective_hfov_deg']:.3f}°"
    )

    print(
        f"fx      : "
        f"{intrinsics['fx_px']:.3f}px"
    )

    print(
        "=" * 78
    )

    manifest = {
        "version": 1,

        "created_at": (
            time.time()
        ),

        "run_dir": (
            str(
                run_dir
            )
        ),

        "repeats": (
            repeats
        ),

        "targets": {
            str(target): list(
                APPROACH_MAP[
                    target
                ]
            )

            for target
            in targets
        },

        "captures": [],
    }

    camera = (
        LatestFrameCamera()
        .start()
    )

    ptz = (
        PTZController()
    )

    first_move = True

    try:
        print(
            "📡 Waiting for RTSP..."
        )

        wait_camera_ready(
            camera
        )

        print(
            "✅ RTSP ready"
        )

        for target in targets:
            approach_a, approach_b = (
                APPROACH_MAP[
                    target
                ]
            )

            print(
                "\n"
                + "#" * 78
            )

            print(
                f"TARGET P{target}"
            )

            print(
                f"Approaches: "
                f"P{approach_a}, "
                f"P{approach_b}"
            )

            print(
                "#" * 78
            )

            for repeat in range(
                1,
                repeats + 1,
            ):
                for approach in (
                    approach_a,
                    approach_b,
                ):
                    print(
                        "\n"
                        f"--- "
                        f"P{approach} "
                        f"-> P{target} "
                        f"| repeat "
                        f"{repeat}/"
                        f"{repeats} "
                        f"---"
                    )

                    # -----------------------------------------
                    # Ensure approach direction
                    # -----------------------------------------

                    move_to_stable(
                        camera,
                        ptz,
                        approach,
                        first_move=(
                            first_move
                        ),
                    )

                    first_move = False

                    # -----------------------------------------
                    # Then target
                    # -----------------------------------------

                    packet = move_to_stable(
                        camera,
                        ptz,
                        target,
                        first_move=False,
                    )

                    filename = (
                        f"P{target}_"
                        f"from_P{approach}_"
                        f"R{repeat:02d}.jpg"
                    )

                    path = (
                        images_dir
                        / filename
                    )

                    ok = cv2.imwrite(
                        str(path),
                        packet.frame,
                    )

                    if not ok:
                        raise RuntimeError(
                            f"Cannot save "
                            f"{path}"
                        )

                    manifest[
                        "captures"
                    ].append(
                        {
                            "target": (
                                target
                            ),

                            "approach": (
                                approach
                            ),

                            "repeat": (
                                repeat
                            ),

                            "path": (
                                str(path)
                            ),

                            "seq": int(
                                packet.seq
                            ),

                            "frame_timestamp": float(
                                packet.timestamp
                            ),

                            "saved_at": (
                                time.time()
                            ),
                        }
                    )

                    print(
                        f"💾 {filename}"
                    )

        manifest_path = (
            run_dir
            / "manifest.json"
        )

        save_json(
            manifest_path,
            manifest,
        )

        print(
            "\n✅ Capture completed"
        )

        print(
            f"Manifest: "
            f"{manifest_path}"
        )

    finally:
        print(
            "📡 Stopping camera..."
        )

        camera.stop()

    # ========================================================
    # Analyze immediately
    # ========================================================

    analysis = analyze_run(
        run_dir,
        manifest,
        camera_matrix,
        distortion,
        ratio_threshold=(
            ratio_threshold
        ),
        min_matches=(
            min_matches
        ),
    )

    output = {
        "version": 1,

        "created_at": (
            time.time()
        ),

        "intrinsics": {
            "hfov_deg": (
                intrinsics[
                    "effective_hfov_deg"
                ]
            ),

            "fx_px": (
                intrinsics[
                    "fx_px"
                ]
            ),

            "cx_px": (
                intrinsics[
                    "cx_px"
                ]
            ),

            "quality": (
                intrinsics[
                    "fit"
                ][
                    "quality"
                ]
            ),
        },

        "manifest": (
            manifest
        ),

        "analysis": (
            analysis
        ),
    }

    result_path = (
        run_dir
        / "repeatability_result.json"
    )

    save_json(
        result_path,
        output,
    )

    print()

    print(
        f"Result:\n"
        f"{result_path}"
    )

    print(
        f"Debug matches:\n"
        f"{run_dir / 'debug_matches'}"
    )

    print(
        "=" * 78
    )


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- PTZ Directional Repeatability"
        )
    )

    parser.add_argument(
        "--targets",
        type=int,
        nargs="+",
        default=[
            1,
            4,
            7,
            8,
        ],
        help=(
            "Target presets. "
            "Default: 1 4 7 8"
        ),
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help=(
            "Repeats per approach "
            "(default: 3)"
        ),
    )

    parser.add_argument(
        "--ratio",
        type=float,
        default=0.75,
        help=(
            "ORB Lowe ratio "
            "(default: 0.75)"
        ),
    )

    parser.add_argument(
        "--min-matches",
        type=int,
        default=20,
        help=(
            "Minimum RANSAC inliers "
            "(default: 20)"
        ),
    )

    args = (
        parser.parse_args()
    )

    if (
        args.repeats
        < 2
    ):
        raise SystemExit(
            "❌ --repeats "
            "must be >= 2"
        )

    if not (
        0.5
        <= args.ratio
        < 1.0
    ):
        raise SystemExit(
            "❌ --ratio "
            "must be 0.5 .. <1.0"
        )

    if (
        args.min_matches
        < 8
    ):
        raise SystemExit(
            "❌ --min-matches "
            "must be >= 8"
        )

    run_test(
        targets=(
            args.targets
        ),

        repeats=(
            args.repeats
        ),

        ratio_threshold=(
            args.ratio
        ),

        min_matches=(
            args.min_matches
        ),
    )


if __name__ == "__main__":
    main()
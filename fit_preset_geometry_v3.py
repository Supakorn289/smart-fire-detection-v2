#!/usr/bin/env python3
# fit_preset_geometry_v3.py

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
# Paths
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
    / "preset_geometry_v3.json"
)


# ============================================================
# Required presets
# ============================================================

PRESETS = list(
    range(1, 10)
)

ANCHOR_PRESET = 1


# ============================================================
# Load JSON
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
            "❌ camera_intrinsics.json "
            "ยังไม่ผ่าน Production validation"
        )

    if (
        data.get("status")
        != "intrinsics_calibrated"
    ):
        raise SystemExit(
            "❌ Intrinsic calibration "
            "status is not calibrated"
        )

    matrix = np.asarray(
        data["camera_matrix"],
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

    width = int(
        data[
            "frame_width"
        ]
    )

    height = int(
        data[
            "frame_height"
        ]
    )

    return (
        data,
        matrix,
        distortion,
        width,
        height,
    )


# ============================================================
# Pixel -> undistorted optical ray
# ============================================================

def pixel_to_ray(
    x_px,
    y_px,
    camera_matrix,
    distortion,
):
    """
    Convert raw distorted image pixel into
    normalized undistorted camera ray.

    OpenCV result:
        x_normalized
        y_normalized

    Camera ray:
        [x_normalized, y_normalized, 1]
    """

    point = np.asarray(
        [
            [
                [
                    float(
                        x_px
                    ),
                    float(
                        y_px
                    ),
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

    y_norm = float(
        undistorted[
            0,
            0,
            1,
        ]
    )

    return (
        x_norm,
        y_norm,
    )


def pixel_horizontal_angle_deg(
    x_px,
    y_px,
    camera_matrix,
    distortion,
):
    """
    Horizontal optical angle relative
    to the camera optical axis.

    Negative = left
    Positive = right
    """

    x_norm, _ = (
        pixel_to_ray(
            x_px,
            y_px,
            camera_matrix,
            distortion,
        )
    )

    return math.degrees(
        math.atan2(
            x_norm,
            1.0,
        )
    )


# ============================================================
# Angle normalization
# ============================================================

def normalize_signed_deg(
    angle,
):
    """
    Normalize into [-180, 180).
    """

    return (
        (
            float(angle)
            + 180.0
        )
        % 360.0
    ) - 180.0


def angle_difference_deg(
    a,
    b,
):
    """
    Signed angular difference a - b.
    """

    return normalize_signed_deg(
        float(a)
        - float(b)
    )


# ============================================================
# Load observations
# ============================================================

def build_observations(
    marks,
    camera_matrix,
    distortion,
):
    """
    For one same physical reference:

        C_a + offset_a
        =
        C_b + offset_b

    Therefore:

        C_b - C_a
        =
        offset_a - offset_b

    C = actual relative center angle
        of each PTZ preset.
    """

    pairs = (
        marks.get(
            "pairs",
            {}
        )
    )

    if not pairs:
        raise SystemExit(
            "❌ overlap_marks.json "
            "does not contain pairs"
        )

    observations = []

    pair_reports = []

    graph_edges = []

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

        matches = (
            pair.get(
                "matches",
                []
            )
        )

        if len(matches) < 2:
            print(
                f"⚠️ Skip "
                f"{pair_name}: "
                "matches < 2"
            )

            continue

        graph_edges.append(
            (
                preset_a,
                preset_b,
            )
        )

        pair_deltas = []

        for index, match in enumerate(
            matches,
            start=1,
        ):
            xa = float(
                match[
                    "x_a_px"
                ]
            )

            ya = float(
                match[
                    "y_a_px"
                ]
            )

            xb = float(
                match[
                    "x_b_px"
                ]
            )

            yb = float(
                match[
                    "y_b_px"
                ]
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

            # C_b - C_a
            delta_center = (
                angle_a
                - angle_b
            )

            pair_deltas.append(
                delta_center
            )

            observations.append(
                {
                    "pair": (
                        pair_name
                    ),

                    "match": (
                        index
                    ),

                    "preset_a": (
                        preset_a
                    ),

                    "preset_b": (
                        preset_b
                    ),

                    "x_a_px": (
                        xa
                    ),

                    "y_a_px": (
                        ya
                    ),

                    "x_b_px": (
                        xb
                    ),

                    "y_b_px": (
                        yb
                    ),

                    "offset_a_deg": (
                        angle_a
                    ),

                    "offset_b_deg": (
                        angle_b
                    ),

                    "measured_delta_deg": (
                        delta_center
                    ),
                }
            )

        pair_reports.append(
            {
                "pair": (
                    pair_name
                ),

                "preset_a": (
                    preset_a
                ),

                "preset_b": (
                    preset_b
                ),

                "matches": (
                    len(
                        pair_deltas
                    )
                ),

                "delta_values_deg": (
                    pair_deltas
                ),

                "mean_delta_deg": float(
                    np.mean(
                        pair_deltas
                    )
                ),

                "median_delta_deg": float(
                    np.median(
                        pair_deltas
                    )
                ),

                "std_delta_deg": float(
                    np.std(
                        pair_deltas
                    )
                ),
            }
        )

    return (
        observations,
        pair_reports,
        graph_edges,
    )


# ============================================================
# Graph connectivity check
# ============================================================

def validate_graph(
    edges,
):
    adjacency = {
        preset: set()
        for preset in PRESETS
    }

    for a, b in edges:
        adjacency[
            a
        ].add(
            b
        )

        adjacency[
            b
        ].add(
            a
        )

    visited = set()

    stack = [
        ANCHOR_PRESET
    ]

    while stack:
        current = (
            stack.pop()
        )

        if current in visited:
            continue

        visited.add(
            current
        )

        stack.extend(
            adjacency.get(
                current,
                []
            )
        )

    missing = (
        set(
            PRESETS
        )
        - visited
    )

    if missing:
        raise SystemExit(
            "❌ Preset observation graph "
            "is disconnected.\n"
            f"Missing presets: "
            f"{sorted(missing)}"
        )


# ============================================================
# Global least squares
# ============================================================

def solve_geometry(
    observations,
):
    """
    Anchor:
        P1 = 0°

    Unknown:
        P2 ... P9

    Observation:

        C_b - C_a = measured_delta
    """

    unknown_presets = [
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
            unknown_presets
        )
    }

    rows = []

    rhs = []

    for obs in observations:
        preset_a = (
            obs[
                "preset_a"
            ]
        )

        preset_b = (
            obs[
                "preset_b"
            ]
        )

        row = np.zeros(
            len(
                unknown_presets
            ),
            dtype=np.float64,
        )

        # C_b
        if (
            preset_b
            != ANCHOR_PRESET
        ):
            row[
                index_map[
                    preset_b
                ]
            ] += 1.0

        # -C_a
        if (
            preset_a
            != ANCHOR_PRESET
        ):
            row[
                index_map[
                    preset_a
                ]
            ] -= 1.0

        rows.append(
            row
        )

        rhs.append(
            float(
                obs[
                    "measured_delta_deg"
                ]
            )
        )

    if not rows:
        raise SystemExit(
            "❌ No usable observations"
        )

    A = np.vstack(
        rows
    )

    b = np.asarray(
        rhs,
        dtype=np.float64,
    )

    solution, _, rank, singular_values = (
        np.linalg.lstsq(
            A,
            b,
            rcond=None,
        )
    )

    if rank < len(
        unknown_presets
    ):
        raise SystemExit(
            "❌ Geometry system "
            "is rank deficient"
        )

    centers = {
        ANCHOR_PRESET: (
            0.0
        )
    }

    for preset in unknown_presets:
        centers[
            preset
        ] = float(
            solution[
                index_map[
                    preset
                ]
            ]
        )

    predicted = (
        A @ solution
    )

    residuals = (
        predicted
        - b
    )

    return (
        centers,
        residuals,
        rank,
        singular_values,
    )


# ============================================================
# Quality
# ============================================================

def classify_quality(
    rms,
    max_abs,
):
    """
    Relative geometry consistency.

    excellent:
        RMS <= 0.25°
        Max <= 0.75°

    good:
        RMS <= 0.50°
        Max <= 1.50°

    needs_validation:
        RMS <= 1.00°
        Max <= 3.00°

    otherwise:
        redo_recommended
    """

    if (
        rms <= 0.25
        and
        max_abs <= 0.75
    ):
        return (
            "excellent"
        )

    if (
        rms <= 0.50
        and
        max_abs <= 1.50
    ):
        return (
            "good"
        )

    if (
        rms <= 1.00
        and
        max_abs <= 3.00
    ):
        return (
            "needs_validation"
        )

    return (
        "redo_recommended"
    )


# ============================================================
# Pair residual report
# ============================================================

def build_residual_report(
    observations,
    centers,
):
    result = []

    residual_values = []

    pair_values = {}

    for obs in observations:
        preset_a = (
            obs[
                "preset_a"
            ]
        )

        preset_b = (
            obs[
                "preset_b"
            ]
        )

        fitted_delta = (
            centers[
                preset_b
            ]
            -
            centers[
                preset_a
            ]
        )

        measured_delta = (
            obs[
                "measured_delta_deg"
            ]
        )

        residual = (
            fitted_delta
            -
            measured_delta
        )

        residual_values.append(
            residual
        )

        pair_name = (
            obs[
                "pair"
            ]
        )

        pair_values.setdefault(
            pair_name,
            []
        ).append(
            residual
        )

        result.append(
            {
                **obs,

                "fitted_delta_deg": (
                    fitted_delta
                ),

                "residual_deg": (
                    residual
                ),
            }
        )

    pair_summary = {}

    for pair_name, values in (
        pair_values.items()
    ):
        pair_summary[
            pair_name
        ] = {
            "samples": (
                len(
                    values
                )
            ),

            "mean_residual_deg": float(
                np.mean(
                    values
                )
            ),

            "rms_residual_deg": float(
                math.sqrt(
                    float(
                        np.mean(
                            np.square(
                                values
                            )
                        )
                    )
                )
            ),

            "max_abs_residual_deg": float(
                np.max(
                    np.abs(
                        values
                    )
                )
            ),
        }

    return (
        result,
        residual_values,
        pair_summary,
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
        "Preset Geometry Calibration v3"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # Intrinsics
    # ========================================================

    (
        intrinsics,
        camera_matrix,
        distortion,
        width,
        height,
    ) = load_intrinsics()

    print(
        "✅ Camera intrinsics loaded"
    )

    print(
        f"Resolution : "
        f"{width}x{height}"
    )

    print(
        f"fx         : "
        f"{intrinsics['fx_px']:.3f}px"
    )

    print(
        f"cx         : "
        f"{intrinsics['cx_px']:.3f}px"
    )

    print(
        f"HFOV       : "
        f"{intrinsics['effective_hfov_deg']:.3f}°"
    )

    print(
        f"Quality    : "
        f"{intrinsics['fit']['quality']}"
    )

    # ========================================================
    # Marks
    # ========================================================

    marks = load_json(
        MARKS_FILE
    )

    mark_width = int(
        marks.get(
            "frame_width",
            width,
        )
    )

    mark_height = int(
        marks.get(
            "frame_height",
            height,
        )
    )

    if (
        mark_width != width
        or
        mark_height != height
    ):
        raise SystemExit(
            "❌ Resolution mismatch:\n"
            f"Intrinsics = "
            f"{width}x{height}\n"
            f"Marks      = "
            f"{mark_width}x{mark_height}"
        )

    (
        observations,
        pair_reports,
        graph_edges,
    ) = build_observations(
        marks,
        camera_matrix,
        distortion,
    )

    print(
        f"✅ Overlap observations: "
        f"{len(observations)}"
    )

    print(
        f"✅ Overlap pairs       : "
        f"{len(pair_reports)}"
    )

    # ========================================================
    # Graph validation
    # ========================================================

    validate_graph(
        graph_edges
    )

    print(
        "✅ Preset graph connected"
    )

    # ========================================================
    # Solve
    # ========================================================

    (
        centers,
        _solver_residuals,
        rank,
        singular_values,
    ) = solve_geometry(
        observations
    )

    (
        observation_report,
        residual_values,
        pair_residual_summary,
    ) = build_residual_report(
        observations,
        centers,
    )

    residual_array = (
        np.asarray(
            residual_values,
            dtype=np.float64,
        )
    )

    rms = float(
        math.sqrt(
            float(
                np.mean(
                    residual_array
                    ** 2
                )
            )
        )
    )

    mean_abs = float(
        np.mean(
            np.abs(
                residual_array
            )
        )
    )

    max_abs = float(
        np.max(
            np.abs(
                residual_array
            )
        )
    )

    quality = (
        classify_quality(
            rms,
            max_abs,
        )
    )

    valid_relative = (
        quality
        in {
            "excellent",
            "good",
        }
    )

    # ========================================================
    # Normalize centers
    # ========================================================

    fitted = {
        preset: (
            normalize_signed_deg(
                centers[
                    preset
                ]
            )
        )
        for preset
        in PRESETS
    }

    nominal = {
        int(preset): float(
            angle
        )
        for preset, angle
        in PRESET_PAN_DEG.items()
    }

    corrections = {
        preset: (
            angle_difference_deg(
                fitted[
                    preset
                ],
                nominal[
                    preset
                ],
            )
        )
        for preset
        in PRESETS
    }

    # ========================================================
    # Results
    # ========================================================

    print(
        "\n"
        + "-" * 78
    )

    print(
        "PRESET GEOMETRY RESULT"
    )

    print(
        "-" * 78
    )

    print(
        f"Observations : "
        f"{len(observations)}"
    )

    print(
        f"Rank         : "
        f"{rank}"
    )

    print(
        f"RMS error    : "
        f"{rms:.6f}°"
    )

    print(
        f"Mean abs     : "
        f"{mean_abs:.6f}°"
    )

    print(
        f"Max error    : "
        f"{max_abs:.6f}°"
    )

    print(
        f"Quality      : "
        f"{quality}"
    )

    print(
        f"Relative use : "
        f"{'YES' if valid_relative else 'NO'}"
    )

    print()

    print(
        "Preset | Nominal       Fitted       Correction"
    )

    print(
        "-" * 55
    )

    for preset in PRESETS:
        print(
            f"P{preset:<2d}    "
            f"{nominal[preset]:>+10.3f}° "
            f"{fitted[preset]:>+10.3f}° "
            f"{corrections[preset]:>+10.3f}°"
        )

    # ========================================================
    # Pair report
    # ========================================================

    print(
        "\n"
        + "-" * 78
    )

    print(
        "PAIR CONSISTENCY"
    )

    print(
        "-" * 78
    )

    for pair_name in sorted(
        pair_residual_summary
    ):
        info = (
            pair_residual_summary[
                pair_name
            ]
        )

        print(
            f"{pair_name:<8s} "
            f"| n="
            f"{info['samples']} "
            f"| RMS="
            f"{info['rms_residual_deg']:.4f}° "
            f"| Max="
            f"{info['max_abs_residual_deg']:.4f}°"
        )

    # ========================================================
    # Correction warnings
    # ========================================================

    large_corrections = []

    for preset, correction in (
        corrections.items()
    ):
        if abs(
            correction
        ) > 10.0:
            large_corrections.append(
                (
                    preset,
                    correction,
                )
            )

    if large_corrections:
        print()

        print(
            "⚠️ Large preset corrections:"
        )

        for (
            preset,
            correction,
        ) in large_corrections:
            print(
                f"  P{preset}: "
                f"{correction:+.3f}°"
            )

        print(
            "ยังไม่ควรนำ Geometry "
            "เข้า World Bearing จน Verify"
        )

    # ========================================================
    # Save
    # ========================================================

    output = {
        "version": 3,

        "created_at": (
            time.time()
        ),

        "status": (
            "relative_geometry_calibrated"
            if valid_relative
            else "relative_geometry_unverified"
        ),

        "valid_for_relative_geometry": (
            valid_relative
        ),

        # ยังไม่ได้ผูกกับ North
        "valid_for_world_bearing": (
            False
        ),

        "absolute_north_calibrated": (
            False
        ),

        "anchor": {
            "preset": (
                ANCHOR_PRESET
            ),

            "relative_pan_deg": (
                0.0
            ),
        },

        "intrinsics_source": (
            str(
                INTRINSICS_FILE
            )
        ),

        "marks_source": (
            str(
                MARKS_FILE
            )
        ),

        "frame_width": (
            width
        ),

        "frame_height": (
            height
        ),

        "camera_intrinsics": {
            "fx_px": (
                float(
                    intrinsics[
                        "fx_px"
                    ]
                )
            ),

            "fy_px": (
                float(
                    intrinsics[
                        "fy_px"
                    ]
                )
            ),

            "cx_px": (
                float(
                    intrinsics[
                        "cx_px"
                    ]
                )
            ),

            "cy_px": (
                float(
                    intrinsics[
                        "cy_px"
                    ]
                )
            ),

            "effective_hfov_deg": (
                float(
                    intrinsics[
                        "effective_hfov_deg"
                    ]
                )
            ),

            "distortion_coefficients": (
                intrinsics[
                    "distortion_coefficients"
                ]
            ),
        },

        "preset_relative_pan_deg": {
            str(preset): round(
                float(
                    fitted[
                        preset
                    ]
                ),
                9,
            )
            for preset
            in PRESETS
        },

        "preset_nominal_pan_deg": {
            str(preset): (
                nominal[
                    preset
                ]
            )
            for preset
            in PRESETS
        },

        "preset_correction_deg": {
            str(preset): round(
                float(
                    corrections[
                        preset
                    ]
                ),
                9,
            )
            for preset
            in PRESETS
        },

        "fit": {
            "observations": (
                len(
                    observations
                )
            ),

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

            "quality": (
                quality
            ),
        },

        "pair_consistency": (
            pair_residual_summary
        ),

        "observations": (
            observation_report
        ),

        "notes": [
            (
                "Camera distortion is removed "
                "before calculating pixel angle."
            ),

            (
                "Preset 1 is the relative "
                "zero-angle anchor."
            ),

            (
                "This calibration does not "
                "define True North."
            ),

            (
                "Do not enable GPS solely "
                "from this file."
            ),

            (
                "World bearing requires "
                "absolute north calibration."
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

    print(
        "\n"
        + "=" * 78
    )

    print(
        f"Saved: "
        f"{OUTPUT_FILE}"
    )

    print(
        "=" * 78
    )

    if valid_relative:
        print(
            "✅ Preset Relative Geometry "
            "ผ่านเกณฑ์"
        )

        print(
            "➡️ ขั้นต่อไป: "
            "Overlap Bearing Validation"
        )

    else:
        print(
            "⚠️ Preset Relative Geometry "
            "ยังไม่ผ่าน"
        )

        print(
            "ห้ามนำเข้า Production"
        )


if __name__ == "__main__":
    main()
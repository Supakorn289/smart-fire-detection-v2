#!/usr/bin/env python3
# refine_overlap_marks_v3.py

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from config import CALIBRATION_DIR


# ============================================================
# Paths
# ============================================================

WORK_DIR = (
    CALIBRATION_DIR
    / "bearing_v2"
)

IMAGE_DIR = (
    WORK_DIR
    / "images"
)

MARKS_FILE = (
    WORK_DIR
    / "overlap_marks.json"
)

INTRINSICS_FILE = (
    CALIBRATION_DIR
    / "camera_intrinsics.json"
)


# ============================================================
# Pairs to refine
# ============================================================
#
# 2-3, 4-5, 8-9
#   = noisy pairs from Geometry v3
#
# 5-9
#   = NEW loop-closure pair around ±180 degrees
#
# ============================================================

REFINE_PAIRS = [
    (2, 3),
    (4, 5),
    (8, 9),
    (5, 9),
]


# ============================================================
# QA thresholds
# ============================================================
#
# ใช้เพื่อ "เตือน" เท่านั้น
# ไม่บล็อกการ Save
#
# Matching point ของคู่เดียวกันควรให้
# center-delta ใกล้กันหลาย ๆ จุด
#
# ============================================================

QA_STD_WARNING_DEG = 0.75
QA_RANGE_WARNING_DEG = 2.00


# ============================================================
# JSON helpers
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

    tmp = path.with_suffix(
        ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        path
    )


# ============================================================
# Backup
# ============================================================

def backup_marks():
    if not MARKS_FILE.exists():
        raise SystemExit(
            f"❌ Missing:\n{MARKS_FILE}"
        )

    stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = (
        WORK_DIR
        / (
            "overlap_marks_backup_"
            f"{stamp}.json"
        )
    )

    counter = 1

    while backup.exists():
        backup = (
            WORK_DIR
            / (
                "overlap_marks_backup_"
                f"{stamp}_{counter}.json"
            )
        )

        counter += 1

    shutil.copy2(
        MARKS_FILE,
        backup,
    )

    print(
        f"📦 Backup created:\n"
        f"   {backup}"
    )

    return backup


# ============================================================
# Camera intrinsics
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
            "❌ Intrinsic status "
            "ไม่ใช่ intrinsics_calibrated"
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
# Pixel -> undistorted horizontal angle
# ============================================================

def pixel_horizontal_angle_deg(
    x_px,
    y_px,
    camera_matrix,
    distortion,
):
    """
    Raw distorted image pixel
        ↓
    undistortPoints()
        ↓
    normalized optical ray
        ↓
    horizontal angle

    Negative = left
    Positive = right
    """

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
# Pair QA
# ============================================================

def calculate_pair_qa(
    matches,
    camera_matrix,
    distortion,
):
    """
    Same physical point:

        center_a + offset_a
        =
        center_b + offset_b

    Therefore:

        center_b - center_a
        =
        offset_a - offset_b

    ทุก matching point ในคู่เดียวกัน
    ควรให้ delta ใกล้กัน
    """

    values = []

    for match in matches:
        angle_a = (
            pixel_horizontal_angle_deg(
                match["x_a_px"],
                match["y_a_px"],
                camera_matrix,
                distortion,
            )
        )

        angle_b = (
            pixel_horizontal_angle_deg(
                match["x_b_px"],
                match["y_b_px"],
                camera_matrix,
                distortion,
            )
        )

        delta = (
            angle_a
            - angle_b
        )

        values.append(
            float(delta)
        )

    if not values:
        return {
            "count": 0,
            "values": [],
            "mean": None,
            "median": None,
            "std": None,
            "range": None,
            "min": None,
            "max": None,
        }

    array = np.asarray(
        values,
        dtype=np.float64,
    )

    return {
        "count": len(values),

        "values": values,

        "mean": float(
            np.mean(array)
        ),

        "median": float(
            np.median(array)
        ),

        "std": float(
            np.std(array)
        ),

        "range": float(
            np.max(array)
            - np.min(array)
        ),

        "min": float(
            np.min(array)
        ),

        "max": float(
            np.max(array)
        ),
    }


def print_pair_qa(
    preset_a,
    preset_b,
    matches,
    camera_matrix,
    distortion,
):
    qa = calculate_pair_qa(
        matches,
        camera_matrix,
        distortion,
    )

    print(
        "\n"
        f"📐 P{preset_a} ↔ P{preset_b} QA"
    )

    if qa["count"] == 0:
        print(
            "   no points"
        )

        return qa

    for index, value in enumerate(
        qa["values"],
        start=1,
    ):
        print(
            f"   #{index}: "
            f"delta="
            f"{value:+.4f}°"
        )

    print(
        f"   median = "
        f"{qa['median']:+.4f}°"
    )

    print(
        f"   mean   = "
        f"{qa['mean']:+.4f}°"
    )

    print(
        f"   std    = "
        f"{qa['std']:.4f}°"
    )

    print(
        f"   range  = "
        f"{qa['range']:.4f}°"
    )

    if (
        qa["count"] >= 3
        and
        (
            qa["std"]
            > QA_STD_WARNING_DEG
            or
            qa["range"]
            > QA_RANGE_WARNING_DEG
        )
    ):
        print(
            "   ⚠️ QA WARNING:"
        )

        print(
            "      Matching points "
            "กระจายมากกว่าที่คาด"
        )

        print(
            "      ตรวจว่าเป็น "
            "จุดเดียวกันจริงหรือไม่"
        )

    elif qa["count"] >= 3:
        print(
            "   ✅ Point consistency "
            "ดูสมเหตุสมผล"
        )

    return qa


# ============================================================
# Pair marker GUI
# ============================================================

class PairMarker:

    def __init__(
        self,
        preset_a,
        preset_b,
        image_a,
        image_b,
        *,
        camera_matrix,
        distortion,
        scale,
        min_points,
    ):
        self.preset_a = int(
            preset_a
        )

        self.preset_b = int(
            preset_b
        )

        self.image_a = (
            image_a
        )

        self.image_b = (
            image_b
        )

        self.camera_matrix = (
            camera_matrix
        )

        self.distortion = (
            distortion
        )

        self.scale = float(
            scale
        )

        self.min_points = int(
            min_points
        )

        # Refinement:
        # เริ่มใหม่จาก 0 จุดเสมอ
        self.points = []

        self.pending_left = None

        # ----------------------------------------------------
        # Display images
        # ----------------------------------------------------

        self.display_a = cv2.resize(
            image_a,
            None,
            fx=self.scale,
            fy=self.scale,
            interpolation=(
                cv2.INTER_AREA
            ),
        )

        self.display_b = cv2.resize(
            image_b,
            None,
            fx=self.scale,
            fy=self.scale,
            interpolation=(
                cv2.INTER_AREA
            ),
        )

        if (
            self.display_a.shape[0]
            !=
            self.display_b.shape[0]
        ):
            raise ValueError(
                "Display image "
                "heights differ"
            )

        self.left_width = int(
            self.display_a.shape[1]
        )

        self.display_height = int(
            self.display_a.shape[0]
        )

        self.window_name = (
            f"Refine Geometry v3 "
            f"| P{preset_a} LEFT "
            f"<-> "
            f"P{preset_b} RIGHT"
        )


    # ========================================================
    # QA values
    # ========================================================

    def _qa(
        self,
    ):
        return calculate_pair_qa(
            self.points,
            self.camera_matrix,
            self.distortion,
        )


    # ========================================================
    # Draw
    # ========================================================

    def _draw(
        self,
    ):
        canvas = np.hstack(
            [
                self.display_a.copy(),
                self.display_b.copy(),
            ]
        )

        # ----------------------------------------------------
        # Separator
        # ----------------------------------------------------

        cv2.line(
            canvas,
            (
                self.left_width,
                0,
            ),
            (
                self.left_width,
                self.display_height - 1,
            ),
            (
                255,
                255,
                255,
            ),
            2,
        )

        # ----------------------------------------------------
        # Existing points
        # ----------------------------------------------------

        for index, item in enumerate(
            self.points,
            start=1,
        ):
            xa = int(
                round(
                    item[
                        "x_a_px"
                    ]
                    * self.scale
                )
            )

            ya = int(
                round(
                    item[
                        "y_a_px"
                    ]
                    * self.scale
                )
            )

            xb_local = int(
                round(
                    item[
                        "x_b_px"
                    ]
                    * self.scale
                )
            )

            xb = (
                self.left_width
                + xb_local
            )

            yb = int(
                round(
                    item[
                        "y_b_px"
                    ]
                    * self.scale
                )
            )

            # Same match line

            cv2.line(
                canvas,
                (
                    xa,
                    ya,
                ),
                (
                    xb,
                    yb,
                ),
                (
                    80,
                    180,
                    80,
                ),
                1,
                cv2.LINE_AA,
            )

            # Left point

            cv2.circle(
                canvas,
                (
                    xa,
                    ya,
                ),
                6,
                (
                    0,
                    255,
                    0,
                ),
                -1,
            )

            # Right point

            cv2.circle(
                canvas,
                (
                    xb,
                    yb,
                ),
                6,
                (
                    0,
                    255,
                    0,
                ),
                -1,
            )

            cv2.putText(
                canvas,
                str(index),
                (
                    xa + 8,
                    ya - 8,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (
                    0,
                    255,
                    0,
                ),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                canvas,
                str(index),
                (
                    xb + 8,
                    yb - 8,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (
                    0,
                    255,
                    0,
                ),
                2,
                cv2.LINE_AA,
            )

        # ----------------------------------------------------
        # Pending left point
        # ----------------------------------------------------

        if (
            self.pending_left
            is not None
        ):
            xa = int(
                round(
                    self.pending_left[0]
                    * self.scale
                )
            )

            ya = int(
                round(
                    self.pending_left[1]
                    * self.scale
                )
            )

            cv2.circle(
                canvas,
                (
                    xa,
                    ya,
                ),
                9,
                (
                    0,
                    255,
                    255,
                ),
                2,
            )

        # ----------------------------------------------------
        # HUD
        # ----------------------------------------------------

        qa = self._qa()

        title = (
            f"P{self.preset_a} LEFT "
            f"<-> "
            f"P{self.preset_b} RIGHT "
            f"| points="
            f"{len(self.points)}/"
            f"{self.min_points}"
        )

        instruction = (
            "Click SAME fixed point: "
            "LEFT first -> RIGHT second"
        )

        controls = (
            "N=next  U=undo  "
            "R=reset  Q=save+quit"
        )

        cv2.putText(
            canvas,
            title,
            (
                10,
                24,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (
                0,
                255,
                255,
            ),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            canvas,
            instruction,
            (
                10,
                48,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (
                0,
                255,
                255,
            ),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            canvas,
            controls,
            (
                10,
                72,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (
                0,
                255,
                255,
            ),
            2,
            cv2.LINE_AA,
        )

        if (
            qa["count"]
            >= 2
        ):
            qa_text = (
                f"delta median="
                f"{qa['median']:+.3f} deg "
                f"| std="
                f"{qa['std']:.3f} "
                f"| range="
                f"{qa['range']:.3f}"
            )

            if (
                qa["std"]
                > QA_STD_WARNING_DEG
                or
                qa["range"]
                > QA_RANGE_WARNING_DEG
            ):
                qa_color = (
                    0,
                    165,
                    255,
                )

            else:
                qa_color = (
                    0,
                    255,
                    0,
                )

            cv2.putText(
                canvas,
                qa_text,
                (
                    10,
                    96,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                qa_color,
                2,
                cv2.LINE_AA,
            )

        return canvas


    # ========================================================
    # Mouse callback
    # ========================================================

    def _mouse(
        self,
        event,
        x,
        y,
        _flags,
        _param,
    ):
        if (
            event
            !=
            cv2.EVENT_LBUTTONDOWN
        ):
            return

        # ----------------------------------------------------
        # LEFT image
        # ----------------------------------------------------

        if (
            x
            < self.left_width
        ):
            self.pending_left = (
                x
                / self.scale,
                y
                / self.scale,
            )

            print(
                f"LEFT "
                f"x="
                f"{self.pending_left[0]:.2f} "
                f"y="
                f"{self.pending_left[1]:.2f}"
            )

            print(
                "→ คลิกจุดเดียวกัน "
                "ในภาพขวา"
            )

            return

        # ----------------------------------------------------
        # RIGHT image
        # ----------------------------------------------------

        if (
            self.pending_left
            is None
        ):
            print(
                "⚠️ คลิกภาพซ้ายก่อน"
            )

            return

        right_x = (
            x
            - self.left_width
        ) / self.scale

        right_y = (
            y
            / self.scale
        )

        item = {
            "x_a_px": round(
                float(
                    self.pending_left[0]
                ),
                3,
            ),

            "y_a_px": round(
                float(
                    self.pending_left[1]
                ),
                3,
            ),

            "x_b_px": round(
                float(
                    right_x
                ),
                3,
            ),

            "y_b_px": round(
                float(
                    right_y
                ),
                3,
            ),
        }

        self.points.append(
            item
        )

        # ----------------------------------------------------
        # Calculate optical delta immediately
        # ----------------------------------------------------

        angle_a = (
            pixel_horizontal_angle_deg(
                item["x_a_px"],
                item["y_a_px"],
                self.camera_matrix,
                self.distortion,
            )
        )

        angle_b = (
            pixel_horizontal_angle_deg(
                item["x_b_px"],
                item["y_b_px"],
                self.camera_matrix,
                self.distortion,
            )
        )

        delta = (
            angle_a
            - angle_b
        )

        print(
            f"RIGHT "
            f"x={right_x:.2f} "
            f"y={right_y:.2f}"
        )

        print(
            f"✅ Match "
            f"#{len(self.points)} "
            f"| optical delta="
            f"{delta:+.4f}°"
        )

        self.pending_left = None


    # ========================================================
    # GUI loop
    # ========================================================

    def run(
        self,
    ):
        cv2.namedWindow(
            self.window_name,
            cv2.WINDOW_NORMAL,
        )

        cv2.setMouseCallback(
            self.window_name,
            self._mouse,
        )

        try:
            while True:
                canvas = (
                    self._draw()
                )

                cv2.imshow(
                    self.window_name,
                    canvas,
                )

                key = (
                    cv2.waitKey(30)
                    & 0xFF
                )

                # =============================================
                # Undo
                # =============================================

                if key in (
                    ord("u"),
                    ord("U"),
                ):
                    if (
                        self.pending_left
                        is not None
                    ):
                        self.pending_left = (
                            None
                        )

                        print(
                            "↩️ Pending left "
                            "click cleared"
                        )

                    elif self.points:
                        removed = (
                            self.points.pop()
                        )

                        print(
                            "↩️ Removed match:"
                        )

                        print(
                            f"   {removed}"
                        )

                # =============================================
                # Reset
                # =============================================

                elif key in (
                    ord("r"),
                    ord("R"),
                ):
                    self.points = []

                    self.pending_left = None

                    print(
                        "🗑️ Current pair reset"
                    )

                # =============================================
                # Next
                # =============================================

                elif key in (
                    ord("n"),
                    ord("N"),
                ):
                    if (
                        len(self.points)
                        < self.min_points
                    ):
                        print(
                            "⚠️ ต้องมีอย่างน้อย "
                            f"{self.min_points} จุด"
                        )

                        continue

                    qa = print_pair_qa(
                        self.preset_a,
                        self.preset_b,
                        self.points,
                        self.camera_matrix,
                        self.distortion,
                    )

                    if (
                        qa["std"]
                        > QA_STD_WARNING_DEG
                        or
                        qa["range"]
                        > QA_RANGE_WARNING_DEG
                    ):
                        print(
                            "⚠️ QA warning "
                            "แต่ระบบยังอนุญาตให้ Save"
                        )

                    return (
                        "next",
                        list(
                            self.points
                        ),
                    )

                # =============================================
                # Save + Quit
                # =============================================

                elif key in (
                    ord("q"),
                    ord("Q"),
                    27,
                ):
                    return (
                        "quit",
                        list(
                            self.points
                        ),
                    )

        finally:
            cv2.destroyWindow(
                self.window_name
            )


# ============================================================
# Save pair
# ============================================================

def save_pair(
    marks,
    preset_a,
    preset_b,
    points,
):
    key = (
        f"{preset_a}-{preset_b}"
    )

    marks.setdefault(
        "pairs",
        {},
    )

    marks[
        "pairs"
    ][key] = {
        "preset_a": int(
            preset_a
        ),

        "preset_b": int(
            preset_b
        ),

        "matches": (
            points
        ),

        "refined_at": (
            time.time()
        ),

        "refinement_version": (
            3
        ),
    }

    marks["version"] = max(
        int(
            marks.get(
                "version",
                2,
            )
        ),
        3,
    )

    marks["updated_at"] = (
        time.time()
    )

    marks[
        "geometry_refinement"
    ] = {
        "version": 3,

        "target_pairs": [
            "2-3",
            "4-5",
            "8-9",
            "5-9",
        ],

        "loop_closure_pair": (
            "5-9"
        ),
    }

    save_json(
        MARKS_FILE,
        marks,
    )


# ============================================================
# Summary
# ============================================================

def print_summary(
    marks,
    camera_matrix,
    distortion,
):
    print(
        "\n"
        + "=" * 76
    )

    print(
        "REFINEMENT SUMMARY"
    )

    print(
        "=" * 76
    )

    for (
        preset_a,
        preset_b,
    ) in REFINE_PAIRS:
        key = (
            f"{preset_a}-{preset_b}"
        )

        pair = (
            marks
            .get(
                "pairs",
                {},
            )
            .get(
                key
            )
        )

        if pair is None:
            print(
                f"P{preset_a} ↔ P{preset_b}"
                " | MISSING"
            )

            continue

        matches = (
            pair.get(
                "matches",
                [],
            )
        )

        qa = calculate_pair_qa(
            matches,
            camera_matrix,
            distortion,
        )

        if (
            qa["count"]
            == 0
        ):
            print(
                f"P{preset_a} ↔ P{preset_b}"
                " | 0 points"
            )

            continue

        print(
            f"P{preset_a} ↔ P{preset_b} "
            f"| n="
            f"{qa['count']} "
            f"| median="
            f"{qa['median']:+.4f}° "
            f"| std="
            f"{qa['std']:.4f}° "
            f"| range="
            f"{qa['range']:.4f}°"
        )

    print(
        "=" * 76
    )


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- Refine Overlap Marks v3"
        )
    )

    parser.add_argument(
        "--scale",
        type=float,
        default=0.65,
        help=(
            "GUI scale "
            "(default: 0.65)"
        ),
    )

    parser.add_argument(
        "--min-points",
        type=int,
        default=5,
        help=(
            "Minimum points per pair "
            "(default: 5)"
        ),
    )

    args = (
        parser.parse_args()
    )

    if args.scale <= 0:
        raise SystemExit(
            "❌ --scale must be > 0"
        )

    if args.min_points < 3:
        raise SystemExit(
            "❌ --min-points "
            "must be >= 3"
        )

    print(
        "=" * 76
    )

    print(
        "Smart Fire Detection v2"
    )

    print(
        "Overlap Refinement v3"
    )

    print(
        "=" * 76
    )

    print(
        "Pairs:"
    )

    print(
        "  P2 ↔ P3  refine"
    )

    print(
        "  P4 ↔ P5  refine"
    )

    print(
        "  P8 ↔ P9  refine"
    )

    print(
        "  P5 ↔ P9  NEW loop closure"
    )

    print(
        "=" * 76
    )

    # ========================================================
    # Load intrinsics
    # ========================================================

    (
        intrinsics,
        camera_matrix,
        distortion,
        frame_width,
        frame_height,
    ) = load_intrinsics()

    print(
        "✅ Camera intrinsics loaded"
    )

    print(
        f"   Resolution: "
        f"{frame_width}x"
        f"{frame_height}"
    )

    print(
        f"   HFOV      : "
        f"{intrinsics['effective_hfov_deg']:.3f}°"
    )

    print(
        f"   Quality   : "
        f"{intrinsics['fit']['quality']}"
    )

    # ========================================================
    # Load marks
    # ========================================================

    marks = load_json(
        MARKS_FILE
    )

    mark_width = int(
        marks.get(
            "frame_width",
            frame_width,
        )
    )

    mark_height = int(
        marks.get(
            "frame_height",
            frame_height,
        )
    )

    if (
        mark_width != frame_width
        or
        mark_height != frame_height
    ):
        raise SystemExit(
            "❌ Resolution mismatch\n"
            f"Intrinsics: "
            f"{frame_width}x{frame_height}\n"
            f"Marks     : "
            f"{mark_width}x{mark_height}"
        )

    # ========================================================
    # Backup before modification
    # ========================================================

    backup_marks()

    # ========================================================
    # Process target pairs
    # ========================================================

    for (
        preset_a,
        preset_b,
    ) in REFINE_PAIRS:
        key = (
            f"{preset_a}-{preset_b}"
        )

        old_pair = (
            marks
            .get(
                "pairs",
                {},
            )
            .get(
                key
            )
        )

        old_count = (
            len(
                old_pair.get(
                    "matches",
                    [],
                )
            )
            if old_pair
            else 0
        )

        path_a = (
            IMAGE_DIR
            / f"preset_{preset_a}.jpg"
        )

        path_b = (
            IMAGE_DIR
            / f"preset_{preset_b}.jpg"
        )

        image_a = cv2.imread(
            str(
                path_a
            )
        )

        image_b = cv2.imread(
            str(
                path_b
            )
        )

        if image_a is None:
            raise SystemExit(
                f"❌ Cannot read:\n"
                f"{path_a}"
            )

        if image_b is None:
            raise SystemExit(
                f"❌ Cannot read:\n"
                f"{path_b}"
            )

        ha, wa = (
            image_a.shape[:2]
        )

        hb, wb = (
            image_b.shape[:2]
        )

        if (
            wa != frame_width
            or
            ha != frame_height
            or
            wb != frame_width
            or
            hb != frame_height
        ):
            raise SystemExit(
                "❌ Preset image "
                "resolution mismatch"
            )

        print(
            "\n"
            + "-" * 76
        )

        print(
            f"P{preset_a} ↔ P{preset_b}"
        )

        print(
            f"Old points : "
            f"{old_count}"
        )

        print(
            f"New target : "
            f"{args.min_points}"
        )

        if (
            preset_a == 5
            and
            preset_b == 9
        ):
            print(
                "🔁 LOOP CLOSURE PAIR"
            )

            print(
                "เลือกเฉพาะจุดคงที่ "
                "ที่เห็นร่วมกันจริง"
            )

        marker = PairMarker(
            preset_a,
            preset_b,
            image_a,
            image_b,
            camera_matrix=(
                camera_matrix
            ),
            distortion=(
                distortion
            ),
            scale=(
                args.scale
            ),
            min_points=(
                args.min_points
            ),
        )

        action, points = (
            marker.run()
        )

        # ----------------------------------------------------
        # Save even when Q is used
        # so partial work is recoverable
        # ----------------------------------------------------

        if points:
            save_pair(
                marks,
                preset_a,
                preset_b,
                points,
            )

            print(
                f"💾 Saved "
                f"P{preset_a} ↔ P{preset_b}"
                f" | {len(points)} points"
            )

        else:
            print(
                f"ℹ️ No new points saved "
                f"for P{preset_a} ↔ "
                f"P{preset_b}"
            )

        if (
            action
            == "quit"
        ):
            print(
                "\n🛑 Refinement paused"
            )

            print(
                "รันคำสั่งเดิมอีกครั้ง "
                "เพื่อทำต่อ"
            )

            return

    # ========================================================
    # Final reload
    # ========================================================

    marks = load_json(
        MARKS_FILE
    )

    print_summary(
        marks,
        camera_matrix,
        distortion,
    )

    print(
        "\n✅ Overlap refinement "
        "completed"
    )

    print(
        f"Marks:\n"
        f"{MARKS_FILE}"
    )

    print()

    print(
        "⚠️ ยังไม่ต้องรัน "
        "fit_preset_geometry_v3.py "
        "ตัวเดิม"
    )

    print(
        "P5↔P9 ข้าม ±180° "
        "ต้องใช้ Circular Solver v3.1"
    )


if __name__ == "__main__":
    main()
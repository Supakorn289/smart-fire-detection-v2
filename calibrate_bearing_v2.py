#!/usr/bin/env python3

"""
Smart Fire Detection v2
Bearing Geometry Calibration v2

หา:
- Effective Horizontal FOV
- Principal X
- Relative center angle ของ PTZ Preset 1..9

สำคัญ:
ผลจากไฟล์นี้ยังเป็น Relative Geometry

Preset 1 = 0 degree reference

ยังไม่ใช่ True North
และยังไม่ควรเปิด GPS จาก Calibration นี้เพียงอย่างเดียว

Workflow:

1.
python calibrate_bearing_v2.py capture

2.
python calibrate_bearing_v2.py mark

3.
python calibrate_bearing_v2.py fit
"""

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
    HFOV_DEG,
    INITIAL_PRESET_WAIT_SEC,
    POST_MOVE_FRESH_FRAMES,
    PRESET_PAN_DEG,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
)

from ptz import PTZController


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

MANIFEST_FILE = (
    WORK_DIR
    / "capture_manifest.json"
)

OUTPUT_FILE = (
    CALIBRATION_DIR
    / "bearing_geometry.json"
)


# ============================================================
# Capture route
# ============================================================
#
# ไม่ไปจาก P5 -> P6 โดยตรง
#
# แต่กลับ:
#
# 5 -> 4 -> 3 -> 2 -> 1 -> 6
#
# เพื่อตรงกับ movement logic ที่เราเคยทดสอบแล้ว
# ============================================================

CAPTURE_ROUTE = [
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
]


# ============================================================
# Adjacent overlapping preset pairs
# ============================================================
#
# เราไม่จำเป็นต้องใช้ P5 <-> P9
# เพราะ positive / negative branches
# ถูกเชื่อมผ่าน P1 อยู่แล้ว
# ============================================================

OVERLAP_PAIRS = [
    (1, 2),
    (2, 3),
    (3, 4),
    (4, 5),

    (1, 6),
    (6, 7),
    (7, 8),
    (8, 9),
]


# ============================================================
# Helpers
# ============================================================

def ensure_dirs():
    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    IMAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def wait_fresh_frames(
    camera,
    after_seq,
    count,
):
    seq = after_seq

    packet = None

    for _ in range(
        max(1, count)
    ):

        packet = (
            camera.wait_for_newer(
                seq,
                timeout=2.0,
            )
        )

        if packet is None:
            return None

        seq = packet.seq

    return packet


# ============================================================
# Stable capture
# ============================================================

def capture_stable(
    camera,
    ptz,
    preset,
    first_move=False,
):

    print(
        f"\n🔄 Capture preset "
        f"{preset} "
        f"| nominal pan="
        f"{PRESET_PAN_DEG[preset]:+.1f}°"
    )

    ok, wait_sec = (
        ptz.goto_preset(
            preset
        )
    )

    if not ok:
        raise RuntimeError(
            f"PTZ failed "
            f"at preset {preset}"
        )

    if first_move:

        wait_sec = max(
            wait_sec,
            INITIAL_PRESET_WAIT_SEC,
        )

    print(
        f"⏱️ PTZ wait "
        f"{wait_sec:.2f}s"
    )

    time.sleep(
        wait_sec
    )

    # --------------------------------------------------------
    # Require fresh frame AFTER movement
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
            f"at preset {preset}"
        )

    # --------------------------------------------------------
    # Require stable image
    # --------------------------------------------------------

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:

        raise RuntimeError(
            f"Image not stable "
            f"at preset {preset}"
        )

    print(
        f"✅ Stable "
        f"| seq={stable.seq} "
        f"| age="
        f"{time.time() - stable.timestamp:.3f}s"
    )

    return stable


# ============================================================
# CAPTURE command
# ============================================================

def command_capture(_args):

    ensure_dirs()

    print(
        "=" * 76
    )

    print(
        "Bearing Geometry Calibration v2 "
        "- CAPTURE"
    )

    print(
        "=" * 76
    )

    print(
        "ระบบจะถ่ายภาพ Stable "
        "ของ Preset 1-9"
    )

    print(
        "ใช้ฉากปกติที่มีวัตถุคงที่ "
        "ไม่ต้องใช้ภาพ Fire/Smoke"
    )

    print(
        "=" * 76
    )

    camera = (
        LatestFrameCamera()
        .start()
    )

    try:

        # ----------------------------------------------------
        # RTSP ready
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

        ptz = (
            PTZController()
        )

        captured = {}

        first_move = True

        # ----------------------------------------------------
        # Capture route
        # ----------------------------------------------------

        for preset in CAPTURE_ROUTE:

            packet = capture_stable(
                camera,
                ptz,
                preset,
                first_move=(
                    first_move
                ),
            )

            first_move = False

            # Preset ที่เคย save แล้ว
            # ไม่ต้อง overwrite
            if preset in captured:
                continue

            path = (
                IMAGE_DIR
                / f"preset_{preset}.jpg"
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

            height, width = (
                packet.frame.shape[:2]
            )

            captured[preset] = {

                "preset": (
                    preset
                ),

                "path": (
                    str(path)
                ),

                "seq": (
                    int(
                        packet.seq
                    )
                ),

                "width": (
                    int(
                        width
                    )
                ),

                "height": (
                    int(
                        height
                    )
                ),

                "captured_at": (
                    float(
                        time.time()
                    )
                ),
            }

            print(
                f"💾 Saved "
                f"{path}"
            )

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        missing = [

            preset

            for preset
            in range(1, 10)

            if preset
            not in captured
        ]

        if missing:

            raise RuntimeError(
                "Missing presets: "
                f"{missing}"
            )

        widths = {

            item["width"]

            for item
            in captured.values()
        }

        heights = {

            item["height"]

            for item
            in captured.values()
        }

        if (
            len(widths) != 1
            or len(heights) != 1
        ):

            raise RuntimeError(
                "Captured images have "
                "different resolutions"
            )

        # ----------------------------------------------------
        # Manifest
        # ----------------------------------------------------

        manifest = {

            "version": 2,

            "created_at": (
                time.time()
            ),

            "frame_width": (
                next(
                    iter(widths)
                )
            ),

            "frame_height": (
                next(
                    iter(heights)
                )
            ),

            "nominal_hfov_deg": (
                float(
                    HFOV_DEG
                )
            ),

            "presets": {

                str(key): value

                for key, value
                in sorted(
                    captured.items()
                )
            },
        }

        MANIFEST_FILE.write_text(

            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ),

            encoding="utf-8",
        )

        print(
            "\n"
            + "=" * 76
        )

        print(
            "✅ Capture completed"
        )

        print(
            f"Images   : "
            f"{IMAGE_DIR}"
        )

        print(
            f"Manifest : "
            f"{MANIFEST_FILE}"
        )

        print(
            "=" * 76
        )

    finally:

        camera.stop()


# ============================================================
# Load / save calibration data
# ============================================================

def load_manifest():

    if not MANIFEST_FILE.exists():

        raise SystemExit(
            "❌ capture_manifest.json "
            "not found\n"
            "Run:\n"
            "python calibrate_bearing_v2.py capture"
        )

    return json.loads(
        MANIFEST_FILE.read_text(
            encoding="utf-8"
        )
    )


def load_marks():

    if not MARKS_FILE.exists():

        return {

            "version": 2,

            "pairs": {},
        }

    return json.loads(
        MARKS_FILE.read_text(
            encoding="utf-8"
        )
    )


def save_marks(
    data,
):

    MARKS_FILE.write_text(

        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )


# ============================================================
# GUI Pair Marker
# ============================================================

class PairMarker:

    def __init__(
        self,
        preset_a,
        preset_b,
        image_a,
        image_b,
        existing_points,
        scale,
    ):

        self.preset_a = (
            preset_a
        )

        self.preset_b = (
            preset_b
        )

        self.image_a = (
            image_a
        )

        self.image_b = (
            image_b
        )

        self.scale = (
            scale
        )

        self.points = list(
            existing_points
        )

        self.pending_left = (
            None
        )

        # ----------------------------------------------------
        # Resize for display
        # ----------------------------------------------------

        self.display_a = cv2.resize(
            image_a,
            None,
            fx=scale,
            fy=scale,
            interpolation=(
                cv2.INTER_AREA
            ),
        )

        self.display_b = cv2.resize(
            image_b,
            None,
            fx=scale,
            fy=scale,
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
                "Image heights differ"
            )

        self.left_w = (
            self.display_a.shape[1]
        )

        self.display_h = (
            self.display_a.shape[0]
        )

        self.window_name = (
            f"Bearing v2 "
            f"| P{preset_a} LEFT "
            f"-> P{preset_b} RIGHT"
        )


    # ========================================================
    # Draw GUI
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

        # center separator

        cv2.line(
            canvas,
            (
                self.left_w,
                0,
            ),
            (
                self.left_w,
                self.display_h - 1,
            ),
            (
                255,
                255,
                255,
            ),
            2,
        )

        # ----------------------------------------------------
        # Existing matching points
        # ----------------------------------------------------

        for index, item in enumerate(
            self.points,
            start=1,
        ):

            xa = int(
                round(
                    item["x_a_px"]
                    * self.scale
                )
            )

            ya = int(
                round(
                    item["y_a_px"]
                    * self.scale
                )
            )

            xb = (
                self.left_w
                + int(
                    round(
                        item["x_b_px"]
                        * self.scale
                    )
                )
            )

            yb = int(
                round(
                    item["y_b_px"]
                    * self.scale
                )
            )

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
        # Pending left click
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
                8,
                (
                    0,
                    255,
                    255,
                ),
                2,
            )

        # ----------------------------------------------------
        # Instructions
        # ----------------------------------------------------

        help_lines = [

            (
                f"P{self.preset_a} LEFT "
                f"-> "
                f"P{self.preset_b} RIGHT "
                f"| matches="
                f"{len(self.points)}"
            ),

            (
                "Click SAME fixed point: "
                "LEFT first -> RIGHT second"
            ),

            (
                "N=next  "
                "U=undo  "
                "R=reset  "
                "Q=save+quit"
            ),
        ]

        yy = 24

        for text in help_lines:

            cv2.putText(
                canvas,
                text,
                (
                    10,
                    yy,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (
                    0,
                    255,
                    255,
                ),
                2,
                cv2.LINE_AA,
            )

            yy += 24

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
        # LEFT IMAGE
        # ----------------------------------------------------

        if (
            x
            < self.left_w
        ):

            self.pending_left = (

                x
                / self.scale,

                y
                / self.scale,
            )

            print(
                f"LEFT "
                f"x={self.pending_left[0]:.1f} "
                f"y={self.pending_left[1]:.1f}"
            )

            print(
                "→ คลิกจุดเดียวกัน "
                "ในภาพขวา"
            )

            return

        # ----------------------------------------------------
        # RIGHT IMAGE
        # ----------------------------------------------------

        if (
            self.pending_left
            is None
        ):

            print(
                "⚠️ คลิกภาพซ้ายก่อน"
            )

            return

        right = (

            (
                x
                - self.left_w
            )
            / self.scale,

            y
            / self.scale,
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
                    right[0]
                ),
                3,
            ),

            "y_b_px": round(
                float(
                    right[1]
                ),
                3,
            ),
        }

        self.points.append(
            item
        )

        print(
            f"RIGHT "
            f"x={right[0]:.1f} "
            f"y={right[1]:.1f}"
        )

        print(
            f"✅ Match "
            f"#{len(self.points)}"
        )

        self.pending_left = (
            None
        )


    # ========================================================
    # GUI loop
    # ========================================================

    def run(
        self,
        min_points,
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

                # --------------------------------------------
                # Undo
                # --------------------------------------------

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
                            "↩️ Pending click cleared"
                        )

                    elif self.points:

                        removed = (
                            self.points.pop()
                        )

                        print(
                            "↩️ Removed "
                            f"{removed}"
                        )

                # --------------------------------------------
                # Reset pair
                # --------------------------------------------

                elif key in (
                    ord("r"),
                    ord("R"),
                ):

                    self.points = []

                    self.pending_left = (
                        None
                    )

                    print(
                        "🗑️ Pair reset"
                    )

                # --------------------------------------------
                # Next pair
                # --------------------------------------------

                elif key in (
                    ord("n"),
                    ord("N"),
                ):

                    if (
                        len(self.points)
                        < min_points
                    ):

                        print(
                            "⚠️ ต้องมีอย่างน้อย "
                            f"{min_points} "
                            "matching points"
                        )

                        continue

                    return (
                        "next",
                        self.points,
                    )

                # --------------------------------------------
                # Quit
                # --------------------------------------------

                elif key in (
                    ord("q"),
                    ord("Q"),
                    27,
                ):

                    return (
                        "quit",
                        self.points,
                    )

        finally:

            cv2.destroyWindow(
                self.window_name
            )


# ============================================================
# MARK command
# ============================================================

def command_mark(
    args,
):

    ensure_dirs()

    manifest = (
        load_manifest()
    )

    data = (
        load_marks()
    )

    width = int(
        manifest[
            "frame_width"
        ]
    )

    height = int(
        manifest[
            "frame_height"
        ]
    )

    print(
        "=" * 76
    )

    print(
        "Bearing Geometry Calibration v2 "
        "- MARK"
    )

    print(
        "=" * 76
    )

    print(
        f"Resolution : "
        f"{width}x{height}"
    )

    print(
        f"Minimum    : "
        f"{args.min_points} "
        "points / pair"
    )

    print(
        "Recommended: "
        "3-5 points / pair"
    )

    print()

    print(
        "เลือกจุดคงที่จุดเดียวกัน "
        "ในภาพซ้ายและขวา"
    )

    print(
        "ควรเลือกวัตถุที่อยู่ไกล "
        "และไม่เคลื่อนที่"
    )

    print(
        "=" * 76
    )

    # --------------------------------------------------------
    # Process every overlap pair
    # --------------------------------------------------------

    for (
        preset_a,
        preset_b,
    ) in OVERLAP_PAIRS:

        path_a = (
            IMAGE_DIR
            / f"preset_{preset_a}.jpg"
        )

        path_b = (
            IMAGE_DIR
            / f"preset_{preset_b}.jpg"
        )

        image_a = cv2.imread(
            str(path_a)
        )

        image_b = cv2.imread(
            str(path_b)
        )

        if (
            image_a is None
            or image_b is None
        ):

            raise SystemExit(
                "❌ Missing images "
                f"P{preset_a}/P{preset_b}"
            )

        key = (
            f"{preset_a}-{preset_b}"
        )

        existing = (

            data
            .get(
                "pairs",
                {},
            )
            .get(
                key,
                {},
            )
            .get(
                "matches",
                [],
            )
        )

        print(
            f"\nP{preset_a} "
            f"↔ P{preset_b} "
            f"| existing="
            f"{len(existing)}"
        )

        marker = PairMarker(
            preset_a,
            preset_b,
            image_a,
            image_b,
            existing,
            args.scale,
        )

        action, points = (
            marker.run(
                args.min_points
            )
        )

        data.setdefault(
            "pairs",
            {},
        )

        data[
            "frame_width"
        ] = width

        data[
            "frame_height"
        ] = height

        data[
            "updated_at"
        ] = (
            time.time()
        )

        data[
            "pairs"
        ][key] = {

            "preset_a": (
                preset_a
            ),

            "preset_b": (
                preset_b
            ),

            "matches": (
                points
            ),
        }

        save_marks(
            data
        )

        print(
            f"💾 Saved "
            f"{MARKS_FILE}"
        )

        if (
            action
            == "quit"
        ):

            print(
                "🛑 Marking paused"
            )

            print(
                "รัน mark ใหม่ "
                "เพื่อทำต่อได้"
            )

            return

    print(
        "\n"
        + "=" * 76
    )

    print(
        "✅ All pairs marked"
    )

    print(
        f"Marks: "
        f"{MARKS_FILE}"
    )

    print(
        "=" * 76
    )


# ============================================================
# Observation loader
# ============================================================

def load_observations(
    min_points,
):

    manifest = (
        load_manifest()
    )

    marks = (
        load_marks()
    )

    width = int(
        manifest[
            "frame_width"
        ]
    )

    refs = []

    observations = []

    for (
        preset_a,
        preset_b,
    ) in OVERLAP_PAIRS:

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

            raise SystemExit(
                "❌ Missing marks "
                f"P{preset_a}"
                " ↔ "
                f"P{preset_b}"
            )

        matches = (
            pair.get(
                "matches",
                [],
            )
        )

        if (
            len(matches)
            < min_points
        ):

            raise SystemExit(
                f"❌ P{preset_a}"
                f" ↔ P{preset_b} "
                f"มีเพียง "
                f"{len(matches)} points "
                f"(ต้อง >= "
                f"{min_points})"
            )

        for index, match in enumerate(
            matches,
            start=1,
        ):

            ref_id = (
                f"p{preset_a}_"
                f"p{preset_b}_"
                f"{index:02d}"
            )

            refs.append(
                ref_id
            )

            observations.append(
                {

                    "ref_id": (
                        ref_id
                    ),

                    "preset": (
                        preset_a
                    ),

                    "x_px": float(
                        match[
                            "x_a_px"
                        ]
                    ),
                }
            )

            observations.append(
                {

                    "ref_id": (
                        ref_id
                    ),

                    "preset": (
                        preset_b
                    ),

                    "x_px": float(
                        match[
                            "x_b_px"
                        ]
                    ),
                }
            )

    return (
        width,
        refs,
        observations,
    )


# ============================================================
# Geometry
# ============================================================

def focal_length_px(
    width,
    hfov_deg,
):

    return (
        width
        /
        (
            2.0
            *
            math.tan(
                math.radians(
                    hfov_deg
                )
                / 2.0
            )
        )
    )


def pixel_offset_deg(
    x_px,
    width,
    hfov_deg,
    cx_px,
):

    fx = focal_length_px(
        width,
        hfov_deg,
    )

    return math.degrees(
        math.atan2(
            x_px - cx_px,
            fx,
        )
    )


# ============================================================
# Linear geometry solver
# ============================================================

def solve_linear_geometry(
    width,
    refs,
    observations,
    hfov_deg,
    cx_px,
):

    # P1 ถูก fix = 0°
    #
    # unknown centers คือ P2..P9

    presets_unknown = list(
        range(
            2,
            10,
        )
    )

    center_index = {

        preset: index

        for index, preset
        in enumerate(
            presets_unknown
        )
    }

    ref_base = len(
        presets_unknown
    )

    ref_index = {

        ref_id:
        ref_base + index

        for index, ref_id
        in enumerate(
            refs
        )
    }

    rows = []

    rhs = []

    # --------------------------------------------------------
    # Observation equation:
    #
    # ReferenceAngle
    # =
    # PresetCenter
    # +
    # PixelOffset
    #
    # =>
    #
    # PresetCenter
    # -
    # ReferenceAngle
    # =
    # -PixelOffset
    # --------------------------------------------------------

    for obs in observations:

        row = np.zeros(
            ref_base
            + len(refs),
            dtype=np.float64,
        )

        preset = int(
            obs[
                "preset"
            ]
        )

        ref_id = (
            obs[
                "ref_id"
            ]
        )

        if (
            preset
            != 1
        ):

            row[
                center_index[
                    preset
                ]
            ] = 1.0

        row[
            ref_index[
                ref_id
            ]
        ] = -1.0

        offset = pixel_offset_deg(
            obs[
                "x_px"
            ],
            width,
            hfov_deg,
            cx_px,
        )

        rows.append(
            row
        )

        rhs.append(
            -offset
        )

    A = np.vstack(
        rows
    )

    b = np.asarray(
        rhs,
        dtype=np.float64,
    )

    solution, *_ = (
        np.linalg.lstsq(
            A,
            b,
            rcond=None,
        )
    )

    residuals = (
        A
        @ solution
        - b
    )

    centers = {

        1: 0.0,
    }

    for preset in presets_unknown:

        centers[
            preset
        ] = float(
            solution[
                center_index[
                    preset
                ]
            ]
        )

    reference_angles = {}

    for ref_id in refs:

        reference_angles[
            ref_id
        ] = float(
            solution[
                ref_index[
                    ref_id
                ]
            ]
        )

    return (
        centers,
        reference_angles,
        residuals,
    )


# ============================================================
# Objective function
# ============================================================

def objective(
    width,
    refs,
    observations,
    hfov_deg,
    cx_px,
):

    (
        _centers,
        _reference_angles,
        residuals,
    ) = solve_linear_geometry(
        width,
        refs,
        observations,
        hfov_deg,
        cx_px,
    )

    return float(
        math.sqrt(
            float(
                np.mean(
                    residuals
                    ** 2
                )
            )
        )
    )


# ============================================================
# HFOV + CX search
# ============================================================

def coarse_to_fine_search(
    width,
    refs,
    observations,
    hfov_min,
    hfov_max,
    cx_min,
    cx_max,
):

    best = None

    stages = [

        (
            61,
            41,
        ),

        (
            31,
            31,
        ),

        (
            31,
            31,
        ),

        (
            31,
            31,
        ),
    ]

    h_lo = float(
        hfov_min
    )

    h_hi = float(
        hfov_max
    )

    c_lo = float(
        cx_min
    )

    c_hi = float(
        cx_max
    )

    for stage_index, (
        h_count,
        c_count,
    ) in enumerate(
        stages,
        start=1,
    ):

        h_values = np.linspace(
            h_lo,
            h_hi,
            h_count,
        )

        c_values = np.linspace(
            c_lo,
            c_hi,
            c_count,
        )

        for hfov in h_values:

            for cx in c_values:

                score = objective(
                    width,
                    refs,
                    observations,
                    float(
                        hfov
                    ),
                    float(
                        cx
                    ),
                )

                if (
                    best is None
                    or
                    score
                    <
                    best["rms"]
                ):

                    best = {

                        "hfov": float(
                            hfov
                        ),

                        "cx": float(
                            cx
                        ),

                        "rms": (
                            score
                        ),
                    }

        h_step = float(
            h_values[1]
            -
            h_values[0]
        )

        c_step = float(
            c_values[1]
            -
            c_values[0]
        )

        print(
            f"Search "
            f"{stage_index}/"
            f"{len(stages)} "
            f"| HFOV="
            f"{best['hfov']:.6f}° "
            f"| cx="
            f"{best['cx']:.3f}px "
            f"| RMS="
            f"{best['rms']:.6f}°"
        )

        h_lo = max(
            hfov_min,
            best["hfov"]
            -
            2.5
            * h_step,
        )

        h_hi = min(
            hfov_max,
            best["hfov"]
            +
            2.5
            * h_step,
        )

        c_lo = max(
            cx_min,
            best["cx"]
            -
            2.5
            * c_step,
        )

        c_hi = min(
            cx_max,
            best["cx"]
            +
            2.5
            * c_step,
        )

    return best


# ============================================================
# Normalize relative pan
# ============================================================

def normalize_relative_pan(
    angle_deg,
):

    value = (
        angle_deg
        + 180.0
    ) % 360.0 - 180.0

    return value


# ============================================================
# Fit quality
# ============================================================

def classify_fit(
    rms_deg,
    max_abs_deg,
):

    if (
        rms_deg <= 0.5
        and
        max_abs_deg <= 1.0
    ):

        return "excellent"

    if (
        rms_deg <= 1.0
        and
        max_abs_deg <= 2.0
    ):

        return "good"

    if (
        rms_deg <= 2.0
        and
        max_abs_deg <= 4.0
    ):

        return (
            "needs_validation"
        )

    return (
        "redo_recommended"
    )


# ============================================================
# FIT command
# ============================================================

def command_fit(
    args,
):

    ensure_dirs()

    (
        width,
        refs,
        observations,
    ) = load_observations(
        args.min_points
    )

    hfov_min = float(
        args.hfov_min
    )

    hfov_max = float(
        args.hfov_max
    )

    cx_min = (
        float(
            args.cx_min_frac
        )
        * width
    )

    cx_max = (
        float(
            args.cx_max_frac
        )
        * width
    )

    if not (
        1.0
        < hfov_min
        < hfov_max
        < 179.0
    ):

        raise SystemExit(
            "❌ Invalid HFOV range"
        )

    if not (
        0.0
        <= cx_min
        < cx_max
        <= width
    ):

        raise SystemExit(
            "❌ Invalid CX range"
        )

    print(
        "=" * 76
    )

    print(
        "Bearing Geometry Calibration v2 "
        "- FIT"
    )

    print(
        "=" * 76
    )

    print(
        f"Width        : "
        f"{width}px"
    )

    print(
        f"References   : "
        f"{len(refs)}"
    )

    print(
        f"Observations : "
        f"{len(observations)}"
    )

    print(
        f"HFOV search  : "
        f"{hfov_min:.2f} "
        f".. "
        f"{hfov_max:.2f}°"
    )

    print(
        f"CX search    : "
        f"{cx_min:.1f} "
        f".. "
        f"{cx_max:.1f}px"
    )

    print()

    print(
        "P1 = Relative 0° anchor"
    )

    print(
        "True North ยังไม่ถูกคำนวณ"
    )

    print(
        "=" * 76
    )

    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    best = (
        coarse_to_fine_search(
            width,
            refs,
            observations,
            hfov_min,
            hfov_max,
            cx_min,
            cx_max,
        )
    )

    # --------------------------------------------------------
    # Final fit
    # --------------------------------------------------------

    (
        centers,
        reference_angles,
        residuals,
    ) = solve_linear_geometry(
        width,
        refs,
        observations,
        best[
            "hfov"
        ],
        best[
            "cx"
        ],
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

    max_abs = float(
        np.max(
            np.abs(
                residuals
            )
        )
    )

    quality = (
        classify_fit(
            rms,
            max_abs,
        )
    )

    nominal = {

        int(key): float(
            value
        )

        for key, value
        in PRESET_PAN_DEG.items()
    }

    centers_normalized = {

        preset:
        normalize_relative_pan(
            centers[
                preset
            ]
        )

        for preset
        in centers
    }

    corrections = {

        preset:
        (
            centers_normalized[
                preset
            ]
            -
            nominal[
                preset
            ]
        )

        for preset
        in centers_normalized
    }

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    print(
        "\n"
        + "-" * 76
    )

    print(
        "FIT RESULT"
    )

    print(
        "-" * 76
    )

    print(
        "Effective HFOV : "
        f"{best['hfov']:.6f}°"
    )

    print(
        "Config HFOV    : "
        f"{float(HFOV_DEG):.6f}°"
    )

    print(
        "Principal X    : "
        f"{best['cx']:.3f}px"
    )

    print(
        "Image center   : "
        f"{width / 2.0:.3f}px"
    )

    print(
        "RMS error      : "
        f"{rms:.6f}°"
    )

    print(
        "Max error      : "
        f"{max_abs:.6f}°"
    )

    print(
        "Quality        : "
        f"{quality}"
    )

    print()

    print(
        "Preset | Nominal | Fitted | Correction"
    )

    for preset in range(
        1,
        10,
    ):

        print(
            f"P{preset:<2d}    "
            f"{nominal[preset]:>+9.3f}°  "
            f"{centers_normalized[preset]:>+9.3f}°  "
            f"{corrections[preset]:>+9.3f}°"
        )

    # --------------------------------------------------------
    # Large correction warning
    # --------------------------------------------------------

    largest_correction = max(

        abs(value)

        for value
        in corrections.values()
    )

    if (
        largest_correction
        >
        args.max_preset_correction
    ):

        print()

        print(
            "⚠️ Large preset correction detected"
        )

        print(
            "ตรวจการคลิก Matching Point "
            "หรือ Parallax"
        )

    # --------------------------------------------------------
    # Observation report
    # --------------------------------------------------------

    observation_report = []

    for obs, residual in zip(
        observations,
        residuals,
    ):

        preset = int(
            obs[
                "preset"
            ]
        )

        ref_id = (
            obs[
                "ref_id"
            ]
        )

        predicted = (

            centers[
                preset
            ]

            +

            pixel_offset_deg(
                obs[
                    "x_px"
                ],
                width,
                best[
                    "hfov"
                ],
                best[
                    "cx"
                ],
            )
        )

        observation_report.append(
            {

                "ref_id": (
                    ref_id
                ),

                "preset": (
                    preset
                ),

                "x_px": round(
                    float(
                        obs[
                            "x_px"
                        ]
                    ),
                    3,
                ),

                "predicted_relative_angle_deg": round(
                    float(
                        predicted
                    ),
                    6,
                ),

                "fitted_reference_angle_deg": round(
                    float(
                        reference_angles[
                            ref_id
                        ]
                    ),
                    6,
                ),

                "residual_deg": round(
                    float(
                        residual
                    ),
                    6,
                ),
            }
        )

    # --------------------------------------------------------
    # Save result
    # --------------------------------------------------------

    output = {

        "version": 2,

        "created_at": (
            time.time()
        ),

        "status": (
            "relative_geometry_only"
        ),

        "frame_width": (
            int(
                width
            )
        ),

        "effective_hfov_deg": (
            float(
                best[
                    "hfov"
                ]
            )
        ),

        "principal_x_px": (
            float(
                best[
                    "cx"
                ]
            )
        ),

        "anchor": {

            "preset": 1,

            "relative_pan_deg": (
                0.0
            ),
        },

        "preset_relative_pan_deg": {

            str(preset): round(
                float(
                    centers_normalized[
                        preset
                    ]
                ),
                8,
            )

            for preset
            in range(
                1,
                10,
            )
        },

        "preset_nominal_pan_deg": {

            str(preset): float(
                nominal[
                    preset
                ]
            )

            for preset
            in range(
                1,
                10,
            )
        },

        "preset_correction_deg": {

            str(preset): round(
                float(
                    corrections[
                        preset
                    ]
                ),
                8,
            )

            for preset
            in range(
                1,
                10,
            )
        },

        "fit": {

            "references": (
                len(
                    refs
                )
            ),

            "observations": (
                len(
                    observations
                )
            ),

            "rms_consistency_deg": (
                rms
            ),

            "max_abs_residual_deg": (
                max_abs
            ),

            "quality": (
                quality
            ),
        },

        "absolute_north_calibrated": (
            False
        ),

        "notes": [

            (
                "Relative geometry only."
            ),

            (
                "Preset 1 is relative pan 0 degrees."
            ),

            (
                "True North calibration is still required."
            ),

            (
                "Do not enable production GPS "
                "solely from this file."
            ),
        ],

        "observations": (
            observation_report
        ),
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
        + "=" * 76
    )

    print(
        f"✅ Saved "
        f"{OUTPUT_FILE}"
    )

    print(
        "=" * 76
    )

    if quality in {
        "needs_validation",
        "redo_recommended",
    }:

        print(
            "⚠️ ยังไม่ควรเอาค่านี้ "
            "เข้า Production"
        )

        print(
            "ให้ตรวจ Matching Point "
            "และ Calibration ใหม่"
        )

    else:

        print(
            "✅ Relative Geometry "
            "ผ่านระดับเบื้องต้น"
        )

        print(
            "ขั้นต่อไปคือ "
            "Overlap Validation"
        )


# ============================================================
# CLI
# ============================================================

def build_parser():

    parser = (
        argparse.ArgumentParser(
            description=(
                "Smart Fire Detection v2 "
                "Bearing Geometry Calibration"
            )
        )
    )

    sub = (
        parser.add_subparsers(
            dest="command",
            required=True,
        )
    )

    # --------------------------------------------------------
    # capture
    # --------------------------------------------------------

    capture_parser = (
        sub.add_parser(
            "capture",
            help=(
                "Capture stable images "
                "for presets 1..9"
            ),
        )
    )

    capture_parser.set_defaults(
        func=command_capture
    )

    # --------------------------------------------------------
    # mark
    # --------------------------------------------------------

    mark_parser = (
        sub.add_parser(
            "mark",
            help=(
                "Mark matching points "
                "between overlapping presets"
            ),
        )
    )

    mark_parser.add_argument(
        "--scale",
        type=float,
        default=0.65,
        help=(
            "GUI display scale "
            "(default: 0.65)"
        ),
    )

    mark_parser.add_argument(
        "--min-points",
        type=int,
        default=3,
        help=(
            "Minimum matching points "
            "per pair "
            "(default: 3)"
        ),
    )

    mark_parser.set_defaults(
        func=command_mark
    )

    # --------------------------------------------------------
    # fit
    # --------------------------------------------------------

    fit_parser = (
        sub.add_parser(
            "fit",
            help=(
                "Fit HFOV, principal X "
                "and relative preset centers"
            ),
        )
    )

    fit_parser.add_argument(
        "--min-points",
        type=int,
        default=3,
    )

    fit_parser.add_argument(
        "--hfov-min",
        type=float,
        default=35.0,
    )

    fit_parser.add_argument(
        "--hfov-max",
        type=float,
        default=90.0,
    )

    fit_parser.add_argument(
        "--cx-min-frac",
        type=float,
        default=0.45,
    )

    fit_parser.add_argument(
        "--cx-max-frac",
        type=float,
        default=0.55,
    )

    fit_parser.add_argument(
        "--max-preset-correction",
        type=float,
        default=10.0,
    )

    fit_parser.set_defaults(
        func=command_fit
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

    if (
        getattr(
            args,
            "scale",
            1.0,
        )
        <= 0
    ):

        raise SystemExit(
            "❌ --scale must be > 0"
        )

    if (
        getattr(
            args,
            "min_points",
            3,
        )
        < 2
    ):

        raise SystemExit(
            "❌ --min-points "
            "must be >= 2"
        )

    args.func(
        args
    )


if __name__ == "__main__":
    main()
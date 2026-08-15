#!/usr/bin/env python3

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import cv2
import psutil

from camera import LatestFrameCamera, wait_until_stable

from config import (
    SWEEP_SEQUENCE,
    PRESET_BEARING_DEG,
    INITIAL_PRESET_WAIT_SEC,
    STABLE_DIFF_THRESHOLD,
    STABLE_REQUIRED_PAIRS,
    STABLE_TIMEOUT_SEC,
    POST_MOVE_FRESH_FRAMES,
    FRAMES_PER_SCAN,
    MIN_CONFIRM_FRAMES,
    FRAME_SAMPLE_GAP_SEC,
    ALERT_COOLDOWN_SEC,
    STATIC_DIR,
    DASHBOARD_WRITE_INTERVAL_SEC,
    SITE_CALIBRATION_FILE,
)

from detection import (
    FireDetector,
    consensus,
    bbox_iou,
)

from notify import (
    TelegramWorker,
    format_alert,
)

from overlay import (
    draw_detection,
    draw_status,
)

from ptz import PTZController


# ============================================================
# Runtime configuration
# ============================================================

LATEST_FRAME = (
    STATIC_DIR
    / "latest_frame.jpg"
)

LATEST_ALERT = (
    STATIC_DIR
    / "latest_alert.jpg"
)

STATUS_JSON = (
    STATIC_DIR
    / "status.json"
)


# ------------------------------------------------------------
# Startup AI warm-up
# ------------------------------------------------------------
#
# Warm-up เฉพาะครั้งเดียวตอนเปิดโปรแกรม
# ไม่ Warm-up ทุก Preset
#

STARTUP_WARMUP_RUNS = max(
    0,
    int(
        os.getenv(
            "STARTUP_WARMUP_RUNS",
            "3",
        )
    ),
)


# ------------------------------------------------------------
# Valid GPS quality
# ------------------------------------------------------------

VALID_GPS_QUALITIES = {
    "calibrated",
    "calibrated-low",
}


# ------------------------------------------------------------
# Alert Event Deduplication
# ------------------------------------------------------------
#
# เหตุการณ์จะถือว่า "ซ้ำ" เมื่อ:
#
# - Class เดียวกัน
# - Preset เดียวกัน
# - Bounding Box IoU >= threshold
# - ยังอยู่ภายใน ALERT_COOLDOWN_SEC
#
# คนละ Preset จะถือเป็นคนละ Event
#

ALERT_DEDUP_IOU_THRESHOLD = float(
    os.getenv(
        "ALERT_DEDUP_IOU_THRESHOLD",
        "0.50",
    )
)


# ------------------------------------------------------------
# Alert spool directory
# ------------------------------------------------------------
#
# Telegram worker เป็น asynchronous
#
# จึงไม่ควรส่ง latest_alert.jpg โดยตรงเข้า Queue
# เพราะ Alert ใหม่อาจ overwrite รูปเดิม
# ก่อน Telegram worker เปิดอ่านไฟล์
#

ALERT_SPOOL_DIR = (
    STATIC_DIR
    / "alert_spool"
)

ALERT_SPOOL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# Atomic output helpers
# ============================================================

def atomic_imwrite(
    path: Path,
    frame,
) -> bool:
    """
    Write image into a temporary file,
    then atomically replace the target.

    ลดโอกาส Dashboard อ่าน JPEG
    ขณะไฟล์กำลังถูกเขียน
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_name(
        path.stem
        + ".tmp"
        + path.suffix
    )

    try:

        ok = cv2.imwrite(
            str(tmp),
            frame,
        )

        if not ok:

            print(
                f"⚠️ Cannot write image: "
                f"{tmp}"
            )

            return False

        os.replace(
            tmp,
            path,
        )

        return True

    except Exception as exc:

        print(
            f"⚠️ Image write error "
            f"{path}: {exc}"
        )

        try:

            if tmp.exists():
                tmp.unlink()

        except OSError:
            pass

        return False


def write_status(
    data,
) -> bool:
    """
    Atomically write static/status.json.
    """

    STATUS_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = (
        STATUS_JSON
        .with_suffix(".tmp")
    )

    try:

        tmp.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(
            tmp,
            STATUS_JSON,
        )

        return True

    except Exception as exc:

        print(
            "⚠️ status.json "
            f"write error: {exc}"
        )

        try:

            if tmp.exists():
                tmp.unlink()

        except OSError:
            pass

        return False


# ============================================================
# Camera helpers
# ============================================================

def wait_fresh_frames(
    camera,
    after_seq,
    count,
):
    """
    Wait for a number of frames newer than after_seq.

    Returns:
        newest packet or None
    """

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
# AI Startup Warm-up
# ============================================================

def warm_up_detector(
    camera,
    detector,
    runs,
):
    """
    Warm up AI backend ONCE at program startup.

    Warm-up results:
    - ไม่เข้า consensus
    - ไม่สร้าง Alert
    - ไม่บันทึกเป็น Detection Event
    """

    if runs <= 0:

        print(
            "\nℹ️ AI startup "
            "warm-up disabled"
        )

        return []

    packet = (
        camera.latest(
            copy=True,
        )
    )

    if packet is None:

        raise RuntimeError(
            "No frame available "
            "for AI startup warm-up"
        )

    warmup_preset = (
        SWEEP_SEQUENCE[0]
    )

    timings_ms = []

    print(
        f"\n🔥 AI startup warm-up "
        f"({runs} runs)..."
    )

    for i in range(runs):

        t0 = (
            time.perf_counter()
        )

        detector.detect(
            packet.frame,
            warmup_preset,
        )

        infer_ms = (
            time.perf_counter()
            - t0
        ) * 1000.0

        timings_ms.append(
            infer_ms
        )

        print(
            f"  Warm-up "
            f"{i + 1}/{runs} "
            f"| inference="
            f"{infer_ms:.1f} ms"
        )

    print(
        "✅ AI startup "
        "warm-up completed"
    )

    print(
        f"   first = "
        f"{timings_ms[0]:.1f} ms"
    )

    print(
        f"   last  = "
        f"{timings_ms[-1]:.1f} ms"
    )

    return timings_ms


# ============================================================
# Detection helpers
# ============================================================

def print_detection(
    prefix,
    detection,
):
    """
    Print Detection to console.
    """

    if (
        detection.distance_m
        is None
    ):

        distance_text = "N/A"

    else:

        distance_text = (
            f"{detection.distance_m:.2f} m"
        )

    if detection.gps is None:

        gps_text = "None"

    else:

        gps_text = (
            f"{detection.gps[0]:.8f},"
            f"{detection.gps[1]:.8f}"
        )

    print(
        f"{prefix}"
        f"{detection.canonical_class} "
        f"conf="
        f"{detection.confidence:.3f} "
        f"bearing="
        f"{detection.bearing_deg:.2f}° "
        f"distance="
        f"{distance_text} "
        f"quality="
        f"{detection.distance_quality} "
        f"gps="
        f"{gps_text}"
    )


# ============================================================
# Location safety
# ============================================================

def sanitize_detection_location(
    detection,
    *,
    site_bearing_calibrated,
):
    """
    Final production safety barrier.

    GPS จะใช้งานได้เมื่อ:

    1. Site bearing calibration มีอยู่
    2. Distance มีค่า
    3. Distance quality อยู่ใน calibrated range
    """

    location_valid = (
        site_bearing_calibrated
        and detection.distance_m
        is not None
        and detection.distance_quality
        in VALID_GPS_QUALITIES
    )

    if (
        detection.gps is not None
        and not location_valid
    ):

        print(
            "⚠️ GPS suppressed by "
            "production safety guard "
            f"| quality="
            f"{detection.distance_quality}"
        )

        return replace(
            detection,
            gps=None,
        )

    return detection


def detection_to_dict(
    detection,
    *,
    site_bearing_calibrated,
):
    """
    Convert Detection into JSON-safe object.
    """

    gps = None

    if detection.gps is not None:

        gps = [
            round(
                float(
                    detection.gps[0]
                ),
                8,
            ),
            round(
                float(
                    detection.gps[1]
                ),
                8,
            ),
        ]

    return {

        "class": (
            detection
            .canonical_class
        ),

        "model_class": (
            detection
            .model_class
        ),

        "confidence": round(
            float(
                detection.confidence
            ),
            6,
        ),

        "bbox": list(
            detection.bbox
        ),

        "bearing_deg": round(
            float(
                detection.bearing_deg
            ),
            6,
        ),

        "bearing_calibrated": (
            site_bearing_calibrated
        ),

        "distance_m": (
            None
            if detection.distance_m
            is None
            else round(
                float(
                    detection.distance_m
                ),
                6,
            )
        ),

        "distance_quality": (
            detection
            .distance_quality
        ),

        "gps": gps,
    }


# ============================================================
# Alert Event Deduplication
# ============================================================

class AlertDeduplicator:
    """
    Event-based alert cooldown.

    Same event:
    - same canonical class
    - same preset
    - bounding boxes overlap >= IoU threshold

    Different preset:
    - different event

    Different object inside same preset:
    - different event if IoU is low
    """

    def __init__(
        self,
        cooldown_sec,
        iou_threshold=0.50,
    ):

        self.cooldown_sec = max(
            0.0,
            float(
                cooldown_sec
            ),
        )

        self.iou_threshold = float(
            iou_threshold
        )

        if not (
            0.0
            <= self.iou_threshold
            <= 1.0
        ):

            raise ValueError(
                "ALERT_DEDUP_IOU_THRESHOLD "
                "must be between 0 and 1"
            )

        self.events = []


    def _purge(
        self,
        now_mono,
    ):
        """
        Remove expired cooldown events.
        """

        self.events = [

            event

            for event
            in self.events

            if (
                now_mono
                - event["alerted_at"]
                < self.cooldown_sec
            )
        ]


    def should_alert(
        self,
        detection,
        preset,
        now_mono,
    ):
        """
        Returns:

            (True, "new_event")

        or

            (
                False,
                "duplicate IoU=... remaining=...s"
            )
        """

        self._purge(
            now_mono
        )

        for event in self.events:

            # -----------------------------
            # Different class
            # -----------------------------

            if (
                event["class"]
                != detection.canonical_class
            ):
                continue


            # -----------------------------
            # Different preset
            #
            # จะไม่ถูก cooldown ข้ามกัน
            # -----------------------------

            if (
                event["preset"]
                != preset
            ):
                continue


            # -----------------------------
            # Spatial comparison
            # -----------------------------

            iou = bbox_iou(
                event["bbox"],
                detection.bbox,
            )

            if (
                iou
                >= self.iou_threshold
            ):

                # Update bbox to latest
                # เพื่อรองรับวัตถุขยับเล็กน้อย
                # แต่ไม่ต่อเวลา cooldown
                event["bbox"] = tuple(
                    detection.bbox
                )

                event["last_seen"] = (
                    now_mono
                )

                remaining = max(
                    0.0,
                    self.cooldown_sec
                    - (
                        now_mono
                        - event[
                            "alerted_at"
                        ]
                    ),
                )

                return (
                    False,
                    (
                        "duplicate "
                        f"IoU={iou:.3f} "
                        f"remaining="
                        f"{remaining:.1f}s"
                    ),
                )

        return (
            True,
            "new_event",
        )


    def record_alert(
        self,
        detection,
        preset,
        now_mono,
    ):
        """
        Register a newly alerted event.
        """

        self.events.append(
            {
                "class": (
                    detection
                    .canonical_class
                ),

                "preset": preset,

                "bbox": tuple(
                    detection.bbox
                ),

                "alerted_at": (
                    now_mono
                ),

                "last_seen": (
                    now_mono
                ),
            }
        )


# ============================================================
# Telegram alert spool
# ============================================================

def create_alert_spool(
    frame,
    preset,
    detection,
):
    """
    Create unique image file for Telegram queue.

    Prevents this race condition:

        Alert A -> latest_alert.jpg
                 ↓
        Alert B overwrites file
                 ↓
        Telegram A accidentally
        sends Alert B image
    """

    timestamp = (
        time.strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    unique = (
        time.time_ns()
    )

    class_name = (
        detection
        .canonical_class
        .replace("/", "_")
        .replace("\\", "_")
    )

    path = (
        ALERT_SPOOL_DIR
        / (
            f"alert_"
            f"{timestamp}_"
            f"{unique}_"
            f"p{preset}_"
            f"{class_name}.jpg"
        )
    )

    if not atomic_imwrite(
        path,
        frame,
    ):

        return None

    return path


# ============================================================
# Preset scanning
# ============================================================

def scan_preset(
    camera,
    ptz,
    detector,
    preset,
    *,
    first_move=False,
    site_bearing_calibrated=False,
):
    """
    Production scan flow:

        PTZ
          ↓
        calculated wait
          ↓
        fresh frames
          ↓
        stable frame
          ↓
        AI frame 1
          ↓
        AI frame 2
          ↓
        AI frame 3
          ↓
        IoU consensus
          ↓
        location safety
    """

    scan_start = (
        time.perf_counter()
    )

    info = {

        "status": "starting",

        "preset": preset,

        "ptz_ok": False,

        "frames_processed": 0,

        "inference_ms": [],

        "stable_seq": None,

        "scan_ms": None,
    }


    print(
        "\n"
        + "-" * 76
    )

    print(
        f"🔄 Move -> preset "
        f"{preset} "
        f"| center="
        f"{PRESET_BEARING_DEG[preset]:.1f}°"
    )


    # ========================================================
    # PTZ
    # ========================================================

    ok, wait_sec = (
        ptz.goto_preset(
            preset
        )
    )

    if not ok:

        print(
            "❌ PTZ command failed"
        )

        info["status"] = (
            "ptz_failed"
        )

        info["scan_ms"] = (
            time.perf_counter()
            - scan_start
        ) * 1000.0

        return (
            [],
            None,
            info,
        )


    info["ptz_ok"] = True


    # --------------------------------------------------------
    # First movement
    # --------------------------------------------------------

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


    # ========================================================
    # Fresh frames
    # ========================================================

    arrival_seq = (
        camera.sequence
    )

    fresh = wait_fresh_frames(
        camera,
        arrival_seq,
        POST_MOVE_FRESH_FRAMES,
    )

    if fresh is None:

        print(
            "⚠️ No fresh "
            "post-move frame"
        )

        info["status"] = (
            "fresh_frame_timeout"
        )

        info["scan_ms"] = (
            time.perf_counter()
            - scan_start
        ) * 1000.0

        return (
            [],
            None,
            info,
        )


    # ========================================================
    # Stable frame
    # ========================================================

    stable = wait_until_stable(
        camera,
        fresh.seq,
        STABLE_DIFF_THRESHOLD,
        STABLE_REQUIRED_PAIRS,
        STABLE_TIMEOUT_SEC,
    )

    if stable is None:

        print(
            "⚠️ Image not stable; "
            "skip preset"
        )

        info["status"] = (
            "stability_timeout"
        )

        info["scan_ms"] = (
            time.perf_counter()
            - scan_start
        ) * 1000.0

        return (
            [],
            None,
            info,
        )


    info["stable_seq"] = (
        stable.seq
    )

    print(
        f"✅ Stable frame "
        f"| seq={stable.seq} "
        f"| age="
        f"{time.time() - stable.timestamp:.3f}s"
    )


    # ========================================================
    # AI scan
    # ========================================================

    detection_sets = []

    packet = stable

    last_packet = stable


    for i in range(
        FRAMES_PER_SCAN
    ):


        # ----------------------------------------------------
        # Frame 2+
        # ----------------------------------------------------

        if i > 0:

            time.sleep(
                FRAME_SAMPLE_GAP_SEC
            )

            packet = (
                camera.wait_for_newer(
                    last_packet.seq,
                    timeout=2.0,
                )
            )

            if packet is None:

                print(
                    f"⚠️ Frame "
                    f"{i + 1}/"
                    f"{FRAMES_PER_SCAN} "
                    "timeout"
                )

                break


        last_packet = packet


        # ----------------------------------------------------
        # AI inference
        # ----------------------------------------------------

        t0 = (
            time.perf_counter()
        )

        detections = (
            detector.detect(
                packet.frame,
                preset,
            )
        )

        infer_ms = (
            time.perf_counter()
            - t0
        ) * 1000.0


        detection_sets.append(
            detections
        )

        info[
            "inference_ms"
        ].append(
            round(
                infer_ms,
                3,
            )
        )


        print(
            f"Frame "
            f"{i + 1}/"
            f"{FRAMES_PER_SCAN} "
            f"| seq={packet.seq} "
            f"| infer="
            f"{infer_ms:.1f} ms "
            f"| detections="
            f"{len(detections)}"
        )


        for detection in detections:

            print_detection(
                "  - ",
                detection,
            )


    info[
        "frames_processed"
    ] = len(
        detection_sets
    )


    # ========================================================
    # Consensus
    # ========================================================

    if (
        len(detection_sets)
        < MIN_CONFIRM_FRAMES
    ):

        confirmed = []

        print(
            "⚠️ Not enough frames "
            "for consensus "
            f"({len(detection_sets)}/"
            f"{MIN_CONFIRM_FRAMES})"
        )

    else:

        confirmed = consensus(
            detection_sets,
            MIN_CONFIRM_FRAMES,
        )


    # ========================================================
    # GPS safety
    # ========================================================

    confirmed = [

        sanitize_detection_location(
            detection,
            site_bearing_calibrated=(
                site_bearing_calibrated
            ),
        )

        for detection
        in confirmed
    ]


    # ========================================================
    # Console result
    # ========================================================

    if confirmed:

        print(
            f"🔥 CONFIRMED: "
            f"{len(confirmed)} "
            "detection(s)"
        )

        for detection in confirmed:

            print_detection(
                "  * ",
                detection,
            )

    else:

        print(
            "✅ No confirmed "
            "Fire/Smoke"
        )


    # ========================================================
    # Scan status
    # ========================================================

    if (
        len(detection_sets)
        == FRAMES_PER_SCAN
    ):

        info["status"] = "ok"

    else:

        info["status"] = (
            "partial_frames"
        )


    info["scan_ms"] = (
        time.perf_counter()
        - scan_start
    ) * 1000.0


    return (
        confirmed,
        last_packet,
        info,
    )


# ============================================================
# Status helpers
# ============================================================

def build_status(
    *,
    timestamp,
    cycle,
    step,
    preset,
    confirmed,
    scan_info,
    site_bearing_calibrated,
):
    """
    Build Dashboard status.json.
    """

    return {

        "timestamp": (
            timestamp
        ),

        "runtime_status": (
            scan_info[
                "status"
            ]
        ),

        "cycle": (
            cycle
        ),

        "step": (
            step
        ),

        "preset": (
            preset
        ),

        "center_bearing_deg": (
            PRESET_BEARING_DEG[
                preset
            ]
        ),

        "site_bearing_calibrated": (
            site_bearing_calibrated
        ),

        "frames_processed": (
            scan_info[
                "frames_processed"
            ]
        ),

        "inference_ms": (
            scan_info[
                "inference_ms"
            ]
        ),

        "scan_ms": (
            None
            if scan_info[
                "scan_ms"
            ]
            is None
            else round(
                scan_info[
                    "scan_ms"
                ],
                3,
            )
        ),

        "detections": len(
            confirmed
        ),

        "confirmed": [

            detection_to_dict(
                detection,
                site_bearing_calibrated=(
                    site_bearing_calibrated
                ),
            )

            for detection
            in confirmed
        ],

        "cpu_percent": (
            psutil.cpu_percent(
                interval=None
            )
        ),

        "ram_percent": (
            psutil
            .virtual_memory()
            .percent
        ),
    }


# ============================================================
# Main
# ============================================================

def main():

    # ========================================================
    # Header
    # ========================================================

    print(
        "=" * 76
    )

    print(
        "🔥 Smart Fire Detection v2 "
        "- Production Runtime"
    )

    print(
        f"Sweep sequence : "
        f"{SWEEP_SEQUENCE}"
    )

    print(
        f"Frames/scan    : "
        f"{FRAMES_PER_SCAN}"
    )

    print(
        f"Confirm        : "
        f"{MIN_CONFIRM_FRAMES}/"
        f"{FRAMES_PER_SCAN}"
    )

    print(
        f"Startup warm-up: "
        f"{STARTUP_WARMUP_RUNS}"
    )

    print(
        f"Alert cooldown : "
        f"{ALERT_COOLDOWN_SEC:.1f}s"
    )

    print(
        f"Alert dedup IoU: "
        f"{ALERT_DEDUP_IOU_THRESHOLD:.2f}"
    )

    print(
        "=" * 76
    )


    # ========================================================
    # Calibration state
    # ========================================================

    site_bearing_calibrated = (
        SITE_CALIBRATION_FILE
        .exists()
    )

    if site_bearing_calibrated:

        print(
            "✅ Site bearing "
            "calibration found"
        )

    else:

        print(
            "⚠️ Site bearing "
            "calibration not found"
        )

        print(
            "   Bearing ยังเป็น "
            "software-calculated bearing"
        )

        print(
            "   Production GPS output "
            "will be suppressed"
        )


    # ========================================================
    # Camera
    # ========================================================

    print(
        "\n📡 กำลังเปิด RTSP..."
    )

    camera = (
        LatestFrameCamera()
        .start()
    )


    try:

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
                    "เปิด RTSP "
                    "ไม่สำเร็จภายใน "
                    "10 วินาที"
                )

            time.sleep(
                0.1
            )


        print(
            "✅ RTSP พร้อม"
        )


        # ====================================================
        # AI
        # ====================================================

        print(
            "\n🧠 กำลังโหลด AI..."
        )

        detector = (
            FireDetector()
        )

        print(
            "✅ AI พร้อม"
        )


        # ====================================================
        # Startup warm-up
        # ====================================================

        warm_up_detector(
            camera,
            detector,
            STARTUP_WARMUP_RUNS,
        )


        # ====================================================
        # PTZ
        # ====================================================

        ptz = (
            PTZController()
        )


        # ====================================================
        # Telegram
        # ====================================================

        notifier = (
            TelegramWorker()
        )


        # ====================================================
        # Alert Event Deduplicator
        # ====================================================

        alert_dedup = (
            AlertDeduplicator(
                cooldown_sec=(
                    ALERT_COOLDOWN_SEC
                ),
                iou_threshold=(
                    ALERT_DEDUP_IOU_THRESHOLD
                ),
            )
        )

        print(
            "\n🔔 Alert system ready"
        )

        print(
            "   Cooldown    : "
            f"{ALERT_COOLDOWN_SEC:.1f}s"
        )

        print(
            "   Dedup IoU   : "
            f"{ALERT_DEDUP_IOU_THRESHOLD:.2f}"
        )

        print(
            "   Dedup scope : "
            "class + preset + bbox"
        )


        # ====================================================
        # Dashboard timer
        # ====================================================

        last_dashboard_mono = (
            -float("inf")
        )


        # ====================================================
        # Runtime sweep
        # ====================================================

        cycle = 0

        first_move = True


        while True:

            cycle += 1


            print(
                "\n"
                + "#" * 76
            )

            print(
                f"CYCLE {cycle}"
            )

            print(
                "#" * 76
            )


            # ------------------------------------------------
            # Sweep sequence
            #
            # Cycle 1:
            #   P1 → ... → P1
            #
            # Cycle 2+:
            #   เริ่ม P2 เพราะรอบก่อนเพิ่งจบ P1
            # ------------------------------------------------

            if cycle == 1:

                sequence = (
                    SWEEP_SEQUENCE
                )

                step_offset = 0

            else:

                sequence = (
                    SWEEP_SEQUENCE[1:]
                )

                step_offset = 1


            # =================================================
            # Preset loop
            # =================================================

            for (
                local_index,
                preset,
            ) in enumerate(
                sequence,
                start=1,
            ):


                logical_step = (
                    local_index
                    + step_offset
                )


                # =============================================
                # Scan preset
                # =============================================

                try:

                    (
                        confirmed,
                        packet,
                        scan_info,
                    ) = scan_preset(
                        camera,
                        ptz,
                        detector,
                        preset,
                        first_move=(
                            first_move
                        ),
                        site_bearing_calibrated=(
                            site_bearing_calibrated
                        ),
                    )


                except Exception as exc:

                    print(
                        "❌ Preset scan "
                        "exception "
                        f"| preset="
                        f"{preset} "
                        f"| "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    now = (
                        time.time()
                    )

                    write_status(
                        {

                            "timestamp": (
                                now
                            ),

                            "runtime_status": (
                                "scan_exception"
                            ),

                            "cycle": (
                                cycle
                            ),

                            "step": (
                                logical_step
                            ),

                            "preset": (
                                preset
                            ),

                            "error": (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),

                            "cpu_percent": (
                                psutil
                                .cpu_percent(
                                    interval=None
                                )
                            ),

                            "ram_percent": (
                                psutil
                                .virtual_memory()
                                .percent
                            ),
                        }
                    )

                    continue


                # =============================================
                # First movement complete
                # =============================================

                if (
                    first_move
                    and scan_info[
                        "ptz_ok"
                    ]
                ):

                    first_move = False


                now_wall = (
                    time.time()
                )

                now_mono = (
                    time.monotonic()
                )


                # =============================================
                # No usable packet
                # =============================================

                if packet is None:

                    status = (
                        build_status(
                            timestamp=(
                                now_wall
                            ),
                            cycle=(
                                cycle
                            ),
                            step=(
                                logical_step
                            ),
                            preset=(
                                preset
                            ),
                            confirmed=[],
                            scan_info=(
                                scan_info
                            ),
                            site_bearing_calibrated=(
                                site_bearing_calibrated
                            ),
                        )
                    )

                    write_status(
                        status
                    )

                    print(
                        f"⚠️ Skip output "
                        f"| preset="
                        f"{preset} "
                        f"| status="
                        f"{scan_info['status']}"
                    )

                    continue


                # =============================================
                # Draw frame
                # =============================================

                frame = (
                    packet
                    .frame
                    .copy()
                )


                for detection in confirmed:

                    draw_detection(
                        frame,
                        detection,
                    )


                draw_status(
                    frame,
                    preset,
                    PRESET_BEARING_DEG[
                        preset
                    ],
                    (
                        f"SCAN | "
                        f"det="
                        f"{len(confirmed)}"
                    ),
                )


                # =============================================
                # Dashboard latest frame
                # =============================================

                if (
                    now_mono
                    - last_dashboard_mono
                    >=
                    DASHBOARD_WRITE_INTERVAL_SEC
                ):

                    if atomic_imwrite(
                        LATEST_FRAME,
                        frame,
                    ):

                        last_dashboard_mono = (
                            now_mono
                        )


                # =============================================
                # status.json
                # =============================================

                status = (
                    build_status(
                        timestamp=(
                            now_wall
                        ),
                        cycle=(
                            cycle
                        ),
                        step=(
                            logical_step
                        ),
                        preset=(
                            preset
                        ),
                        confirmed=(
                            confirmed
                        ),
                        scan_info=(
                            scan_info
                        ),
                        site_bearing_calibrated=(
                            site_bearing_calibrated
                        ),
                    )
                )

                write_status(
                    status
                )


                # =================================================
                # EVENT-BASED ALERTING
                # =================================================
                #
                # ไม่มี Global cooldown แล้ว
                #
                # แต่ละ Detection ถูกตรวจว่าเป็น:
                #
                # - Event ใหม่
                # - Duplicate Event
                #
                # ด้วย:
                #
                # class
                # + preset
                # + bbox IoU
                # =================================================

                if confirmed:


                    # ---------------------------------------------
                    # Confidence สูงก่อน
                    # ---------------------------------------------

                    ordered_alerts = sorted(
                        confirmed,
                        key=lambda d: (
                            d.confidence
                        ),
                        reverse=True,
                    )


                    for detection in ordered_alerts:


                        # =========================================
                        # Check event cooldown
                        # =========================================

                        (
                            should_alert,
                            reason,
                        ) = (
                            alert_dedup
                            .should_alert(
                                detection,
                                preset,
                                now_mono,
                            )
                        )


                        # =========================================
                        # Duplicate Event
                        # =========================================

                        if not should_alert:

                            print(
                                "🔕 Alert suppressed "
                                f"| preset="
                                f"{preset} "
                                f"| class="
                                f"{detection.canonical_class} "
                                f"| {reason}"
                            )

                            continue


                        # =========================================
                        # NEW EVENT
                        # =========================================

                        print(
                            "🆕 New alert event "
                            f"| preset="
                            f"{preset} "
                            f"| class="
                            f"{detection.canonical_class}"
                        )


                        # -----------------------------------------
                        # Dashboard latest alert
                        # -----------------------------------------

                        atomic_imwrite(
                            LATEST_ALERT,
                            frame,
                        )


                        # -----------------------------------------
                        # Build safe message
                        # -----------------------------------------

                        message = (
                            format_alert(
                                detection,
                                bearing_calibrated=(
                                    site_bearing_calibrated
                                ),
                            )
                        )


                        # -----------------------------------------
                        # Alert accepted state
                        # -----------------------------------------

                        alert_accepted = True


                        # =========================================
                        # Telegram enabled
                        # =========================================

                        if notifier.enabled:


                            # -------------------------------------
                            # Create unique spool image
                            # -------------------------------------

                            spool_path = (
                                create_alert_spool(
                                    frame,
                                    preset,
                                    detection,
                                )
                            )


                            if spool_path is None:

                                print(
                                    "⚠️ Alert spool "
                                    "could not be "
                                    "created"
                                )

                                # ไม่ record cooldown
                                # เพื่อให้รอบถัดไป retry
                                alert_accepted = (
                                    False
                                )


                            else:


                                # ---------------------------------
                                # Queue Telegram
                                # ---------------------------------

                                alert_accepted = (
                                    notifier.submit(
                                        message,
                                        str(
                                            spool_path
                                        ),
                                        delete_after_send=True,
                                    )
                                )


                                if alert_accepted:

                                    print(
                                        "📨 Telegram "
                                        "alert queued"
                                    )

                                else:

                                    print(
                                        "⚠️ Telegram "
                                        "queue rejected "
                                        "alert"
                                    )


                        # =========================================
                        # Telegram disabled
                        # =========================================

                        else:

                            print(
                                "ℹ️ Telegram "
                                "not configured; "
                                "local alert only"
                            )


                        # =========================================
                        # Record cooldown event
                        # =========================================
                        #
                        # Record เมื่อ:
                        #
                        # - Telegram queue รับแล้ว
                        # หรือ
                        # - Telegram disabled แต่ Local alert สำเร็จ
                        #
                        # ถ้า Queue เต็ม / spool fail
                        # จะไม่ Record เพื่อให้ retry
                        # =========================================

                        if alert_accepted:

                            alert_dedup.record_alert(
                                detection,
                                preset,
                                now_mono,
                            )


                        # =========================================
                        # Console Alert
                        # =========================================

                        print(
                            "\n"
                            + "=" * 76
                        )

                        print(
                            "🔔 ALERT"
                        )

                        print(
                            f"Preset: "
                            f"{preset}"
                        )

                        print(
                            f"Event: "
                            f"{reason}"
                        )

                        print(
                            message
                        )

                        print(
                            "=" * 76
                        )


    # ========================================================
    # Stop
    # ========================================================

    except KeyboardInterrupt:

        print(
            "\n🛑 Stop requested"
        )


    finally:

        print(
            "📡 Stopping camera..."
        )

        camera.stop()

        print(
            "✅ Smart Fire Detection "
            "stopped"
        )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()
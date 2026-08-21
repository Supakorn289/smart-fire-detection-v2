#!/usr/bin/env python3
# tests/test_integration_alert_pipeline.py

"""
Smart Fire Detection v2
Alert Pipeline Integration Tests

Scope:

    Confirmed Detection
            ↓
    Alert Event Deduplication
            ↓
    Local Alert Image
            ↓
    Safety-aware Message
            ↓
    Unique Alert Spool
            ↓
    TelegramWorker Queue
            ↓
    Cooldown Record

IMPORTANT:
- ไม่เชื่อม Telegram จริง
- ไม่ทำ HTTP request
- ไม่ใช้ Camera
- ไม่ใช้ PTZ
- ไม่ใช้ AI model
- ไม่ใช้ Production hardware
"""

import queue
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

import main as runtime
import notify


# ============================================================
# Helpers
# ============================================================

def make_detection(
    *,
    canonical_class="fire",
    model_class="fire",
    confidence=0.91,
    bbox=(300, 200, 500, 500),
    bearing_deg=45.0,
    distance_m=None,
    distance_quality="unavailable",
    gps=None,
):
    """
    Minimal Detection-compatible object

    ใช้ SimpleNamespace เพื่อทดสอบ Alert layer
    โดยไม่ต้องโหลด AI Model
    """

    return SimpleNamespace(
        canonical_class=canonical_class,
        model_class=model_class,
        confidence=confidence,
        bbox=bbox,
        bearing_deg=bearing_deg,
        distance_m=distance_m,
        distance_quality=distance_quality,
        gps=gps,
    )


def make_frame():
    """
    Synthetic BGR frame

    ไม่มี Camera / Network
    """

    return np.zeros(
        (
            120,
            160,
            3,
        ),
        dtype=np.uint8,
    )


def make_enabled_worker(
    max_queue=5,
):
    """
    สร้าง TelegramWorker สำหรับ Queue Test เท่านั้น

    ไม่เรียก __init__()
    เพื่อไม่สร้าง Background Thread

    จึงไม่มี Network / Telegram HTTP request
    """

    worker = (
        notify.TelegramWorker.__new__(
            notify.TelegramWorker
        )
    )

    worker.enabled = True

    worker.q = queue.Queue(
        maxsize=max_queue
    )

    worker.thread = None

    return worker


# ============================================================
# Test 1
# Same event is suppressed during cooldown
# ============================================================

def test_alert_deduplicator_suppresses_same_event():

    dedup = runtime.AlertDeduplicator(
        cooldown_sec=30.0,
        iou_threshold=0.50,
    )


    first = make_detection(
        bbox=(
            300,
            200,
            500,
            500,
        )
    )


    should_alert, reason = (
        dedup.should_alert(
            first,
            preset=1,
            now_mono=100.0,
        )
    )


    assert should_alert is True

    assert (
        reason
        == "new_event"
    )


    dedup.record_alert(
        first,
        preset=1,
        now_mono=100.0,
    )


    # --------------------------------------------------------
    # Object ขยับเล็กน้อย
    # แต่ยังมี IoU สูง
    # --------------------------------------------------------

    second = make_detection(
        bbox=(
            305,
            205,
            505,
            505,
        )
    )


    should_alert, reason = (
        dedup.should_alert(
            second,
            preset=1,
            now_mono=105.0,
        )
    )


    assert should_alert is False

    assert (
        reason.startswith(
            "duplicate "
        )
    )

    assert (
        "remaining="
        in reason
    )


# ============================================================
# Test 2
# Different preset / different object = new event
# ============================================================

def test_alert_deduplicator_separates_independent_events():

    dedup = runtime.AlertDeduplicator(
        cooldown_sec=30.0,
        iou_threshold=0.50,
    )


    original = make_detection(
        bbox=(
            300,
            200,
            500,
            500,
        )
    )


    dedup.record_alert(
        original,
        preset=1,
        now_mono=100.0,
    )


    # --------------------------------------------------------
    # Same object but different preset
    # ต้องไม่ถูก cooldown ข้าม preset
    # --------------------------------------------------------

    should_alert, reason = (
        dedup.should_alert(
            original,
            preset=2,
            now_mono=105.0,
        )
    )


    assert should_alert is True

    assert (
        reason
        == "new_event"
    )


    # --------------------------------------------------------
    # Same preset but different spatial object
    # IoU ต่ำ
    # --------------------------------------------------------

    different_object = make_detection(
        bbox=(
            700,
            200,
            900,
            500,
        )
    )


    should_alert, reason = (
        dedup.should_alert(
            different_object,
            preset=1,
            now_mono=105.0,
        )
    )


    assert should_alert is True

    assert (
        reason
        == "new_event"
    )


# ============================================================
# Test 3
# Cooldown expiry
# ============================================================

def test_alert_deduplicator_allows_event_after_cooldown():

    dedup = runtime.AlertDeduplicator(
        cooldown_sec=30.0,
        iou_threshold=0.50,
    )


    detection = make_detection()


    dedup.record_alert(
        detection,
        preset=1,
        now_mono=100.0,
    )


    # --------------------------------------------------------
    # 31 sec > cooldown 30 sec
    # --------------------------------------------------------

    should_alert, reason = (
        dedup.should_alert(
            detection,
            preset=1,
            now_mono=131.0,
        )
    )


    assert should_alert is True

    assert (
        reason
        == "new_event"
    )


# ============================================================
# Test 4
# Unique alert spool images
# ============================================================

def test_create_alert_spool_creates_unique_jpeg(
    tmp_path,
    monkeypatch,
):

    spool_dir = (
        tmp_path
        / "alert_spool"
    )


    monkeypatch.setattr(
        runtime,
        "ALERT_SPOOL_DIR",
        spool_dir,
    )


    frame = make_frame()

    detection = make_detection()


    first = runtime.create_alert_spool(
        frame,
        preset=3,
        detection=detection,
    )


    second = runtime.create_alert_spool(
        frame,
        preset=3,
        detection=detection,
    )


    assert first is not None

    assert second is not None


    first = Path(
        first
    )

    second = Path(
        second
    )


    assert first.is_file()

    assert second.is_file()


    # --------------------------------------------------------
    # แต่ละ Alert ต้องมีไฟล์ของตัวเอง
    # --------------------------------------------------------

    assert (
        first
        != second
    )


    assert (
        first.parent
        == spool_dir
    )

    assert (
        second.parent
        == spool_dir
    )


    assert (
        "p3_fire"
        in first.name
    )


    # --------------------------------------------------------
    # ตรวจว่าเป็น JPEG ที่ OpenCV อ่านได้จริง
    # --------------------------------------------------------

    decoded = cv2.imread(
        str(
            first
        )
    )


    assert (
        decoded
        is not None
    )

    assert (
        decoded.size
        > 0
    )


# ============================================================
# Test 5
# Unsafe location must not leak GPS link
# ============================================================

def test_format_alert_suppresses_unsafe_gps():

    detection = make_detection(
        bearing_deg=80.0,
        distance_m=25.0,
        distance_quality=(
            "unverified-range"
        ),
        gps=(
            1.234567,
            2.345678,
        ),
    )


    message = notify.format_alert(
        detection,
        bearing_calibrated=False,
    )


    # --------------------------------------------------------
    # Bearing calibration warning
    # --------------------------------------------------------

    assert (
        "Site Bearing Calibration"
        in message
    )


    # --------------------------------------------------------
    # GPS object มีอยู่ใน Detection
    # แต่ quality/site ไม่ผ่าน
    #
    # ต้องไม่มี Google Maps link
    # --------------------------------------------------------

    assert (
        "google.com/maps"
        not in message
    )


    assert (
        "Location Safety Guard"
        in message
    )


# ============================================================
# Test 6
# GPS may appear only when location quality is valid
# ============================================================

def test_format_alert_includes_gps_only_when_safe():

    detection = make_detection(
        bearing_deg=90.0,
        distance_m=20.0,
        distance_quality="calibrated",
        gps=(
            1.234567,
            2.345678,
        ),
    )


    message = notify.format_alert(
        detection,
        bearing_calibrated=True,
    )


    assert (
        "1.234567, 2.345678"
        in message
    )

    assert (
        "google.com/maps"
        in message
    )

    assert (
        "Location Safety Guard"
        not in message
    )


# ============================================================
# Test 7
# TelegramWorker submit -> queue
# ============================================================

def test_telegram_worker_submit_queues_without_network():

    worker = make_enabled_worker(
        max_queue=2
    )


    accepted = worker.submit(
        "integration-test",
        "alert-test.jpg",
        delete_after_send=True,
    )


    assert (
        accepted
        is True
    )


    item = (
        worker.q.get_nowait()
    )


    assert (
        item
        == (
            "integration-test",
            "alert-test.jpg",
            True,
        )
    )


    worker.q.task_done()


# ============================================================
# Test 8
# Full queue -> reject + spool cleanup
# ============================================================

def test_telegram_worker_full_queue_rejects_and_cleans_spool(
    tmp_path,
):

    worker = make_enabled_worker(
        max_queue=1
    )


    # --------------------------------------------------------
    # Fill queue
    # --------------------------------------------------------

    worker.q.put_nowait(
        (
            "existing-alert",
            None,
            False,
        )
    )


    spool_file = (
        tmp_path
        / "queued-alert.jpg"
    )


    spool_file.write_bytes(
        b"temporary-spool"
    )


    assert (
        spool_file.is_file()
    )


    accepted = worker.submit(
        "new-alert",
        str(
            spool_file
        ),
        delete_after_send=True,
    )


    assert (
        accepted
        is False
    )


    # --------------------------------------------------------
    # submit() ต้อง cleanup spool
    # เมื่อไฟล์ยังไม่ได้เข้า queue
    # --------------------------------------------------------

    assert (
        not spool_file.exists()
    )


# ============================================================
# Test 9
# Integrated Alert Path
# ============================================================

def test_confirmed_alert_to_dashboard_spool_queue_and_dedup(
    tmp_path,
    monkeypatch,
):

    # ========================================================
    # Temporary runtime paths
    # ========================================================

    latest_alert = (
        tmp_path
        / "latest_alert.jpg"
    )


    spool_dir = (
        tmp_path
        / "alert_spool"
    )


    monkeypatch.setattr(
        runtime,
        "LATEST_ALERT",
        latest_alert,
    )


    monkeypatch.setattr(
        runtime,
        "ALERT_SPOOL_DIR",
        spool_dir,
    )


    # ========================================================
    # Confirmed Detection
    # ========================================================

    detection = make_detection(
        canonical_class="fire",
        model_class="fire",
        confidence=0.93,
        bbox=(
            300,
            200,
            500,
            500,
        ),
        bearing_deg=45.0,
        distance_m=None,
        distance_quality="unavailable",
        gps=None,
    )


    frame = make_frame()


    # ========================================================
    # Event Dedup
    # ========================================================

    dedup = runtime.AlertDeduplicator(
        cooldown_sec=30.0,
        iou_threshold=0.50,
    )


    should_alert, reason = (
        dedup.should_alert(
            detection,
            preset=1,
            now_mono=100.0,
        )
    )


    assert (
        should_alert
        is True
    )

    assert (
        reason
        == "new_event"
    )


    # ========================================================
    # Dashboard latest alert
    # ========================================================

    local_write_ok = (
        runtime.atomic_imwrite(
            latest_alert,
            frame,
        )
    )


    assert (
        local_write_ok
        is True
    )

    assert (
        latest_alert.is_file()
    )


    # ========================================================
    # Safety-aware notification message
    # ========================================================

    message = notify.format_alert(
        detection,
        bearing_calibrated=False,
    )


    assert (
        "fire"
        in message.lower()
    )


    assert (
        "google.com/maps"
        not in message
    )


    # ========================================================
    # Unique Telegram spool
    # ========================================================

    spool_path = (
        runtime.create_alert_spool(
            frame,
            preset=1,
            detection=detection,
        )
    )


    assert (
        spool_path
        is not None
    )


    spool_path = Path(
        spool_path
    )


    assert (
        spool_path.is_file()
    )


    # ========================================================
    # Telegram queue
    #
    # ไม่มี Background Thread
    # ไม่มี HTTP request
    # ========================================================

    worker = make_enabled_worker(
        max_queue=5
    )


    alert_accepted = (
        worker.submit(
            message,
            str(
                spool_path
            ),
            delete_after_send=True,
        )
    )


    assert (
        alert_accepted
        is True
    )


    # ========================================================
    # Record cooldown ONLY after queue accepted
    # ========================================================

    if alert_accepted:

        dedup.record_alert(
            detection,
            preset=1,
            now_mono=100.0,
        )


    assert (
        len(
            dedup.events
        )
        == 1
    )


    # ========================================================
    # Inspect queued item
    # ========================================================

    (
        queued_message,
        queued_image,
        delete_after_send,
    ) = worker.q.get_nowait()


    assert (
        queued_message
        == message
    )


    assert (
        Path(
            queued_image
        )
        == spool_path
    )


    assert (
        delete_after_send
        is True
    )


    # --------------------------------------------------------
    # Critical race protection:
    #
    # Telegram queue ต้องใช้ unique spool
    # ไม่ใช่ latest_alert.jpg
    # --------------------------------------------------------

    assert (
        Path(
            queued_image
        )
        != latest_alert
    )


    assert (
        latest_alert.is_file()
    )

    assert (
        spool_path.is_file()
    )


    worker.q.task_done()


    # ========================================================
    # Same event immediately afterwards
    # must now be suppressed
    # ========================================================

    should_alert, reason = (
        dedup.should_alert(
            detection,
            preset=1,
            now_mono=101.0,
        )
    )


    assert (
        should_alert
        is False
    )

    assert (
        reason.startswith(
            "duplicate "
        )
    )
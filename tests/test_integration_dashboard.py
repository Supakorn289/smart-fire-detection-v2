#!/usr/bin/env python3
# tests/test_integration_dashboard.py

"""
Smart Fire Detection v2
Dashboard / Runtime Output Integration Tests

Scope:

    Runtime files
        ↓
    app.py
        ↓
    Flask routes
        ↓
    HTTP response

ไม่ใช้:
- Camera
- PTZ
- AI inference
- Telegram
- Network socket
- Production hardware
"""

import json

import cv2
import numpy as np
import pytest

import app as dashboard_module


# ============================================================
# Helpers
# ============================================================

def make_client():

    dashboard_module.app.config.update(
        TESTING=True
    )

    return (
        dashboard_module.app.test_client()
    )


def make_jpeg(
    path,
):

    frame = np.zeros(
        (
            120,
            160,
            3,
        ),
        dtype=np.uint8,
    )

    ok = cv2.imwrite(
        str(path),
        frame,
    )

    assert ok is True

    assert path.is_file()


# ============================================================
# Test 1
# Dashboard process health
# ============================================================

def test_health_endpoint_reports_dashboard_process():

    client = make_client()

    response = client.get(
        "/health"
    )


    assert (
        response.status_code
        == 200
    )


    payload = (
        response.get_json()
    )


    assert (
        payload["status"]
        == "ok"
    )

    assert (
        payload["service"]
        == "smart-fire-dashboard"
    )

    assert isinstance(
        payload["timestamp"],
        (
            int,
            float,
        ),
    )


# ============================================================
# Test 2
# Runtime not started yet
# ============================================================

def test_status_waiting_when_runtime_file_missing(
    tmp_path,
    monkeypatch,
):

    status_file = (
        tmp_path
        / "status.json"
    )


    monkeypatch.setattr(
        dashboard_module,
        "STATUS_FILE",
        status_file,
    )


    client = make_client()

    response = client.get(
        "/api/status"
    )


    assert (
        response.status_code
        == 200
    )


    assert (
        response.get_json()
        == {
            "status": "waiting",
            "runtime_status": "waiting",
        }
    )


# ============================================================
# Test 3
# Runtime status -> Dashboard API
# ============================================================

def test_valid_runtime_status_is_exposed_by_dashboard(
    tmp_path,
    monkeypatch,
):

    status_file = (
        tmp_path
        / "status.json"
    )


    runtime_payload = {

        "timestamp":
            1234567890.0,

        "runtime_status":
            "running",

        "cycle":
            4,

        "step":
            7,

        "preset":
            3,

        "confirmed":
            1,

        "ai": {
            "release":
                "R3-E6",

            "backend":
                "pt",

            "device":
                "cpu",
        },
    }


    status_file.write_text(
        json.dumps(
            runtime_payload
        ),
        encoding="utf-8",
    )


    monkeypatch.setattr(
        dashboard_module,
        "STATUS_FILE",
        status_file,
    )


    client = make_client()

    response = client.get(
        "/api/status"
    )


    assert (
        response.status_code
        == 200
    )


    assert (
        response.get_json()
        == runtime_payload
    )


# ============================================================
# Test 4
# Corrupted Runtime JSON
# ============================================================

def test_invalid_runtime_json_returns_503(
    tmp_path,
    monkeypatch,
):

    status_file = (
        tmp_path
        / "status.json"
    )


    status_file.write_text(
        "{broken-json",
        encoding="utf-8",
    )


    monkeypatch.setattr(
        dashboard_module,
        "STATUS_FILE",
        status_file,
    )


    client = make_client()

    response = client.get(
        "/api/status"
    )


    assert (
        response.status_code
        == 503
    )


    assert (
        response.get_json()
        == {
            "status":
                "unavailable",

            "runtime_status":
                "invalid_status_json",
        }
    )


# ============================================================
# Test 5
# Valid JSON but invalid root type
# ============================================================

@pytest.mark.parametrize(
    "invalid_payload",
    [
        [],
        "running",
        123,
        True,
    ],
)
def test_status_requires_json_object(
    tmp_path,
    monkeypatch,
    invalid_payload,
):

    status_file = (
        tmp_path
        / "status.json"
    )


    status_file.write_text(
        json.dumps(
            invalid_payload
        ),
        encoding="utf-8",
    )


    monkeypatch.setattr(
        dashboard_module,
        "STATUS_FILE",
        status_file,
    )


    client = make_client()

    response = client.get(
        "/api/status"
    )


    assert (
        response.status_code
        == 503
    )


    assert (
        response.get_json()
        == {
            "status":
                "unavailable",

            "runtime_status":
                "invalid_status_format",
        }
    )


# ============================================================
# Test 6
# Missing image behavior
# ============================================================

def test_missing_runtime_images_return_404(
    tmp_path,
    monkeypatch,
):

    latest_frame = (
        tmp_path
        / "latest_frame.jpg"
    )

    latest_alert = (
        tmp_path
        / "latest_alert.jpg"
    )


    monkeypatch.setattr(
        dashboard_module,
        "LATEST_FRAME_FILE",
        latest_frame,
    )

    monkeypatch.setattr(
        dashboard_module,
        "LATEST_ALERT_FILE",
        latest_alert,
    )


    client = make_client()


    # --------------------------------------------------------
    # Latest frame
    # --------------------------------------------------------

    response = client.get(
        "/image/latest"
    )


    assert (
        response.status_code
        == 404
    )

    assert (
        response.get_json()
        == {
            "status":
                "latest_frame_unavailable"
        }
    )


    # --------------------------------------------------------
    # Latest alert
    # --------------------------------------------------------

    response = client.get(
        "/image/alert"
    )


    assert (
        response.status_code
        == 404
    )

    assert (
        response.get_json()
        == {
            "status":
                "latest_alert_unavailable"
        }
    )


# ============================================================
# Test 7
# Runtime JPEG -> Dashboard
# ============================================================

def test_runtime_images_are_served_as_jpeg(
    tmp_path,
    monkeypatch,
):

    latest_frame = (
        tmp_path
        / "latest_frame.jpg"
    )

    latest_alert = (
        tmp_path
        / "latest_alert.jpg"
    )


    make_jpeg(
        latest_frame
    )

    make_jpeg(
        latest_alert
    )


    monkeypatch.setattr(
        dashboard_module,
        "LATEST_FRAME_FILE",
        latest_frame,
    )

    monkeypatch.setattr(
        dashboard_module,
        "LATEST_ALERT_FILE",
        latest_alert,
    )


    client = make_client()


    for endpoint in (
        "/image/latest",
        "/image/alert",
    ):

        response = client.get(
            endpoint
        )


        assert (
            response.status_code
            == 200
        )


        assert (
            response.mimetype
            == "image/jpeg"
        )


        assert (
            len(
                response.data
            )
            > 0
        )


        # ----------------------------------------------------
        # Runtime images ต้องไม่ถูก Browser cache ค้าง
        # ----------------------------------------------------

        assert (
            "no-store"
            in response.headers.get(
                "Cache-Control",
                ""
            )
        )


# ============================================================
# Test 8
# Dashboard page + security boundary
# ============================================================

def test_dashboard_page_and_static_security_boundary(
    tmp_path,
    monkeypatch,
):

    client = make_client()


    # --------------------------------------------------------
    # Dashboard HTML
    # --------------------------------------------------------

    response = client.get(
        "/"
    )


    assert (
        response.status_code
        == 200
    )

    assert (
        response.mimetype
        == "text/html"
    )

    assert (
        b"Smart Fire Detection v2"
        in response.data
    )


    # --------------------------------------------------------
    # Flask automatic static serving ต้องปิด
    #
    # Runtime files ห้ามถูกเปิดเป็น:
    #
    # /static/<filename>
    # --------------------------------------------------------

    secret_file = (
        tmp_path
        / "secret-runtime-data.txt"
    )

    secret_file.write_text(
        "SHOULD-NOT-BE-PUBLIC",
        encoding="utf-8",
    )


    response = client.get(
        "/static/secret-runtime-data.txt"
    )


    assert (
        response.status_code
        == 404
    )


# ============================================================
# Test 9
# Security / cache response headers
# ============================================================

def test_dashboard_security_headers():

    client = make_client()

    response = client.get(
        "/health"
    )


    assert (
        response.status_code
        == 200
    )


    assert (
        response.headers.get(
            "X-Content-Type-Options"
        )
        == "nosniff"
    )


    assert (
        response.headers.get(
            "X-Frame-Options"
        )
        == "SAMEORIGIN"
    )


    assert (
        response.headers.get(
            "Referrer-Policy"
        )
        == "no-referrer"
    )


    cache_control = (
        response.headers.get(
            "Cache-Control",
            ""
        )
    )


    assert (
        "no-store"
        in cache_control
    )
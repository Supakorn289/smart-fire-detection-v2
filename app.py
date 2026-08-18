#!/usr/bin/env python3
# app.py

import json
import time

from flask import (
    Flask,
    Response,
    jsonify,
    send_file,
)

from config import STATIC_DIR


# ============================================================
# Flask Application
# ============================================================
#
# ปิด Flask automatic static serving
#
# ห้ามใช้:
#
#   static_folder=str(STATIC_DIR)
#
# เพราะจะทำให้ไฟล์ Runtime ทุกไฟล์ใน STATIC_DIR
# ถูกเข้าถึงผ่าน Web ได้
#
# Dashboard จะเปิดเฉพาะ:
#
#   /
#   /api/status
#   /health
#   /image/latest
#   /image/alert
#
# Production ใช้:
#
#   waitress-serve --host=0.0.0.0 --port=5000 app:app
#
# ============================================================

app = Flask(
    __name__,
    static_folder=None,
)


# ============================================================
# Runtime Files
# ============================================================

STATUS_FILE = (
    STATIC_DIR
    / "status.json"
)

LATEST_FRAME_FILE = (
    STATIC_DIR
    / "latest_frame.jpg"
)

LATEST_ALERT_FILE = (
    STATIC_DIR
    / "latest_alert.jpg"
)


# ============================================================
# Dashboard HTML
# ============================================================

HTML = r"""
<!doctype html>

<html lang="th">

<head>

    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <meta
        name="color-scheme"
        content="dark"
    >

    <title>
        Smart Fire Detection v2
    </title>

    <style>

        :root {
            color-scheme: dark;

            --background: #111827;
            --panel: #1f2937;
            --panel-dark: #0f172a;

            --border: #374151;

            --text: #e5e7eb;
            --muted: #9ca3af;

            --green: #86efac;
            --yellow: #fde68a;
            --red: #fca5a5;
        }


        * {
            box-sizing: border-box;
        }


        body {

            margin: 0;

            padding: 20px;

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            background:
                var(--background);

            color:
                var(--text);
        }


        .container {

            width: 100%;

            max-width: 1500px;

            margin:
                0
                auto;
        }


        h1 {

            margin:
                0
                0
                8px
                0;

            font-size: 28px;
        }


        h2 {

            margin:
                0
                0
                14px
                0;

            font-size: 20px;
        }


        .subtitle {

            margin-bottom: 18px;

            color:
                var(--muted);
        }


        .connection {

            display: inline-block;

            margin-bottom: 18px;

            padding:
                7px
                12px;

            border:
                1px
                solid
                var(--border);

            border-radius: 999px;

            background:
                var(--panel);

            color:
                var(--muted);

            font-size: 14px;
        }


        .connection.ok {

            color:
                var(--green);
        }


        .connection.warn {

            color:
                var(--yellow);
        }


        .connection.error {

            color:
                var(--red);
        }


        .grid {

            display: grid;

            grid-template-columns:
                repeat(
                    2,
                    minmax(
                        0,
                        1fr
                    )
                );

            gap: 16px;
        }


        .card {

            padding: 16px;

            border:
                1px
                solid
                var(--border);

            border-radius: 12px;

            background:
                var(--panel);
        }


        .status-card {

            margin-top: 16px;
        }


        .image-container {

            position: relative;

            width: 100%;

            min-height: 240px;

            display: flex;

            align-items: center;

            justify-content: center;

            overflow: hidden;

            border-radius: 8px;

            background:
                var(--panel-dark);
        }


        .camera-image {

            display: block;

            width: 100%;

            max-height: 70vh;

            object-fit: contain;
        }


        .image-status {

            position: absolute;

            left: 12px;

            bottom: 12px;

            padding:
                6px
                9px;

            border-radius: 6px;

            background:
                rgba(
                    0,
                    0,
                    0,
                    0.65
                );

            color:
                var(--muted);

            font-size: 12px;
        }


        pre {

            margin: 0;

            padding: 14px;

            max-height: 500px;

            overflow: auto;

            white-space: pre-wrap;

            overflow-wrap: anywhere;

            border-radius: 8px;

            background:
                var(--panel-dark);

            color:
                var(--text);

            font-family:
                Consolas,
                "Courier New",
                monospace;

            font-size: 13px;

            line-height: 1.5;
        }


        @media (
            max-width: 800px
        ) {

            body {
                padding: 12px;
            }


            .grid {

                grid-template-columns:
                    1fr;
            }


            h1 {

                font-size: 23px;
            }
        }

    </style>

</head>


<body>

<div class="container">


    <h1>
        Smart Fire Detection v2
    </h1>


    <div class="subtitle">
        Production Monitoring Dashboard
    </div>


    <div
        id="connection-status"
        class="connection"
    >
        Connecting...
    </div>


    <div class="grid">


        <!-- ==================================================
             Latest camera frame
             ================================================== -->

        <div class="card">

            <h2>
                Latest Frame
            </h2>


            <div class="image-container">

                <img
                    id="latest-frame"
                    class="camera-image"
                    src="/image/latest"
                    alt="Latest camera frame"
                >

                <div
                    id="latest-frame-status"
                    class="image-status"
                >
                    Waiting...
                </div>

            </div>

        </div>


        <!-- ==================================================
             Latest alert
             ================================================== -->

        <div class="card">

            <h2>
                Last Alert
            </h2>


            <div class="image-container">

                <img
                    id="latest-alert"
                    class="camera-image"
                    src="/image/alert"
                    alt="Latest alert"
                >

                <div
                    id="latest-alert-status"
                    class="image-status"
                >
                    Waiting...
                </div>

            </div>

        </div>


    </div>


    <!-- ======================================================
         Runtime Status
         ====================================================== -->

    <div class="card status-card">

        <h2>
            Runtime Status
        </h2>


        <pre id="status-json">{
  "status": "waiting"
}</pre>

    </div>


</div>


<script>

    "use strict";


    // ========================================================
    // Dashboard configuration
    // ========================================================

    const REFRESH_INTERVAL_MS = 3000;


    // ========================================================
    // DOM references
    // ========================================================

    const connectionStatus = (
        document.getElementById(
            "connection-status"
        )
    );


    const statusJson = (
        document.getElementById(
            "status-json"
        )
    );


    const latestFrame = (
        document.getElementById(
            "latest-frame"
        )
    );


    const latestAlert = (
        document.getElementById(
            "latest-alert"
        )
    );


    const latestFrameStatus = (
        document.getElementById(
            "latest-frame-status"
        )
    );


    const latestAlertStatus = (
        document.getElementById(
            "latest-alert-status"
        )
    );


    // ========================================================
    // Connection status
    // ========================================================

    function setConnectionStatus(
        text,
        state
    ) {

        connectionStatus.textContent = (
            text
        );


        connectionStatus.className = (
            "connection"
        );


        if (state) {

            connectionStatus.classList.add(
                state
            );
        }
    }


    // ========================================================
    // Status API
    // ========================================================

    async function refreshStatus() {

        try {

            const response = await fetch(
                "/api/status",
                {
                    method: "GET",
                    cache: "no-store"
                }
            );


            const data = await response.json();


            statusJson.textContent = (
                JSON.stringify(
                    data,
                    null,
                    2
                )
            );


            if (response.ok) {

                setConnectionStatus(
                    "Runtime connected",
                    "ok"
                );

            } else {

                setConnectionStatus(
                    "Runtime status unavailable",
                    "warn"
                );
            }


        } catch (error) {

            setConnectionStatus(
                "Dashboard API unavailable",
                "error"
            );


            statusJson.textContent = (
                JSON.stringify(
                    {
                        status:
                            "api_unavailable"
                    },
                    null,
                    2
                )
            );
        }
    }


    // ========================================================
    // Image refresh helper
    // ========================================================

    function refreshImage(
        element,
        endpoint
    ) {

        const timestamp = (
            Date.now()
        );


        element.src = (
            endpoint
            + "?t="
            + timestamp
        );
    }


    // ========================================================
    // Latest frame handlers
    // ========================================================

    latestFrame.addEventListener(
        "load",
        function () {

            latestFrameStatus.textContent = (
                "Updated "
                + new Date()
                    .toLocaleTimeString()
            );
        }
    );


    latestFrame.addEventListener(
        "error",
        function () {

            latestFrameStatus.textContent = (
                "Frame unavailable"
            );
        }
    );


    // ========================================================
    // Latest alert handlers
    // ========================================================

    latestAlert.addEventListener(
        "load",
        function () {

            latestAlertStatus.textContent = (
                "Updated "
                + new Date()
                    .toLocaleTimeString()
            );
        }
    );


    latestAlert.addEventListener(
        "error",
        function () {

            latestAlertStatus.textContent = (
                "No alert image"
            );
        }
    );


    // ========================================================
    // Refresh dashboard
    // ========================================================

    async function refreshDashboard() {

        await refreshStatus();


        refreshImage(
            latestFrame,
            "/image/latest"
        );


        refreshImage(
            latestAlert,
            "/image/alert"
        );
    }


    // First load

    refreshDashboard();


    // Repeating refresh

    window.setInterval(
        refreshDashboard,
        REFRESH_INTERVAL_MS
    );

</script>


</body>

</html>
"""


# ============================================================
# Response Security / Cache Headers
# ============================================================

@app.after_request
def apply_response_headers(
    response,
):
    """
    Apply basic response headers.

    Dashboard เป็น Runtime monitoring
    จึงไม่ควร Cache status/image เก่า
    """

    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate, "
        "max-age=0"
    )

    response.headers[
        "Pragma"
    ] = "no-cache"

    response.headers[
        "Expires"
    ] = "0"

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    return response


# ============================================================
# Runtime Status Reader
# ============================================================

def read_status():
    """
    Safely read status.json.

    Returns:
        tuple:
            (
                payload: dict,
                HTTP status code: int
            )

    กรณีไม่มี status.json:
        200 waiting

    กรณีอ่านไฟล์ไม่ได้:
        503

    กรณี JSON เสีย:
        503
    """

    # --------------------------------------------------------
    # Runtime ยังไม่สร้าง status.json
    # --------------------------------------------------------

    if not STATUS_FILE.is_file():

        return (
            {
                "status": "waiting",
                "runtime_status": "waiting",
            },
            200,
        )


    # --------------------------------------------------------
    # Read file
    # --------------------------------------------------------

    try:

        raw = (
            STATUS_FILE
            .read_text(
                encoding="utf-8"
            )
        )

    except OSError as exc:

        app.logger.warning(
            "Cannot read status.json: %s",
            exc,
        )

        return (
            {
                "status":
                    "unavailable",

                "runtime_status":
                    "status_read_error",
            },
            503,
        )


    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        payload = json.loads(
            raw
        )

    except json.JSONDecodeError as exc:

        app.logger.warning(
            "Invalid status.json: %s",
            exc,
        )

        return (
            {
                "status":
                    "unavailable",

                "runtime_status":
                    "invalid_status_json",
            },
            503,
        )


    # --------------------------------------------------------
    # Root object validation
    # --------------------------------------------------------

    if not isinstance(
        payload,
        dict,
    ):

        app.logger.warning(
            "status.json root is not "
            "a JSON object"
        )

        return (
            {
                "status":
                    "unavailable",

                "runtime_status":
                    "invalid_status_format",
            },
            503,
        )


    return (
        payload,
        200,
    )


# ============================================================
# Dashboard
# ============================================================

@app.get("/")
def index():

    return Response(
        HTML,
        status=200,
        mimetype="text/html",
    )


# ============================================================
# Status API
# ============================================================

@app.get("/api/status")
def api_status():

    payload, status_code = (
        read_status()
    )

    response = jsonify(
        payload
    )

    response.status_code = (
        status_code
    )

    return response


# ============================================================
# Health API
# ============================================================
#
# Health endpoint ตรวจเฉพาะว่า
# Dashboard Process ทำงานอยู่
#
# ไม่ได้แปลว่า:
#
# - Camera พร้อม
# - AI พร้อม
# - Calibration พร้อม
#
# Runtime readiness ดูจาก /api/status
#
# ============================================================

@app.get("/health")
def health():

    return jsonify(
        {
            "status": "ok",

            "service":
                "smart-fire-dashboard",

            "timestamp":
                time.time(),
        }
    )


# ============================================================
# Latest Camera Frame
# ============================================================

@app.get("/image/latest")
def latest_frame():

    if not LATEST_FRAME_FILE.is_file():

        return (
            jsonify(
                {
                    "status":
                        "latest_frame_unavailable"
                }
            ),
            404,
        )


    try:

        return send_file(
            LATEST_FRAME_FILE,
            mimetype="image/jpeg",
            conditional=False,
            max_age=0,
        )

    except OSError as exc:

        app.logger.warning(
            "Cannot serve latest frame: %s",
            exc,
        )

        return (
            jsonify(
                {
                    "status":
                        "latest_frame_unavailable"
                }
            ),
            503,
        )


# ============================================================
# Latest Alert Image
# ============================================================

@app.get("/image/alert")
def latest_alert():

    if not LATEST_ALERT_FILE.is_file():

        return (
            jsonify(
                {
                    "status":
                        "latest_alert_unavailable"
                }
            ),
            404,
        )


    try:

        return send_file(
            LATEST_ALERT_FILE,
            mimetype="image/jpeg",
            conditional=False,
            max_age=0,
        )

    except OSError as exc:

        app.logger.warning(
            "Cannot serve latest alert: %s",
            exc,
        )

        return (
            jsonify(
                {
                    "status":
                        "latest_alert_unavailable"
                }
            ),
            503,
        )


# ============================================================
# Development Entry Point
# ============================================================
#
# Production:
#
# ห้ามใช้ Flask Development Server
#
# Production ใช้ Waitress:
#
# waitress-serve \
#     --host=0.0.0.0 \
#     --port=5000 \
#     app:app
#
# block นี้มีไว้สำหรับ Local Development เท่านั้น
#
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )
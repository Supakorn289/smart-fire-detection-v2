#!/usr/bin/env python3

import queue
import threading
from pathlib import Path

import requests

from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
)
from geometry import bearing_to_compass


# ============================================================
# Location safety
# ============================================================

GPS_ALLOWED_QUALITIES = {
    "calibrated",
    "calibrated-low",
}


def _distance_text(d) -> str:
    """
    Format distance according to the current calibration-quality system.
    """

    distance = getattr(
        d,
        "distance_m",
        None,
    )

    quality = str(
        getattr(
            d,
            "distance_quality",
            "unavailable",
        )
        or "unavailable"
    )

    if distance is None:
        return (
            "ระยะทาง: ไม่สามารถคำนวณได้ "
            "/ ยังไม่มี Distance Calibration"
        )

    if quality == "calibrated":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(อยู่ในช่วง Calibration)"
        )

    if quality == "calibrated-low":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(อยู่ในช่วง Calibration "
            "/ ความน่าเชื่อถือต่ำกว่า)"
        )

    if quality == "extrapolated":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(นอกช่วง Calibration "
            "— ไม่ใช้คำนวณ GPS)"
        )

    if quality == "extrapolated-low":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(นอกช่วง Calibration "
            "/ ความน่าเชื่อถือต่ำกว่า "
            "— ไม่ใช้คำนวณ GPS)"
        )

    if quality == "unverified-range":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(ยังไม่ยืนยันช่วง Calibration "
            "— ไม่ใช้คำนวณ GPS)"
        )

    if quality == "unverified-range-low":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(ยังไม่ยืนยันช่วง Calibration "
            "/ ความน่าเชื่อถือต่ำกว่า "
            "— ไม่ใช้คำนวณ GPS)"
        )

    if quality == "unavailable":
        return (
            f"ระยะทาง: {distance:.1f} m "
            "(Calibration unavailable)"
        )

    return (
        f"ระยะทาง: {distance:.1f} m "
        f"(quality={quality})"
    )


def format_alert(
    d,
    *,
    bearing_calibrated: bool | None = None,
) -> str:
    """
    Create a safety-aware alert.

    GPS / Google Maps is included only when:
    - GPS exists
    - distance quality is calibrated/calibrated-low
    - bearing calibration is not explicitly invalid
    """

    quality = str(
        getattr(
            d,
            "distance_quality",
            "unavailable",
        )
        or "unavailable"
    )

    lines = [
        "🔥 แจ้งเตือนระบบตรวจจับไฟ/ควัน",

        (
            f"ประเภท: "
            f"{d.canonical_class} "
            f"({d.model_class})"
        ),

        (
            f"ความมั่นใจ AI: "
            f"{d.confidence:.1%}"
        ),

        (
            f"ทิศทาง: "
            f"{d.bearing_deg:.1f}° "
            f"({bearing_to_compass(d.bearing_deg)})"
        ),
    ]

    if bearing_calibrated is False:
        lines.append(
            "⚠️ ทิศทางยังไม่ผ่าน "
            "Site Bearing Calibration"
        )

    lines.append(
        _distance_text(d)
    )

    gps_allowed = (
        d.gps is not None
        and quality in GPS_ALLOWED_QUALITIES
        and bearing_calibrated is not False
    )

    if gps_allowed:
        lat, lon = d.gps

        lines.append(
            f"พิกัดประมาณ: "
            f"{lat:.6f}, {lon:.6f}"
        )

        lines.append(
            "https://www.google.com/maps/search/"
            f"?api=1&query={lat},{lon}"
        )

    elif d.gps is not None:
        # Defensive guard:
        # ต่อให้ Detection object มี GPS หลุดเข้ามา
        # Notify จะไม่ปล่อย Map link ถ้า quality/site ไม่ผ่าน
        lines.append(
            "⚠️ พิกัดถูกระงับโดย "
            "Location Safety Guard"
        )

    return "\n".join(
        lines
    )


# ============================================================
# Telegram transport
# ============================================================

def send_telegram(
    message: str,
    image_path: str | None = None,
) -> bool:

    if (
        not TELEGRAM_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        return False

    try:

        if image_path:

            with open(
                image_path,
                "rb",
            ) as image_file:

                response = requests.post(
                    (
                        "https://api.telegram.org/"
                        f"bot{TELEGRAM_TOKEN}/"
                        "sendPhoto"
                    ),
                    data={
                        "chat_id": (
                            TELEGRAM_CHAT_ID
                        ),
                        "caption": message,
                    },
                    files={
                        "photo": image_file,
                    },
                    timeout=20,
                )

        else:

            response = requests.post(
                (
                    "https://api.telegram.org/"
                    f"bot{TELEGRAM_TOKEN}/"
                    "sendMessage"
                ),
                data={
                    "chat_id": (
                        TELEGRAM_CHAT_ID
                    ),
                    "text": message,
                },
                timeout=10,
            )

        if response.status_code != 200:

            print(
                "⚠️ Telegram HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )

        return (
            response.status_code
            == 200
        )

    except Exception as exc:

        print(
            "⚠️ Telegram error: "
            f"{exc}"
        )

        return False


# ============================================================
# Background Telegram worker
# ============================================================

class TelegramWorker:

    def __init__(
        self,
        max_queue=5,
    ):
        self.enabled = bool(
            TELEGRAM_TOKEN
            and TELEGRAM_CHAT_ID
        )

        self.q = queue.Queue(
            maxsize=max_queue
        )

        self.thread = None

        if not self.enabled:

            print(
                "⚠️ Telegram disabled: "
                "token/chat id not set"
            )

            return

        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="telegram-worker",
        )

        self.thread.start()

        print(
            "✅ Telegram worker ready"
        )

    def submit(
        self,
        message,
        image_path=None,
        *,
        delete_after_send=False,
    ) -> bool:

        if not self.enabled:
            return False

        item = (
            message,
            image_path,
            delete_after_send,
        )

        try:

            self.q.put_nowait(
                item
            )

            return True

        except queue.Full:

            print(
                "⚠️ Telegram queue full; "
                "alert dropped"
            )

            # ป้องกัน spool file ค้าง
            # ถ้ายังไม่ได้เข้า queue
            if (
                delete_after_send
                and image_path
            ):
                try:
                    Path(
                        image_path
                    ).unlink(
                        missing_ok=True
                    )
                except OSError:
                    pass

            return False

    def _run(self):

        while True:

            (
                message,
                image_path,
                delete_after_send,
            ) = self.q.get()

            try:

                success = send_telegram(
                    message,
                    image_path,
                )

                if success:

                    print(
                        "✅ Telegram alert sent"
                    )

                    # ลบเฉพาะ temporary spool
                    # เมื่อส่งสำเร็จแล้ว
                    if (
                        delete_after_send
                        and image_path
                    ):
                        try:

                            Path(
                                image_path
                            ).unlink(
                                missing_ok=True
                            )

                        except OSError as exc:

                            print(
                                "⚠️ Cannot remove "
                                "alert spool: "
                                f"{exc}"
                            )

                else:

                    print(
                        "⚠️ Telegram alert "
                        "not delivered"
                    )

            finally:

                self.q.task_done()
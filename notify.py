import queue
import threading
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from geometry import bearing_to_compass

def format_alert(d) -> str:
    lines = ['🔥 แจ้งเตือนระบบตรวจจับไฟ/ควัน',
             f'ประเภท: {d.canonical_class} ({d.model_class})',
             f'ความมั่นใจ AI: {d.confidence:.1%}',
             f'ทิศทาง: {d.bearing_deg:.1f}° ({bearing_to_compass(d.bearing_deg)})']
    if d.distance_m is None:
        lines.append('ระยะทาง: ไม่สามารถคำนวณได้/ยังไม่ได้ Calibration')
    else:
        suffix = ' [ประมาณ]' if d.distance_quality != 'estimated' else ''
        lines.append(f'ระยะทาง: {d.distance_m:.1f} m{suffix}')
    if d.gps is not None:
        lat, lon = d.gps
        lines += [f'พิกัดประมาณ: {lat:.6f}, {lon:.6f}',
                  f'https://www.google.com/maps/search/?api=1&query={lat},{lon}']
    return '\n'.join(lines)

def send_telegram(message: str, image_path: str | None = None) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('⚠️ Telegram disabled: token/chat id not set')
        return False
    try:
        if image_path:
            with open(image_path, 'rb') as f:
                r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto',
                                  data={'chat_id': TELEGRAM_CHAT_ID, 'caption': message},
                                  files={'photo': f}, timeout=20)
        else:
            r = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
                              data={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10)
        if r.status_code != 200:
            print(f'⚠️ Telegram HTTP {r.status_code}: {r.text[:300]}')
        return r.status_code == 200
    except Exception as e:
        print(f'⚠️ Telegram error: {e}')
        return False

class TelegramWorker:
    def __init__(self, max_queue=5):
        self.q = queue.Queue(maxsize=max_queue)
        self.thread = threading.Thread(target=self._run, daemon=True, name='telegram-worker')
        self.thread.start()
    def submit(self, message, image_path=None):
        try:
            self.q.put_nowait((message, image_path))
        except queue.Full:
            print('⚠️ Telegram queue full; alert dropped')
    def _run(self):
        while True:
            item = self.q.get()
            try:
                send_telegram(*item)
            finally:
                self.q.task_done()

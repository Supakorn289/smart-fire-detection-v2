# Smart Fire Detection v2

ออกแบบสำหรับ i5-7500 / RAM 4GB / HDD 500GB / Linux headless + PTZ IP camera 355°.

## Flow
RTSP latest-frame -> PTZ move -> fresh frame -> stability check -> AI 3 frames -> consensus -> bearing/distance/GPS -> Telegram worker.

## มุม
- 1 = 0° N
- 2 = 45° NE
- 3 = 90° E
- 4 = 135° SE
- 5 = 177.5°
- 6 = 315° NW (physical pan -45°)
- 7 = 270° W (physical pan -90°)
- 8 = 225° SW (physical pan -135°)
- 9 = 182.5° (physical pan -177.5°)

แยก physical pan ออกจาก compass bearing เพื่อให้ทั้งเวลาเคลื่อนมอเตอร์และทิศบนแผนที่ถูกต้อง.

## Install
```bash
py -3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

ตั้ง secret ผ่าน environment variable; ห้าม hard-code token/password ใน source.

```bash
export CAMERA_PWD='...'
export TELEGRAM_TOKEN='...'
export TELEGRAM_CHAT_ID='...'
```

วางโมเดลที่ `models/fire.pt` แล้วทำตาม `TESTING.md` ก่อนรัน `main.py`.

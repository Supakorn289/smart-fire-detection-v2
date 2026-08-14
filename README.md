Smart Fire Detection v2
ระบบตรวจจับไฟและควันด้วย AI สำหรับกล้อง IP Camera แบบ PTZ 355°  
ออกแบบให้ทำงานแบบ Headless บนเครื่องสเปกจำกัด เช่น Intel Core i5-7500 / RAM 4 GB / HDD 500 GB
> เอกสารนี้เป็นจุดเริ่มต้นสำหรับผู้พัฒนาที่เพิ่งเปิดโปรเจกต์ครั้งแรก  
> ถ้าต้องติดตั้งหรือแก้โค้ด ให้ไปต่อที่ [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md)  
> ถ้าจะทดสอบระบบ ให้ทำตาม [`TESTING.md`](TESTING.md) ตามลำดับ
---
1. ระบบนี้ทำอะไร
ระบบจะให้กล้อง PTZ กวาดตรวจตาม Preset ที่กำหนด เมื่อกล้องหยุดนิ่งแล้วจึงอ่านเฟรมใหม่จาก RTSP และส่งภาพเข้า AI
Flow หลัก:
```text
RTSP Camera
    ↓
Latest Frame
    ↓
PTZ Move
    ↓
Wait for movement
    ↓
Fresh Frame
    ↓
Image Stability Check
    ↓
AI Detection 3 Frames
    ↓
2/3 Frame Consensus
    ↓
Bounding Box
    ├── X → Bearing
    └── Y → Distance
              ↓
        Estimated GPS
              ↓
       Telegram Alert
```
แนวคิดสำคัญคือ AI จะไม่ควรใช้ภาพที่ยังเกิดจากช่วงกล้องกำลังหมุน และต้องลดปัญหา RTSP stale frame ให้มากที่สุด
---
2. โครงสร้างโปรเจกต์
```text
smart-fire-detection-v2/
├── README.md
├── DEVELOPER_GUIDE.md
├── TESTING.md
│
├── main.py
├── config.py
├── camera.py
├── ptz.py
├── detection.py
├── geometry.py
├── calibration.py
├── notify.py
├── overlay.py
├── app.py
│
├── calibrate_bearing.py
├── calibrate_distance.py
├── verify_bearing.py
├── verify_distance.py
│
├── inspect_model.py
├── export_openvino.py
├── test_camera.py
├── test_ptz.py
├── test_ptz_frame_sync.py
├── test_telegram.py
│
├── requirements.txt
├── .env.example
│
├── models/
├── calibration/
├── static/
└── tests/
```
---
3. หน้าที่ของไฟล์หลัก
ไฟล์	หน้าที่
`main.py`	Orchestrator หลักของระบบและ Sweep Loop
`config.py`	Configuration ทั้งหมดจาก Environment Variables
`camera.py`	RTSP decoding thread และ Latest Frame
`ptz.py`	ควบคุม Preset/PTZ และเวลารอการหมุน
`detection.py`	โหลด YOLO, map class, Detection, Consensus
`geometry.py`	Pixel → Bearing และ Bearing+Distance → GPS
`calibration.py`	บันทึก/โหลด Distance และ Site Calibration
`notify.py`	Telegram API และ background worker
`overlay.py`	วาด Bounding Box และสถานะบนภาพ
`app.py`	Flask Dashboard
`calibrate_bearing.py`	ตั้งค่า North Offset
`calibrate_distance.py`	สร้าง Distance Calibration
`verify_distance.py`	ตรวจความแม่นของ Distance Calibration
`verify_bearing.py`	ตรวจความแม่นของ Bearing (Optional ก่อน runtime)
---
4. Preset และ Bearing
ระบบแยก Physical Pan ออกจาก Compass Bearing
Preset	Physical Pan	Compass Bearing
1	0°	0° N
2	+45°	45° NE
3	+90°	90° E
4	+135°	135° SE
5	+177.5°	177.5°
6	-45°	315° NW
7	-90°	270° W
8	-135°	225° SW
9	-177.5°	182.5°
Sweep Sequence:
```text
1 → 2 → 3 → 4 → 5 → 4 → 3 → 2 → 1
→ 6 → 7 → 8 → 9 → 8 → 7 → 6 → 1
```
อย่าเปลี่ยน `PRESET_PAN_DEG` และ `PRESET_BEARING_DEG` ให้เป็นค่าเดียวกันโดยไม่เข้าใจความแตกต่างของสองระบบพิกัดนี้
---
5. Quick Start
Windows
```bat
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
Linux
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
ตรวจสอบ:
```bash
python --version
```
โปรเจกต์นี้แนะนำให้ใช้ Python 3.12 เพื่อให้ environment ตรงกับชุดที่ใช้พัฒนาและทดสอบ
---
6. สิ่งที่ต้องมีเพิ่มเติม
ก่อนใช้งานจริงต้องเตรียม:
กล้อง IP Camera ที่เข้าถึง RTSP ได้
PTZ Preset 1-9 ที่ตั้งไว้ตรงกับระบบ
โมเดล AI ที่ `models/fire.pt`
Environment Variables ของกล้อง
Camera GPS
Distance Calibration
Bearing/Site Calibration
Telegram Token/Chat ID ถ้าต้องการแจ้งเตือน
โมเดลต้องมี class ที่ระบบรู้จัก เช่น:
```text
Fire
Smoke
```
ระบบจะ normalize ชื่อ class และ map ไปเป็น `fire` / `smoke`
---
7. ก่อนรันระบบจริง
ห้ามเริ่มจาก `python main.py` ทันทีบนเครื่องหรือสถานที่ติดตั้งใหม่
ให้ทำตาม:
```text
Install
  ↓
Configure Environment
  ↓
Unit Tests
  ↓
Inspect Model
  ↓
Camera Test
  ↓
PTZ Test
  ↓
PTZ + Frame Sync Test
  ↓
Bearing Calibration
  ↓
Distance Calibration
  ↓
Distance Verification
  ↓
Telegram Test
  ↓
main.py
```
รายละเอียดทั้งหมดอยู่ใน `TESTING.md`
---
8. รันระบบจริง
Terminal 1:
```bash
python main.py
```
Terminal 2:
```bash
python app.py
```
Dashboard:
```text
http://<SERVER-IP>:5000
```
`main.py` จะเขียนข้อมูล runtime ไปที่:
```text
static/latest_frame.jpg
static/latest_alert.jpg
static/status.json
```
---
9. ข้อควรจำ
ย้ายตำแหน่งกล้อง → Calibration เดิมอาจใช้ไม่ได้
เปลี่ยน Tilt/ความสูง/มุมติดตั้ง → ควรทำ Distance Calibration ใหม่
เปลี่ยน HFOV/Resolution → ต้องตรวจ Calibration ใหม่
เปลี่ยน Preset → ต้องตรวจทิศทางใหม่
`Smoke` ไม่มีจุดสัมผัสพื้นที่ชัดเจน ดังนั้น Distance ของ Smoke เป็นค่าประมาณที่มีความน่าเชื่อถือต่ำกว่า Fire
อย่า Hard-code Token หรือ Password ลง Source Code
อย่าใช้ผล GPS เป็นค่าความแม่นยำระดับสำรวจ เพราะตำแหน่งเป้าหมายเป็นค่าประมาณจาก Camera GPS + Bearing + Distance
ก่อนแก้ `camera.py`, `ptz.py`, `geometry.py` หรือ `calibration.py` ควรรัน Unit/Integration Test ซ้ำทุกครั้ง
---
10. เอกสารสำหรับผู้พัฒนา
อ่านตามลำดับ:
`README.md`
`DEVELOPER_GUIDE.md`
`TESTING.md`
ถ้าเพิ่งเข้าร่วมโปรเจกต์ ให้เริ่มที่ `DEVELOPER_GUIDE.md`
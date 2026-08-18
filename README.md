# Smart Fire Detection v2

ระบบตรวจจับ **Fire / Smoke** ด้วย AI จากกล้อง IP PTZ พร้อมระบบหมุนตรวจสอบหลายทิศทาง, ยืนยันผลหลายเฟรม, คำนวณ Bearing/Distance, ประเมินตำแหน่ง, แจ้งเตือน และแสดงผลผ่าน Web Dashboard

---

## 1. ภาพรวม

Smart Fire Detection v2 ออกแบบให้ทำงานแบบ PTZ Step Scan

```text
PTZ Move
   ↓
Camera Stop
   ↓
Fresh Frame
   ↓
Stable Frame
   ↓
AI Detection
   ↓
Multi-frame Confirmation
   ↓
Bearing
   ↓
Distance
   ↓
Estimated Location
   ↓
Alert / Dashboard / Log
```

ระบบไม่ได้ประมวลผลวิดีโอแบบ Continuous FPS เป็นหลัก แต่ทำงานในลักษณะ

```text
หมุน → หยุด → ตรวจ → คำนวณ → แจ้งเตือน → หมุนต่อ
```

แนวทางนี้ช่วยลดปัญหาการนำภาพเก่าหรือภาพระหว่างกล้องกำลังเคลื่อนที่ไปประมวลผล

---

## 2. หลักสำคัญก่อนใช้งาน

เมื่อได้รับโปรเจกต์นี้มาใหม่

**ห้ามเริ่มด้วย**

```bash
python main.py
```

ทันที

ให้ตรวจระบบตามลำดับ

```text
Environment
    ↓
Unit Tests
    ↓
Offline Preflight
    ↓
AI Model / Benchmark
    ↓
Camera
    ↓
PTZ
    ↓
PTZ / Frame Sync
    ↓
AI Integration
    ↓
Camera Intrinsics
    ↓
Bearing Calibration
    ↓
Distance Calibration
    ↓
Verification
    ↓
Full Preflight
    ↓
Full Sweep
    ↓
Runtime
    ↓
Production Services
```

ถ้าขั้นใด `FAIL` หรือเกิด Error ให้หยุดแก้ขั้นนั้นก่อน

---

## 3. ความสามารถหลัก

ระบบรองรับ

- IP Camera ผ่าน RTSP
- PTZ Preset 1–9
- Step Scan
- Fresh-frame protection
- Stable-frame verification
- YOLO Fire/Smoke detection
- Multi-frame confirmation
- IoU consensus
- Bearing estimation
- Perspective distance estimation
- Site GPS estimationเมื่อ Calibration พร้อม
- Local alert
- Telegram notification
- Alert deduplication
- Dashboard
- Runtime status JSON
- PyTorch inference
- OpenVINO inference
- AI benchmark
- Camera calibration
- Bearing verification
- Distance verification
- systemd Production deployment

---

## 4. PTZ Geometry

Preset หลัก

```text
Preset 1 =    0.0°
Preset 2 =  +45.0°
Preset 3 =  +90.0°
Preset 4 = +135.0°
Preset 5 = +177.5°

Preset 6 =  -45.0°
Preset 7 =  -90.0°
Preset 8 = -135.0°
Preset 9 = -177.5°
```

Compass convention

```text
0°   = North
90°  = East
180° = South
270° = West
```

Sweep sequence

```text
1
→ 2
→ 3
→ 4
→ 5
→ 4
→ 3
→ 2
→ 1
→ 6
→ 7
→ 8
→ 9
→ 8
→ 7
→ 6
→ 1
```

---

## 5. Repository Structure

```text
smart-fire-detection-v2/
│
├── README.md
├── DEVELOPER_GUIDE.md
├── TESTING.md
├── PRODUCTION_DEPLOYMENT_GUIDE.md
│
├── main.py
├── app.py
├── config.py
├── camera.py
├── ptz.py
├── detection.py
├── geometry.py
├── calibration.py
├── notify.py
├── overlay.py
│
├── preflight.py
├── benchmark_inference.py
├── export_openvino.py
├── inspect_model.py
│
├── calibrate_intrinsics.py
├── calibrate_bearing.py
├── calibrate_distance.py
│
├── verify_bearing.py
├── verify_distance.py
│
├── test_camera.py
├── test_ptz.py
├── test_ptz_frame_sync.py
├── test_ptz_repeatability_v1.py
├── test_detection_live.py
├── test_detection_stability.py
├── test_full_sweep.py
├── test_telegram.py
│
├── calibrate_bearing_v2.py
├── refine_overlap_marks_v3.py
├── fit_preset_geometry_v3.py
├── fit_preset_geometry_v3_1.py
│
├── collect_hard_negatives.py
├── review_hard_negatives.py
├── prepare_hard_negative_addon.py
│
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
│
├── deploy/
│   ├── install.sh
│   ├── production.env.example
│   ├── smart-fire-detection.service
│   └── smart-fire-dashboard.service
│
├── models/
│   └── .gitkeep
│
├── calibration/
│   └── .gitkeep
│
├── static/
│   └── .gitkeep
│
└── tests/
    ├── test_calibration.py
    ├── test_calibration_range.py
    ├── test_detection_utils.py
    └── test_geometry.py
```

Model, Calibration และ Runtime outputs บางรายการไม่ได้อยู่ใน Git และจะถูกสร้างหรือนำเข้าภายหลัง

---

# 6. Requirements

Project baseline

```text
Python 3.12.x
```

Development รองรับ Windows/Linux

Production workflow ออกแบบสำหรับ

```text
Debian Linux
systemd
Python 3.12
CPU inference
```

---

# 7. Development Setup

## 7.1 สร้าง Virtual Environment

Windows

```bat
python -m venv venv
venv\Scripts\activate
```

Linux

```bash
python3.12 -m venv venv
source venv/bin/activate
```

ตรวจ

```bash
python --version
```

ควรเป็น

```text
Python 3.12.x
```

---

## 7.2 ติดตั้ง Development Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` โหลด Runtime dependencies จาก `requirements.txt` และเพิ่มเครื่องมือสำหรับ Development/Test

Production ไม่จำเป็นต้องติดตั้ง `requirements-dev.txt`

---

# 8. AI Model

นำ PyTorch model ไปไว้ที่

```text
models/fire.pt
```

Model ไม่ควรถูก Commit เข้า Git หาก Repository กำหนดให้ Ignore Model binaries

ตรวจ Model

```bash
python inspect_model.py
```

ระบบต้องสามารถ map class ที่ต้องการไปเป็น

```text
fire
smoke
```

---

# 9. Unit Tests

รัน

```bash
python -m pytest -q
```

`pytest.ini` จำกัด Test Discovery ไว้ใน

```text
tests/
```

เพื่อไม่ให้ pytest รัน Hardware Test ที่อยู่ Root ของ Project

เมื่อ Test ใด Fail ให้แก้ก่อนดำเนินขั้น Hardware

---

# 10. Offline Preflight

เมื่อยังไม่มีกล้องหรือ Site จริง

```bash
python preflight.py --offline
```

เป้าหมาย

```text
FAIL : 0
```

รายการ Hardware/Site สามารถเป็น `SKIP` ได้ใน Offline Mode

Offline Preflight ไม่ได้หมายความว่า Production พร้อมใช้งาน

---

# 11. Environment Variables

`config.py` **ไม่ได้โหลด `.env` อัตโนมัติ**

Environment ต้องถูกส่งผ่าน

```text
Shell
IDE
systemd
Production EnvironmentFile
```

`.env.example` เป็น Template เท่านั้น

ห้ามใส่

```text
Camera Password จริง
Telegram Token จริง
Telegram Chat ID จริง
Site GPS จริง
```

แล้ว Commit เข้า Git

ตัวอย่าง Site ที่ยังไม่ตั้ง

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

`nan` ใช้เพื่อให้ Development/Offline tools สามารถเริ่มทำงานได้

Production Ready ต้องใช้ Site coordinate จริง

---

# 12. AI Benchmark

PyTorch

```bash
python benchmark_inference.py --backend pt --warmup 10 --runs 200
```

OpenVINO

```bash
python benchmark_inference.py --backend openvino --device intel:cpu --warmup 10 --runs 200
```

ผลถูกบันทึกใน

```text
static/benchmark_runs/
```

ควรเปรียบเทียบอย่างน้อย

```text
Mean latency
Median latency
P95 latency
Maximum latency
Standard deviation
Approx FPS
Peak RAM
CPU usage
Warm-up
```

ผล Benchmark บน Development Computer **ไม่ใช่ Production Benchmark**

Production Server ต้อง Benchmark ใหม่

---

# 13. OpenVINO Export

Export

```bash
python export_openvino.py
```

Input

```text
models/fire.pt
```

Output

```text
models/fire_openvino_model/
```

ให้ Benchmark PyTorch และ OpenVINO บน Hardware จริงก่อนเลือก Production Backend

---

# 14. Hardware Test

เมื่อ Camera Environment พร้อม

## Camera

```bash
python test_camera.py
```

## PTZ

```bash
python test_ptz.py
```

## PTZ + Fresh/Stable Frame

```bash
python test_ptz_frame_sync.py
```

ต้องผ่านตามลำดับ

```text
RTSP
 ↓
PTZ
 ↓
Fresh Frame
 ↓
Stable Frame
```

---

# 15. AI Integration Test

```bash
python test_detection_live.py
```

ตรวจ Stability เพิ่มเติม

```bash
python test_detection_stability.py
```

การทดสอบ Fire/Smoke ควรใช้

```text
Public datasets
Existing test images
Existing videos
Recorded media
Screen playback
```

ไม่จำเป็นต้องสร้างเหตุการณ์อันตรายจริงเพื่อทดสอบระบบ

---

# 16. Camera Intrinsics

ทำใหม่เมื่อเปลี่ยน

```text
Camera
Lens
Optical zoom
Digital crop
Resolution
Image pipeline
```

สร้าง Checkerboard

```bash
python calibrate_intrinsics.py generate
```

Capture

```bash
python calibrate_intrinsics.py capture --count 25 --reset
```

Fit

```bash
python calibrate_intrinsics.py fit
```

Output

```text
calibration/camera_intrinsics.json
```

Runtime ต้องใช้ `HFOV_DEG` ที่ตรงกับ Calibration

---

# 17. Bearing Calibration

เมื่อติด Camera ใน Orientation จริง

```bash
python calibrate_bearing.py
```

Output

```text
calibration/site.json
```

หากย้ายกล้องหรือเปลี่ยน Orientation ต้อง Calibration ใหม่

---

# 18. Distance Calibration

```bash
python calibrate_distance.py
```

ขั้นต่ำ

```text
3 points
```

แนะนำ

```text
5–8 points
```

ใช้ Reference object ธรรมดาที่เห็นจุดสัมผัสพื้นชัดเจน

ใช้ค่า Y ของ

```text
จุดล่างสุดที่วัตถุสัมผัสพื้น
```

Output

```text
calibration/distance_global.json
```

---

# 19. Verification

Distance

```bash
python verify_distance.py
```

Bearing

```bash
python verify_bearing.py
```

Verification ต้องใช้ Test points ที่แยกจาก Calibration points เมื่อเป็นไปได้

Calibration มีหน้าที่สร้าง Model

Verification มีหน้าที่วัดว่า Model ที่สร้างไว้ทำงานแม่นเพียงใด

---

# 20. Full Preflight

เมื่อ Camera, Environment และ Calibration พร้อม

```bash
python preflight.py
```

เป้าหมาย

```text
FAIL : 0
```

การผ่าน Full Preflight บน Development Computer ยังไม่เท่ากับ Production Ready

---

# 21. Full Sweep

```bash
python test_full_sweep.py --cycles 1
```

ตรวจ Pipeline

```text
PTZ
 ↓
Fresh Frame
 ↓
Stable Frame
 ↓
AI
 ↓
Multi-frame Detection
 ↓
IoU Consensus
 ↓
Bearing
 ↓
Distance
 ↓
Output
```

Output อยู่ใน

```text
static/sweep_runs/
```

---

# 22. Runtime บน Development Computer

เมื่อ Validation ผ่านแล้ว

```bash
python main.py
```

หยุดด้วย

```text
Ctrl+C
```

---

# 23. Dashboard บน Development Computer

เปิดอีก Terminal

```bash
python app.py
```

เปิด Browser

```text
http://127.0.0.1:5000
```

Dashboard แสดง

```text
Latest frame
Last alert
Status
```

API

```text
/api/status
```

---

# 24. Production Architecture

Production ใช้ 2 systemd services

```text
systemd
│
├── smart-fire-detection.service
│       └── main.py
│
└── smart-fire-dashboard.service
        └── app.py
```

Detection Service ทำหน้าที่ Runtime หลัก

Dashboard Service ทำหน้าที่ Web UI เท่านั้น

ทั้งสองใช้

```text
/etc/smart-fire-detection/production.env
```

---

# 25. Production Paths

Project

```text
/opt/smart-fire-detection-v2
```

Environment

```text
/etc/smart-fire-detection/production.env
```

Detection service

```text
/etc/systemd/system/smart-fire-detection.service
```

Dashboard service

```text
/etc/systemd/system/smart-fire-dashboard.service
```

---

# 26. Production Installer

บน Debian

```bash
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Installer มีหน้าที่เตรียม Runtime แต่จะไม่ Start/Enable Production Services โดยอัตโนมัติ

ต้องทำ Production Validation ก่อน

อ่านขั้นตอนทั้งหมดที่

```text
PRODUCTION_DEPLOYMENT_GUIDE.md
```

---

# 27. Runtime Outputs

ระบบอาจสร้าง

```text
static/
├── latest_frame.jpg
├── latest_alert.jpg
├── status.json
├── alert_spool/
├── benchmark_runs/
├── detection_runs/
└── sweep_runs/
```

---

# 28. Telegram

ถ้าใช้ Telegram ให้กำหนด

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

แล้วทดสอบ

```bash
python test_telegram.py
```

หากไม่กำหนด Telegram ระบบยังสามารถทำ Local Alert ได้ตาม Runtime configuration

---

# 29. Alert Deduplication

Runtime ใช้ Event-based deduplication เพื่อลดการแจ้งเตือนซ้ำ

ใช้ข้อมูล เช่น

```text
Class
Preset
Bounding-box overlap
Cooldown
```

ในการตัดสินใจว่า Detection เป็น Event ใหม่หรือ Event เดิม

---

# 30. GPS Safety

GPS output ไม่ควรถูกเชื่อถือก่อนมี

```text
Valid Site Coordinate
Bearing Calibration
Distance Calibration
Validated distance range
```

หาก Site Bearing Calibration ยังไม่มี Runtime จะต้องไม่ถือ Bearing ที่ได้ว่าเป็น True-North calibrated result

---

# 31. Advanced Geometry Tools

ไฟล์

```text
calibrate_bearing_v2.py
refine_overlap_marks_v3.py
fit_preset_geometry_v3.py
fit_preset_geometry_v3_1.py
```

เป็นเครื่องมือสำหรับการทดลองและวิเคราะห์ Preset Geometry ขั้นสูง

`calibrate_bearing_v2.py` สร้าง Relative Geometry

ผลเพียงอย่างเดียว **ไม่ใช่ True North Calibration**

Production workflow มาตรฐานยังต้องมี

```text
calibrate_bearing.py
```

เพื่อผูกระบบเข้ากับทิศจริงของ Site

---

# 32. Hard Negative Tools

Workflow สำหรับปรับปรุง Dataset

```text
collect_hard_negatives.py
        ↓
review_hard_negatives.py
        ↓
prepare_hard_negative_addon.py
```

ห้ามนำ Candidate ทั้งหมดเข้า Negative Dataset อัตโนมัติ

ต้อง Review ด้วยคนก่อนและเลือกเฉพาะภาพที่ยืนยันว่าไม่มี Fire/Smoke จริง

---

# 33. Security Rules

ห้าม Commit

```text
.env
production.env
Camera credentials
Telegram token
Telegram Chat ID
Site GPS จริง
Private keys
Production Calibration ที่มีข้อมูลอ่อนไหว หากนโยบายโครงการไม่อนุญาต
```

Dashboard ปัจจุบันไม่มี Authentication layer

ดังนั้นไม่ควรเปิด Port 5000 ออก Public Internet โดยตรง

---

# 34. Documentation

Repository มีเอกสารหลัก 4 ไฟล์

```text
README.md
= ภาพรวมและ Quick Start

DEVELOPER_GUIDE.md
= Architecture และคู่มือสำหรับผู้พัฒนา

TESTING.md
= Test Procedure และ Release Gate

PRODUCTION_DEPLOYMENT_GUIDE.md
= Deployment/Operations บน Production Server
```

---

# 35. Production Ready Definition

ระบบไม่ควรถูกเรียกว่า `Production Ready` จนกว่าจะผ่าน

```text
Development Tests
        ↓
Production Environment
        ↓
Production Benchmark
        ↓
Camera / PTZ / Frame Sync
        ↓
Intrinsics Validation
        ↓
Site Calibration
        ↓
Bearing Verification
        ↓
Distance Verification
        ↓
Full Preflight
        ↓
Full Sweep
        ↓
Telegram Test (ถ้าใช้)
        ↓
Detection Service
        ↓
Dashboard Service
        ↓
Reboot Test
        ↓
Production Ready
```

---

## Final Principle

```text
อย่าเดา
   ↓
ตรวจ
   ↓
วัด
   ↓
Calibration
   ↓
Verification
   ↓
Full-system Test
   ↓
Production
```

เมื่อพบปัญหา ให้ย้อนกลับไปยัง Layer ก่อนหน้าและตรวจทีละส่วน
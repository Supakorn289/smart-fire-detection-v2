# Smart Fire Detection v2

# Production Deployment Guide

คู่มือการติดตั้ง, Commissioning, Calibration, Validation, เปิด Service, ดูแลระบบ และ Update Smart Fire Detection v2 บน Production Server

---

# 1. Production Architecture

Production ใช้สอง systemd services

```text
                    systemd
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
smart-fire-detection        smart-fire-dashboard
       .service                    .service
          │                         │
          ▼                         ▼
        main.py               waitress-serve
          │                         │
          ▼                         ▼
        static/                   app:app
          │                         │
          └───────────────┬─────────┘
                          ▼
                    Web Dashboard
```

## Detection Service

รับผิดชอบ

```text
Camera / RTSP
PTZ
Fresh Frame
Stable Frame
AI Detection
Multi-frame Consensus
Bearing
Distance
GPS
Alert
Telegram
Runtime Outputs
```

## Dashboard Service

รับผิดชอบ

```text
Web Dashboard
Latest Frame
Latest Alert
Runtime Status
/api/status
Static File Display
```

Dashboard ไม่ควบคุม Camera, PTZ หรือ AI โดยตรง

---

# 2. Production Workflow

```text
Development Validation
        ↓
Copy / Clone Project
        ↓
Production OS / Python
        ↓
install.sh
        ↓
production.env
        ↓
Offline Preflight
        ↓
Production Benchmark
        ↓
Select AI Backend
        ↓
Camera Test
        ↓
PTZ Test
        ↓
Frame Sync
        ↓
Intrinsics Validation
        ↓
Site Coordinates
        ↓
Bearing Calibration
        ↓
Distance Calibration
        ↓
Bearing Verification
        ↓
Distance Verification
        ↓
Telegram Test
        ↓
Full Preflight
        ↓
Full Sweep
        ↓
Detection Service
        ↓
Dashboard Service
        ↓
Service Validation
        ↓
Reboot Test
        ↓
Production Ready
```

---

# 3. สิ่งที่ห้ามทำ

ห้ามเริ่ม Production ด้วย

```bash
python main.py
```

ทันที

ห้าม Enable systemd ก่อน Validation

ห้ามใช้ Calibration จาก Site เก่าโดยไม่ตรวจสอบ

ห้ามใช้ Development Benchmark แทน Production Benchmark

ห้าม Commit Production secrets

ห้ามเปิด Dashboard Port 5000 สู่ Public Internet โดยตรง

ห้ามรัน `main.py` ซ้อนกับ Detection Service ที่กำลัง Active

---

# 4. Standard Production Paths

Project

```text
/opt/smart-fire-detection-v2
```

Virtual Environment

```text
/opt/smart-fire-detection-v2/venv
```

Production Environment

```text
/etc/smart-fire-detection/production.env
```

Detection systemd unit

```text
/etc/systemd/system/smart-fire-detection.service
```

Dashboard systemd unit

```text
/etc/systemd/system/smart-fire-dashboard.service
```

---

# 5. Production Runtime User

Production Runtime ใช้

```text
User  : smartfire
Group : smartfire
```

ทั้ง Detection และ Dashboard ต้องรันด้วย Account นี้ ไม่ใช่ root

Root ใช้เฉพาะงาน Administration เช่น

```text
Installation
Environment configuration
Service installation
Permissions
System maintenance
```

---

# 6. Production Requirements

Production workflow ปัจจุบันต้องมี

```text
Debian Linux
systemd
Python 3.12.x
Network access to Camera
Storage สำหรับ Runtime outputs
AI model
```

ระหว่างติดตั้ง Packages อาจต้องใช้ Internet access

---

# 7. ตรวจ Production Server

ตรวจ OS

```bash
cat /etc/os-release
```

ตรวจ Kernel

```bash
uname -r
```

ตรวจ Architecture

```bash
uname -m
```

ตรวจ CPU

```bash
lscpu
```

ตรวจ RAM

```bash
free -h
```

ตรวจ Disk

```bash
df -h
```

ตรวจ Network

```bash
ip addr
```

---

# 8. Python Requirement

ตรวจ

```bash
python3.12 --version
```

ต้องเป็น

```text
Python 3.12.x
```

หากไม่มี Python 3.12

```text
STOP
```

อย่าสร้าง Production venv ด้วย Python version อื่นโดยไม่ได้ Validate Dependencies ใหม่

---

# 9. นำ Project ขึ้น Server

Project ต้องอยู่ที่

```text
/opt/smart-fire-detection-v2
```

ตรวจ

```bash
cd /opt/smart-fire-detection-v2
ls
```

ควรมีอย่างน้อย

```text
main.py
app.py
config.py
camera.py
ptz.py
detection.py
geometry.py
calibration.py
notify.py
overlay.py

requirements.txt
preflight.py
benchmark_inference.py

deploy/
models/
calibration/
static/
```

---

# 10. AI Model

PyTorch model

```text
/opt/smart-fire-detection-v2/models/fire.pt
```

ถ้าใช้ OpenVINO

```text
/opt/smart-fire-detection-v2/models/fire_openvino_model/
```

Model binaries อาจไม่ได้ถูกเก็บใน Git

จึงต้องนำ Model ที่ถูกต้องขึ้น Production Server แยกต่างหาก

ควรบันทึก Version หรือ Hash ของ Model ที่ใช้งานจริงไว้ในเอกสารการทดสอบ

---

# 11. ตรวจ Deployment Files

```bash
ls -lah deploy/
```

ต้องมี

```text
install.sh
production.env.example
smart-fire-detection.service
smart-fire-dashboard.service
```

---

# 12. Production Environment Template

Template

```text
deploy/production.env.example
```

ระหว่างยังไม่ตั้ง Site ใช้

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

ห้ามใช้

```text
CAMERA_LAT=CHANGE_ME
CAMERA_LON=CHANGE_ME
```

เพราะ `config.py` อ่านสองค่านี้เป็นตัวเลข

---

# 13. รัน Installer

เข้า Project

```bash
cd /opt/smart-fire-detection-v2
```

อนุญาตให้ Script ทำงาน

```bash
chmod +x deploy/install.sh
```

ติดตั้ง

```bash
sudo ./deploy/install.sh
```

Installer มีหน้าที่เตรียม

```text
Debian validation
Python 3.12 validation
smartfire user/group
Runtime directories
Python venv
CPU PyTorch
Project dependencies
OpenVINO
Waitress
Production environment
Detection service
Dashboard service
Permissions
Model checks
Calibration checks
```

Installer ตั้งใจ

```text
ไม่ Start main.py
ไม่ Start Dashboard
ไม่ Enable Services
ไม่ทำ Calibration
ไม่เขียนทับ production.env เดิม
```

หลัง Installer จบ

**ยังไม่เปิด Production Services**

---

# 14. Production Environment

ไฟล์จริง

```text
/etc/smart-fire-detection/production.env
```

แก้ด้วย

```bash
sudo nano /etc/smart-fire-detection/production.env
```

ตรวจค่าต่อไปนี้

```text
CAMERA_IP
CAMERA_PORT
CAMERA_USER
CAMERA_PWD

RTSP_PORT
RTSP_PATH
CAMERA_ID

FRAME_WIDTH
FRAME_HEIGHT

HFOV_DEG

DEG_PER_SEC
PTZ_BUFFER_SEC
INITIAL_PRESET_WAIT_SEC

STABLE_DIFF_THRESHOLD
STABLE_REQUIRED_PAIRS
STABLE_TIMEOUT_SEC
POST_MOVE_FRESH_FRAMES

MODEL_BACKEND
MODEL_PATH_PT
MODEL_PATH_OPENVINO
INFERENCE_DEVICE
IMGSZ

FIRE_THRESHOLD
SMOKE_THRESHOLD

FRAMES_PER_SCAN
MIN_CONFIRM_FRAMES
FRAME_SAMPLE_GAP_SEC
CONSENSUS_IOU_THRESHOLD

STARTUP_WARMUP_RUNS

CALIBRATION_DIR
MIN_VALID_DISTANCE_M
MAX_VALID_DISTANCE_M

CAMERA_LAT
CAMERA_LON

TELEGRAM_TOKEN
TELEGRAM_CHAT_ID

ALERT_COOLDOWN_SEC
ALERT_DEDUP_IOU_THRESHOLD

STATIC_DIR
DASHBOARD_WRITE_INTERVAL_SEC

HEADLESS_MODE
```

---

# 15. CAMERA_ID

`CAMERA_ID` เป็น Optional

ถ้าปล่อยว่าง

```env
CAMERA_ID=
```

ระบบจะประกอบ RTSP URL จาก

```text
CAMERA_USER
CAMERA_PWD
CAMERA_IP
RTSP_PORT
RTSP_PATH
```

ถ้ากล้องใช้ RTSP URL รูปแบบพิเศษ สามารถกำหนด `CAMERA_ID` เองได้

ห้าม Commit RTSP URL ที่มี Username/Password จริงเข้า Repository

---

# 16. Multi-frame Consensus

Production Environment ต้องมี

```env
CONSENSUS_IOU_THRESHOLD=0.30
```

ค่านี้ใช้กำหนด IoU ขั้นต่ำสำหรับการจับคู่ Detection ของ Object เดียวกันระหว่างหลาย Frame

Runtime baseline

```text
FRAMES_PER_SCAN=3
MIN_CONFIRM_FRAMES=2
CONSENSUS_IOU_THRESHOLD=0.30
```

อย่าปรับค่าเหล่านี้พร้อมกันหลายตัวโดยไม่มีผลทดสอบรองรับ

---

# 17. Environment Security

Production environment ต้องไม่อยู่ใน Git

ตรวจ

```bash
sudo ls -l /etc/smart-fire-detection/production.env
```

ควรเป็นประมาณ

```text
root root
0600
```

ห้ามนำ Output ที่มี Password/Token ไปใส่

```text
Git
Screenshot
Issue
Documentation
Chat
Public Log
```

หลีกเลี่ยงการใช้

```bash
cat /etc/smart-fire-detection/production.env
```

ใน Terminal ที่กำลัง Record หรือ Capture

---

# 18. Camera Credentials

ต้องแก้

```text
CAMERA_IP
CAMERA_USER
CAMERA_PWD
```

จาก Placeholder เป็นค่าจริงใน

```text
/etc/smart-fire-detection/production.env
```

ห้ามใส่ Credential จริงใน

```text
deploy/production.env.example
```

แล้ว Commit

---

# 19. Site Coordinates ระหว่าง Setup

ในระหว่างที่ Site GPS ยังไม่พร้อมสามารถใช้

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

เพื่อทำ

```text
Installation
Offline Preflight
AI Benchmark
Camera Test
PTZ Test
Frame Sync
```

บางส่วนได้

แต่ก่อน Production Ready ต้องเปลี่ยนเป็น Coordinate ของ Camera Site จริง

---

# 20. Manual Commissioning Environment

Production Environment ถูกออกแบบให้ systemd โหลดโดยตรง

ดังนั้นไม่ควรใช้

```bash
source /etc/smart-fire-detection/production.env
```

เป็นวิธีหลัก เพราะ Bash และ systemd EnvironmentFile ไม่ได้ตีความค่าเหมือนกันทุกกรณี

การทดสอบ Production Environment แบบ Manual ควรใช้ transient systemd service

รูปแบบพื้นฐาน

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    <COMMAND>
```

ตัวอย่าง Offline Preflight

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/preflight.py \
    --offline
```

ข้อดีคือ Environment ถูกอ่านด้วย systemd แบบเดียวกับ Production Service

---

# 21. Offline Preflight บน Production

รัน

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/preflight.py \
    --offline
```

เป้าหมาย

```text
FAIL : 0
```

Calibration/Camera ที่ยังไม่พร้อมสามารถเป็น `SKIP` ตาม Offline semantics

ถ้า Software-critical item FAIL ให้แก้ก่อน

---

# 22. Production AI Benchmark

ต้อง Benchmark ใหม่บน Production Hardware

## PyTorch

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/benchmark_inference.py \
    --backend pt \
    --warmup 10 \
    --runs 200
```

## OpenVINO

ถ้ายังไม่มี OpenVINO Export

```bash
cd /opt/smart-fire-detection-v2
sudo -u smartfire ./venv/bin/python export_openvino.py
```

จากนั้น Benchmark

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/benchmark_inference.py \
    --backend openvino \
    --device intel:cpu \
    --warmup 10 \
    --runs 200
```

---

# 23. เลือก Production Backend

เปรียบเทียบอย่างน้อย

```text
Model Load
First Warm-up
Mean
Median
P95
Maximum
Standard Deviation
Peak RAM
CPU
Approx FPS
```

อย่าตัดสินจาก FPS เพียงอย่างเดียว

---

# 24. PyTorch Production Configuration

ถ้าเลือก PyTorch

```env
MODEL_BACKEND=pt
INFERENCE_DEVICE=cpu
```

---

# 25. OpenVINO Production Configuration

ถ้าเลือก OpenVINO

```env
MODEL_BACKEND=openvino
INFERENCE_DEVICE=intel:cpu
```

แก้ที่

```text
/etc/smart-fire-detection/production.env
```

หลังแก้แล้ว คำสั่ง `systemd-run` รอบถัดไปจะอ่านค่าชุดใหม่โดยอัตโนมัติ

---

# 26. Camera Test

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/test_camera.py
```

Pass Criteria

```text
RTSP connected
Frame received
Resolution correct
Frame updates
No timeout
```

ถ้า Fail

```text
STOP
```

อย่าไป PTZ ต่อจนกว่า Camera Test จะผ่าน

---

# 27. PTZ Test

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/test_ptz.py
```

ตรวจด้วยสายตาว่ากล้องไป Preset ถูกจริง

ห้ามตัดสิน PASS จาก HTTP status เพียงอย่างเดียว

---

# 28. PTZ / Frame Sync

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/test_ptz_frame_sync.py
```

ต้องผ่าน

```text
PTZ Move
Fresh Frame
Stable Frame
```

ตรวจภาพ

```text
static/sync_preset_*.jpg
```

---

# 29. Camera Intrinsics

ต้องมี

```text
calibration/camera_intrinsics.json
```

ถ้า Production ใช้

```text
Camera เดิม
Lens เดิม
Optical Zoom เดิม
Digital Crop เดิม
Resolution เดิม
```

สามารถใช้ Calibration ที่ผ่าน Validation แล้วได้

ถ้าปัจจัยใดเปลี่ยน

```text
ต้อง Calibration ใหม่
```

---

# 30. Intrinsics บน Headless Server

`calibrate_intrinsics.py capture` ใช้ GUI

ดังนั้น Workflow ที่สะดวกคือทำ Capture บน Development Computer แล้วนำ

```text
calibration/camera_intrinsics.json
```

มา Production

เงื่อนไขสำคัญคือ

```text
Camera
Lens
Zoom
Crop
Resolution
Image Pipeline
```

ต้องตรงกัน

---

# 31. HFOV

Production Environment ต้องใช้

```env
HFOV_DEG=<CALIBRATED_VALUE>
```

HFOV ต้องตรงกับ Intrinsics Calibration

หาก Camera Geometry เปลี่ยน ห้ามใช้ค่าเดิมโดยไม่ตรวจ

---

# 32. Site GPS

เมื่อทราบตำแหน่งติดตั้งจริงแล้ว

แก้

```text
CAMERA_LAT
CAMERA_LON
```

ใน

```text
/etc/smart-fire-detection/production.env
```

ห้าม Commit Coordinate จริงเข้า Public Repository

---

# 33. Bearing Calibration

ทำหลังติด Camera ในตำแหน่งและ Orientation สุดท้ายแล้ว

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/calibrate_bearing.py
```

Output

```text
calibration/site.json
```

หากย้าย Camera หรือหมุนฐาน

```text
ต้องทำใหม่
```

---

# 34. Bearing Verification

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/verify_bearing.py
```

บันทึก

```text
MAE
RMSE
Max Error
```

สำหรับงานวิจัยควรเก็บผล Verification ไว้เป็นหลักฐาน

---

# 35. Distance Calibration

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/calibrate_distance.py
```

จำนวน Reference Points

```text
ขั้นต่ำ 3 จุด
แนะนำ 5–8 จุด
```

ใช้วัตถุอ้างอิงธรรมดา

ใช้ตำแหน่ง

```text
Bottom ground-contact Y
```

ไม่ใช้ Bounding Box Center

Output

```text
calibration/distance_global.json
```

---

# 36. Distance Verification

ใช้ Test Distances ที่ไม่ใช่ Calibration Points

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/verify_distance.py
```

บันทึก

```text
MAE
RMSE
MAPE
Max Error
```

หาก Error สูง ให้กลับไปตรวจ

```text
Y coordinate
Camera geometry
Ground plane
Calibration point distribution
```

ก่อน Full Production Validation

---

# 37. AI Validation

Positive Fire/Smoke tests ใช้ได้จาก

```text
Public Dataset
Existing Image
Existing Video
Recorded Media
Screen Playback
```

ไม่จำเป็นต้องสร้างเหตุการณ์จริงเพื่อทดสอบระบบ

---

# 38. Telegram

ถ้าใช้ Telegram ต้องกำหนด

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

ใน Production Environment

ทดสอบ

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/test_telegram.py
```

หาก Deployment ไม่ใช้ Telegram สามารถข้ามตาม Scope ได้

---

# 39. Full Preflight

เมื่อ Environment, Hardware และ Calibration พร้อมแล้ว

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/preflight.py
```

เป้าหมาย

```text
FAIL : 0
```

อ่าน Warning ทุกตัว

อย่าข้าม Warning โดยไม่ทราบสาเหตุ

---

# 40. Full Sweep

```bash
sudo systemd-run \
    --wait \
    --pipe \
    --collect \
    --uid=smartfire \
    --property=WorkingDirectory=/opt/smart-fire-detection-v2 \
    --property=EnvironmentFile=/etc/smart-fire-detection/production.env \
    /opt/smart-fire-detection-v2/venv/bin/python \
    /opt/smart-fire-detection-v2/test_full_sweep.py \
    --cycles 1
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
3-frame Detection
 ↓
Consensus
 ↓
Bearing
 ↓
Distance
 ↓
Output
```

ต้องไม่มี Critical Exception

ตรวจ

```text
static/sweep_runs/
```

---

# 41. ตรวจ Runtime Outputs

```bash
ls -lah /opt/smart-fire-detection-v2/static/
```

อาจมี

```text
latest_frame.jpg
latest_alert.jpg
status.json

alert_spool/
benchmark_runs/
detection_runs/
sweep_runs/
```

---

# 42. ตรวจ Runtime Permissions

ตรวจ

```bash
sudo ls -ld \
    /opt/smart-fire-detection-v2/static \
    /opt/smart-fire-detection-v2/calibration
```

Runtime user ต้องสามารถเขียนสอง Directory นี้ได้

หากจำเป็น

```bash
sudo chown -R smartfire:smartfire \
    /opt/smart-fire-detection-v2/static \
    /opt/smart-fire-detection-v2/calibration
```

---

# 43. ตรวจ systemd Units

Reload

```bash
sudo systemctl daemon-reload
```

ตรวจ Unit files

```bash
sudo systemd-analyze verify \
    /etc/systemd/system/smart-fire-detection.service \
    /etc/systemd/system/smart-fire-dashboard.service
```

ถ้ามี Error ให้แก้ก่อน Enable

---

# 44. Dashboard Production Server

บน Development Computer สามารถใช้

```bash
python app.py
```

ได้

คำสั่งนี้ใช้ Flask Development Server และมีไว้สำหรับ Local Development/Test

Production **ไม่เรียก `python app.py` โดยตรง**

Production ใช้

```text
Waitress
```

เป็น WSGI Server

Architecture

```text
smart-fire-dashboard.service
            ↓
      waitress-serve
            ↓
          app:app
            ↓
      Web Dashboard
```

Production command

```bash
/opt/smart-fire-detection-v2/venv/bin/waitress-serve \
    --host=0.0.0.0 \
    --port=5000 \
    app:app
```

ตรวจ Waitress

```bash
/opt/smart-fire-detection-v2/venv/bin/waitress-serve --help
```

ตรวจ Python import

```bash
/opt/smart-fire-detection-v2/venv/bin/python \
    -c "import waitress; print('waitress OK')"
```

---

# 45. Enable Detection Service

ทำเมื่อ

```text
Full Preflight PASS
Full Sweep PASS
Calibration accepted
Verification accepted
```

แล้วเท่านั้น

Enable

```bash
sudo systemctl enable smart-fire-detection.service
```

Start

```bash
sudo systemctl start smart-fire-detection.service
```

ตรวจ

```bash
sudo systemctl status smart-fire-detection.service
```

Expected

```text
active (running)
```

---

# 46. ตรวจ Detection Service Log

```bash
sudo journalctl \
    -u smart-fire-detection.service \
    -n 100 \
    --no-pager
```

Live

```bash
sudo journalctl \
    -u smart-fire-detection.service \
    -f
```

ต้องไม่มี Crash loop หรือ Error ต่อเนื่อง

---

# 47. Enable Dashboard Service

Enable

```bash
sudo systemctl enable smart-fire-dashboard.service
```

Start

```bash
sudo systemctl start smart-fire-dashboard.service
```

ตรวจ

```bash
sudo systemctl status smart-fire-dashboard.service
```

Expected

```text
active (running)
```

---

# 48. ตรวจ Dashboard Runtime

ตรวจ Process

```bash
ps -ef | grep '[w]aitress-serve'
```

ต้องพบ Waitress Process

ตรวจ API จาก Server เอง

```bash
curl -f http://127.0.0.1:5000/api/status
```

Expected

```text
HTTP request success
JSON response
```

หาก Service Active แต่ API ไม่ตอบ ให้ตรวจ Dashboard Log

---

# 49. Dashboard Logs

```bash
sudo journalctl \
    -u smart-fire-dashboard.service \
    -n 100 \
    --no-pager
```

Live

```bash
sudo journalctl \
    -u smart-fire-dashboard.service \
    -f
```

---

# 50. Service Relationship

Detection และ Dashboard เป็นคนละ Process

```text
Detection failure
≠
Dashboard process ต้องถูก kill

Dashboard failure
≠
Detection Runtime ต้องหยุด
```

Dashboard มี Ordering หลัง Detection Service แต่ไม่ควรถูกผูกจน Runtime หลักล้มตาม Dashboard

---

# 51. Dashboard Access

จากเครื่องภายใน Network ที่ได้รับอนุญาต

```text
http://<SERVER-IP>:5000
```

Dashboard แสดง

```text
Latest Frame
Last Alert
Status
```

API

```text
http://<SERVER-IP>:5000/api/status
```

---

# 52. Dashboard Security

Dashboard ปัจจุบันไม่มี Authentication

ดังนั้น

```text
ห้ามเปิด Port 5000 ออก Public Internet โดยตรง
```

ให้ใช้งานใน

```text
Trusted LAN
Private Network
Controlled Network
```

ก่อน

หากต้องเปิดจากภายนอก ควรเพิ่ม Security Layer ที่เหมาะสมก่อน

---

# 53. Reboot Test

หลังทั้งสอง Service ทำงานถูกต้อง

```bash
sudo reboot
```

เมื่อ Server กลับมา

```bash
systemctl is-active smart-fire-detection.service
systemctl is-active smart-fire-dashboard.service
```

Expected

```text
active
active
```

ตรวจเพิ่มเติม

```bash
sudo systemctl status smart-fire-detection.service
sudo systemctl status smart-fire-dashboard.service
```

ตรวจ Dashboard

```bash
curl -f http://127.0.0.1:5000/api/status
```

---

# 54. Production Daily Operations

## Detection Start

```bash
sudo systemctl start smart-fire-detection.service
```

## Detection Stop

```bash
sudo systemctl stop smart-fire-detection.service
```

## Detection Restart

```bash
sudo systemctl restart smart-fire-detection.service
```

## Dashboard Start

```bash
sudo systemctl start smart-fire-dashboard.service
```

## Dashboard Stop

```bash
sudo systemctl stop smart-fire-dashboard.service
```

## Dashboard Restart

```bash
sudo systemctl restart smart-fire-dashboard.service
```

---

# 55. ตรวจ Services พร้อมกัน

```bash
systemctl is-active smart-fire-detection.service
systemctl is-active smart-fire-dashboard.service
```

Expected

```text
active
active
```

---

# 56. ห้ามรัน Runtime ซ้อน

ถ้า

```bash
systemctl is-active smart-fire-detection.service
```

ได้

```text
active
```

ห้ามเปิด

```bash
python main.py
```

อีก Process

เพราะจะเกิด Runtime สองชุดพยายามใช้ Camera และ PTZ เดียวกัน

---

# 57. Manual Debug

ก่อน Manual Debug

```bash
sudo systemctl stop smart-fire-dashboard.service
sudo systemctl stop smart-fire-detection.service
```

จากนั้นใช้ `systemd-run` สำหรับ Test ที่ต้องการ Production Environment

เมื่อ Debug เสร็จ

```bash
sudo systemctl start smart-fire-detection.service
sudo systemctl start smart-fire-dashboard.service
```

---

# 58. Troubleshooting Detection Service

ตรวจตามลำดับ

```text
1. systemctl status
2. journalctl
3. production.env
4. Python venv
5. Dependencies
6. Model path
7. File permissions
8. Camera network
9. RTSP
10. PTZ
11. Calibration files
12. preflight.py
13. test_camera.py
14. test_ptz.py
15. test_ptz_frame_sync.py
16. test_full_sweep.py
```

อย่าเปลี่ยนหลายค่าในครั้งเดียว

---

# 59. Troubleshooting Dashboard

ตรวจตามลำดับ

```text
1. systemctl status smart-fire-dashboard.service
2. journalctl
3. waitress-serve
4. Waitress package
5. app.py
6. Flask dependency
7. STATIC_DIR
8. status.json
9. latest_frame.jpg
10. Port 5000
11. Network / Firewall
```

ตรวจ Waitress

```bash
/opt/smart-fire-detection-v2/venv/bin/waitress-serve --help
```

ตรวจ Local API

```bash
curl -v http://127.0.0.1:5000/api/status
```

---

# 60. Production Backup

ก่อน Update ควร Backup อย่างน้อย

```text
/etc/smart-fire-detection/production.env

calibration/camera_intrinsics.json
calibration/site.json
calibration/distance_global.json
```

รวม Calibration files อื่นที่ Runtime ใช้งานจริง

Model ที่ Production ใช้ก็ควรมีสำเนาที่ระบุ Version ได้

---

# 61. Update Source Code

ก่อน Update

```bash
sudo systemctl stop smart-fire-dashboard.service
sudo systemctl stop smart-fire-detection.service
```

Backup ก่อน

จากนั้น Update Source

---

# 62. หลัง Update

รัน Installer อีกครั้ง

```bash
cd /opt/smart-fire-detection-v2
sudo ./deploy/install.sh
```

Installer ไม่ควรเขียนทับ

```text
Production Environment
Site Calibration
Distance Calibration
Intrinsics
```

เดิมโดยไม่ตั้งใจ

---

# 63. Regression Test หลัง Update

อย่างน้อย

```text
Offline Preflight
      ↓
Unit Tests
      ↓
Tests ของ Module ที่แก้
      ↓
Full Preflight
      ↓
Full Sweep
      ↓
Detection Service
      ↓
Dashboard Service
```

---

# 64. Restart หลัง Update

```bash
sudo systemctl start smart-fire-detection.service
sudo systemctl start smart-fire-dashboard.service
```

ตรวจ Logs ทั้งสอง Service

---

# 65. เมื่อเปลี่ยน AI Model

ต้องทำ

```text
Model Inspection
      ↓
Production Benchmark
      ↓
Live Detection
      ↓
Detection Stability
      ↓
Full Preflight
      ↓
Full Sweep
      ↓
Production
```

ห้ามสมมติว่า Model ใหม่มี Accuracy หรือ Performance เหมือนเดิม

---

# 66. เมื่อเปลี่ยน Backend

ตัวอย่าง

```text
PyTorch
   ↓
OpenVINO
```

ต้องทำใหม่อย่างน้อย

```text
Benchmark
Preflight
AI Test
Full Sweep
```

---

# 67. เมื่อเปลี่ยน Camera

ตรวจใหม่

```text
RTSP
PTZ
Frame Sync
Intrinsics
HFOV
Bearing
Distance
Verification
Full Preflight
Full Sweep
```

---

# 68. เมื่อเปลี่ยน Lens / Zoom / Crop / Resolution

อย่างน้อย

```text
Intrinsics
HFOV
Bearing Verification
Distance Verification
Full Sweep
```

หาก Geometry เปลี่ยนจาก Calibration เดิม ต้องทำ Calibration ใหม่

---

# 69. เมื่อเปลี่ยน Orientation

ต้องทำอย่างน้อย

```text
Bearing Calibration
Bearing Verification
Full Preflight
Full Sweep
```

---

# 70. เมื่อย้าย Site

ห้ามใช้ Site Calibration เดิมทันที

ต้องทำ

```text
Production Coordinate
Bearing Calibration
Distance Calibration
Bearing Verification
Distance Verification
Full Preflight
Full Sweep
```

---

# 71. Production Security Checklist

```text
[ ] ไม่มี Camera Password ใน Git
[ ] ไม่มี Telegram Token ใน Git
[ ] ไม่มี Telegram Chat ID จริงใน Git
[ ] ไม่มี production.env ใน Git
[ ] ไม่มี Site GPS จริงใน Public Repository

[ ] production.env permission ถูกจำกัด
[ ] Services รันด้วย smartfire

[ ] Dashboard ใช้ Waitress
[ ] Dashboard ไม่ใช้ Flask Development Server ใน Production
[ ] Dashboard ไม่ถูกเปิด Public Internet โดยตรง

[ ] Model source/version ถูกบันทึก
[ ] Calibration version ถูกบันทึก
```

---

# 72. Production Acceptance Checklist

```text
[ ] Debian/Systemd พร้อม
[ ] Python 3.12 พร้อม

[ ] Project อยู่ /opt/smart-fire-detection-v2

[ ] install.sh ผ่าน
[ ] production.env ถูกต้อง
[ ] Secrets ไม่อยู่ใน Git

[ ] Offline Preflight FAIL=0

[ ] models/fire.pt พร้อม
[ ] OpenVINO model พร้อม ถ้าใช้

[ ] Production PyTorch Benchmark เสร็จ
[ ] Production OpenVINO Benchmark เสร็จ ถ้าเปรียบเทียบ
[ ] Production Backend ถูกเลือกแล้ว

[ ] Camera Test PASS
[ ] PTZ Test PASS
[ ] Frame Sync PASS

[ ] Intrinsics valid
[ ] HFOV ตรง

[ ] Site Coordinate ถูกต้อง

[ ] Bearing Calibration PASS
[ ] Bearing Verification accepted

[ ] Distance Calibration PASS
[ ] Distance Verification accepted

[ ] Telegram PASS ถ้าใช้

[ ] Full Preflight FAIL=0
[ ] Full Sweep PASS

[ ] Runtime outputs เขียนได้

[ ] Detection Service active
[ ] Dashboard Service active

[ ] Detection Restart PASS
[ ] Dashboard Restart PASS

[ ] Dashboard รันผ่าน Waitress
[ ] /api/status ตอบกลับ

[ ] journalctl ไม่มี Error ต่อเนื่อง

[ ] Reboot Test PASS
[ ] Detection Auto Start PASS
[ ] Dashboard Auto Start PASS

[ ] Dashboard เปิดได้จาก Network ที่อนุญาต
```

---

# 73. Production Ready

ให้ใช้สถานะ

```text
Production Ready
```

เมื่อ Production Acceptance Checklist ผ่านครบตาม Deployment Scope เท่านั้น

การที่

```text
main.py เปิดได้
```

หรือ

```text
AI ตรวจพบ Object ได้
```

เพียงอย่างเดียวไม่เพียงพอ

---

# 74. Production Runtime Summary

```text
Camera
   ↓
RTSP
   ↓
PTZ Step Scan
   ↓
Fresh Frame
   ↓
Stable Frame
   ↓
AI
   ↓
Multi-frame Consensus
   ↓
Bearing / Distance / GPS
   ↓
Alert / Telegram / Static Output
   ↓
Dashboard
```

Production Processes

```text
smart-fire-detection.service
        ↓
      main.py

smart-fire-dashboard.service
        ↓
   waitress-serve
        ↓
      app:app
```

---

# 75. Final Production Principle

```text
Development
     ↓
Test
     ↓
Benchmark
     ↓
Hardware Validation
     ↓
Calibration
     ↓
Verification
     ↓
Full Preflight
     ↓
Full Sweep
     ↓
systemd
     ↓
Service Validation
     ↓
Reboot Test
     ↓
Production Ready
```

เมื่อเกิดปัญหา

```text
อย่าเดา
อย่าแก้หลายค่าในครั้งเดียว
ย้อนกลับไป Test Layer ก่อนหน้า
วัดผลก่อนและหลังทุกการเปลี่ยนแปลง
```

---

# 76. Related Documentation

เอกสารหลักของ Repository

```text
README.md
= Project Overview / Quick Start

DEVELOPER_GUIDE.md
= Source Architecture / Developer Workflow

TESTING.md
= Testing Procedure / Release Gate

PRODUCTION_DEPLOYMENT_GUIDE.md
= Installation / Commissioning / Production Operations
```

เอกสารทั้ง 4 ไฟล์ต้องถูก Update พร้อมกันเมื่อ Architecture หรือ Production Workflow เปลี่ยน
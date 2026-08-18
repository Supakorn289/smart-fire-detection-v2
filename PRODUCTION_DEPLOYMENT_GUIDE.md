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
        main.py                   app.py
          │                         │
          ▼                         │
       static/ ─────────────────────┘
```

Detection Service

```text
Camera
PTZ
AI
Consensus
Bearing
Distance
GPS
Alert
Telegram
Runtime outputs
```

Dashboard Service

```text
Web Dashboard
/api/status
static file display
```

---

# 2. Production Workflow

```text
Development Validation
        ↓
Copy/Clone Project
        ↓
Production OS/Python
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

ห้ามใช้ Calibration จาก Site เก่าโดยไม่ตรวจ

ห้ามใช้ Development Benchmark เป็น Production Benchmark

ห้าม Commit Production secrets

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

Production Service ใช้

```text
smartfire
```

Group

```text
smartfire
```

ทั้ง Detection และ Dashboard ต้องรันด้วย Account นี้ ไม่ใช่ root

---

# 6. Production Requirements

Production workflow ปัจจุบันต้องมี

```text
Debian Linux
systemd
Python 3.12.x
Network access to Camera
Internet accessระหว่างติดตั้ง Python packages ถ้าจำเป็น
AI model
Storage สำหรับ Runtime outputs
```

---

# 7. ตรวจ Server

OS

```bash
cat /etc/os-release
```

Kernel

```bash
uname -r
```

Architecture

```bash
uname -m
```

CPU

```bash
lscpu
```

RAM

```bash
free -h
```

Disk

```bash
df -h
```

Network

```bash
ip addr
```

---

# 8. Python Requirement

ตรวจ

```bash
python3.12 --version
```

ต้องได้

```text
Python 3.12.x
```

หากไม่มี Python 3.12

```text
STOP
```

อย่าสร้าง venv ด้วย Python version อื่นโดยไม่ได้ Validate dependencies ใหม่

---

# 9. นำ Project ขึ้น Server

Project ต้องอยู่

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

Model binaries อาจไม่อยู่ใน Git

ต้องนำขึ้น Server แยกต่างหาก

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

ระหว่างยังไม่ตั้ง Site

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

อย่าใช้

```text
CHANGE_ME
```

กับ LAT/LON เพราะ `config.py` ต้องอ่านค่าเป็นตัวเลข

---

# 13. รัน Installer

```bash
cd /opt/smart-fire-detection-v2

chmod +x deploy/install.sh

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
ไม่ Start app.py
ไม่ Enable Services
ไม่ทำ Calibration
ไม่เขียนทับ production.env เดิม
```

หลัง Installer จบ **ยังไม่เปิด Production Service**

---

# 14. Production Environment

ไฟล์จริง

```text
/etc/smart-fire-detection/production.env
```

เปิดแก้

```bash
sudo nano /etc/smart-fire-detection/production.env
```

ค่าที่ต้องตรวจอย่างน้อย

```text
CAMERA_IP
CAMERA_PORT
CAMERA_USER
CAMERA_PWD

RTSP_PORT
RTSP_PATH

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
STARTUP_WARMUP_RUNS
```

---

# 15. Environment Security

Production environment ต้องไม่อยู่ใน Git

ตรวจ Permission

```bash
sudo ls -l /etc/smart-fire-detection/production.env
```

ควรมี Permission จำกัด

เช่น

```text
root root
0600
```

ห้ามใช้

```bash
cat /etc/smart-fire-detection/production.env
```

ใน Log หรือ Screenshot ที่อาจถูกเผยแพร่

ห้ามใช้คำสั่งที่ Dump Environment ทั้งหมดโดยไม่จำเป็น

---

# 16. Camera Credentials

ต้องแก้

```text
CAMERA_IP
CAMERA_USER
CAMERA_PWD
```

จาก Placeholder เป็นค่าจริงใน Production Environment

ห้ามแก้เป็นค่าจริงใน

```text
deploy/production.env.example
```

แล้ว Commit

---

# 17. Site Coordinates ระหว่าง Setup

ในระยะที่ Site GPS ยังไม่พร้อมสามารถใช้

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

เพื่อทำ Software/Hardware Test บางส่วนได้

แต่ Full Production Validation ต้องใช้ Site coordinate จริง

---

# 18. Manual Commissioning Shell

Production Environment เป็นไฟล์ที่ป้องกันไว้และอ่านโดย root/systemd

สำหรับขั้น Commissioning แบบ Manual ให้ใช้ Root shell

```bash
sudo -i
```

จากนั้น

```bash
set -a
source /etc/smart-fire-detection/production.env
set +a

cd /opt/smart-fire-detection-v2
```

จากนี้คำสั่ง Python ใน Commissioning section จะอ่าน Production Environment ชุดจริง

**อย่าแสดงค่าของ Environment ออกหน้าจอ**

เมื่อ Commissioning เสร็จจะคืน Ownership ของ Runtime directories ก่อนเปิด systemd

---

# 19. Offline Preflight บน Production

```bash
./venv/bin/python preflight.py --offline
```

เป้าหมาย

```text
FAIL : 0
```

Calibration/Camera ที่ยังไม่พร้อมสามารถ `SKIP` ตาม Offline semantics

ถ้า Software-critical item FAIL ให้แก้ก่อน

---

# 20. Production AI Benchmark

ต้อง Benchmark ใหม่บน Hardware จริง

## PyTorch

```bash
./venv/bin/python benchmark_inference.py \
    --backend pt \
    --warmup 10 \
    --runs 200
```

## OpenVINO

ถ้ายังไม่มี Export

```bash
./venv/bin/python export_openvino.py
```

จากนั้น

```bash
./venv/bin/python benchmark_inference.py \
    --backend openvino \
    --device intel:cpu \
    --warmup 10 \
    --runs 200
```

---

# 21. เลือก Backend

เปรียบเทียบ

```text
Mean
Median
P95
Maximum
Standard deviation
Peak RAM
CPU
Warm-up
```

อย่าดู FPS เพียงค่าเดียว

---

# 22. ตั้ง PyTorch

หากเลือก PyTorch

```env
MODEL_BACKEND=pt
INFERENCE_DEVICE=cpu
```

---

# 23. ตั้ง OpenVINO

หากเลือก OpenVINO

```env
MODEL_BACKEND=openvino
INFERENCE_DEVICE=intel:cpu
```

แก้ที่

```text
/etc/smart-fire-detection/production.env
```

จากนั้น Reload Environment ใน Commissioning shell

```bash
set -a
source /etc/smart-fire-detection/production.env
set +a
```

---

# 24. Camera Test

```bash
./venv/bin/python test_camera.py
```

Pass Criteria

```text
RTSP connected
Frame received
Resolution correct
Frame updates
No timeout
```

ถ้า Fail หยุดตรงนี้

---

# 25. PTZ Test

```bash
./venv/bin/python test_ptz.py
```

ดูการหมุนจริงของ Camera

ตรวจ Preset 1–9

อย่าตัดสินจาก HTTP success อย่างเดียว

---

# 26. PTZ / Frame Sync

```bash
./venv/bin/python test_ptz_frame_sync.py
```

ต้องผ่าน

```text
PTZ
Fresh Frame
Stable Frame
```

ตรวจภาพ

```text
static/sync_preset_*.jpg
```

---

# 27. Intrinsics

ต้องมี

```text
calibration/camera_intrinsics.json
```

หาก Camera/Lens/Zoom/Crop/Resolution เดียวกับชุดที่ Calibration แล้ว สามารถใช้ Calibration เดิมที่ผ่าน Validation ได้

ถ้า Geometry เปลี่ยน

```text
ต้อง Calibration ใหม่
```

---

# 28. Intrinsics บน Headless Server

`calibrate_intrinsics.py capture` ใช้ GUI

ดังนั้นทางเลือกที่สะดวกคือทำ Intrinsics Capture บน Development Computer ด้วย Camera configuration เดียวกัน แล้วนำ

```text
camera_intrinsics.json
```

ไป Production

เงื่อนไขคือ

```text
Camera
Lens
Zoom
Crop
Resolution
```

ต้องเหมือนกัน

---

# 29. HFOV

Production

```env
HFOV_DEG=<CALIBRATED_VALUE>
```

ต้องตรงกับ Intrinsics

อย่าใช้ค่าเก่าหลังเปลี่ยน Camera Geometry

---

# 30. Site GPS

เมื่อทราบตำแหน่งติดตั้งจริง

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

Reload

```bash
set -a
source /etc/smart-fire-detection/production.env
set +a
```

---

# 31. Bearing Calibration

เมื่อติด Camera ในตำแหน่งและ Orientation สุดท้ายแล้ว

```bash
./venv/bin/python calibrate_bearing.py
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

# 32. Bearing Verification

```bash
./venv/bin/python verify_bearing.py
```

ใช้ Reference directions ที่เหมาะสม

บันทึก

```text
MAE
RMSE
Max Error
```

สำหรับงานวิจัยควรเก็บผล Verification ไว้เป็นหลักฐาน

---

# 33. Distance Calibration

```bash
./venv/bin/python calibrate_distance.py
```

จำนวน

```text
ขั้นต่ำ 3
แนะนำ 5–8
```

ใช้ Reference object ธรรมดา

ใช้

```text
Bottom ground-contact Y
```

ไม่ใช้ Bounding Box center

Output

```text
calibration/distance_global.json
```

---

# 34. Distance Verification

ใช้ Test distances ที่ไม่ใช่ Calibration points

```bash
./venv/bin/python verify_distance.py
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

ก่อน Full Production

---

# 35. AI Validation

AI Positive Test สามารถใช้

```text
Public Dataset
Existing Image
Existing Video
Recorded Media
Screen Playback
```

ไม่จำเป็นต้องสร้างเหตุการณ์อันตรายจริง

---

# 36. Telegram

ถ้าใช้ Telegram

ตั้ง

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

แล้ว

```bash
./venv/bin/python test_telegram.py
```

ตรวจว่า Notification ถึงปลายทาง

หากไม่ใช้ Telegram สามารถปล่อย Disabled ได้ตาม Deployment scope

---

# 37. Full Preflight

หลัง Environment/Hardware/Calibration พร้อม

```bash
./venv/bin/python preflight.py
```

เป้าหมาย

```text
FAIL : 0
```

อ่าน Warning ทุกตัว

อย่าข้าม Warning โดยไม่ทราบสาเหตุ

---

# 38. Full Sweep

```bash
./venv/bin/python test_full_sweep.py --cycles 1
```

ตรวจ

```text
PTZ
 ↓
Fresh
 ↓
Stable
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

# 39. ตรวจ Runtime Outputs

```bash
ls -lah static/
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

# 40. คืน Ownership ก่อน systemd

ถ้าช่วง Commissioning รัน Python จาก Root shell ให้คืน Runtime directories

```bash
chown -R smartfire:smartfire \
    /opt/smart-fire-detection-v2/static \
    /opt/smart-fire-detection-v2/calibration
```

จากนั้น

```bash
exit
```

ตอนนี้กลับมา User shell ปกติ

---

# 41. ตรวจ systemd Units

```bash
sudo systemctl daemon-reload
```

ถ้ามี `systemd-analyze`

```bash
sudo systemd-analyze verify \
    /etc/systemd/system/smart-fire-detection.service \
    /etc/systemd/system/smart-fire-dashboard.service
```

แก้ Error ก่อน Enable

---

# 42. Enable Detection Service

ทำเมื่อ

```text
Full Preflight PASS
Full Sweep PASS
Calibration/Verification accepted
```

แล้วเท่านั้น

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

# 43. Enable Dashboard Service

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

# 44. Service Relationship

Dashboard unit มี Ordering หลัง Detection Service

แต่ไม่ได้บังคับให้ Detection ต้อง Active ตลอดเพื่อให้ Dashboard process อยู่

Architecture จึงเป็น

```text
Detection failure
≠
Dashboard process ต้องถูก kill

Dashboard failure
≠
Detection ต้องหยุด
```

---

# 45. Detection Logs

ล่าสุด

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

---

# 46. Dashboard Logs

ล่าสุด

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

# 47. Dashboard Access

ภายใน Network ที่อนุญาต

```text
http://<SERVER-IP>:5000
```

ตรวจ

```text
Latest frame
Last alert
Status
```

API

```text
http://<SERVER-IP>:5000/api/status
```

---

# 48. Dashboard Security

Dashboard ปัจจุบันไม่มี Authentication

ดังนั้น

```text
อย่าเปิด Port 5000 ออก Internet โดยตรง
```

ให้ใช้ใน Trusted/Internal Network จนกว่าจะเพิ่ม Security layer ที่เหมาะสม

---

# 49. Reboot Test

หลังทั้งสอง Service ทำงานถูกต้อง

```bash
sudo reboot
```

หลัง Server กลับมา

```bash
systemctl is-active smart-fire-detection.service
systemctl is-active smart-fire-dashboard.service
```

ต้องได้

```text
active
active
```

จากนั้นตรวจ

```bash
sudo systemctl status smart-fire-detection.service
sudo systemctl status smart-fire-dashboard.service
```

และเปิด Dashboard

---

# 50. คำสั่งใช้งานประจำวัน

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

# 51. ตรวจ Services พร้อมกัน

```bash
systemctl is-active smart-fire-detection.service
systemctl is-active smart-fire-dashboard.service
```

---

# 52. ห้ามรัน Runtime ซ้อน

ถ้า

```bash
systemctl is-active smart-fire-detection.service
```

ได้

```text
active
```

ห้ามรัน

```bash
python main.py
```

อีก Process

เพราะจะเกิด Runtime สองชุดพยายามใช้ Camera/PTZ เดียวกัน

---

# 53. Manual Debug

ก่อน Manual Debug

```bash
sudo systemctl stop smart-fire-dashboard.service
sudo systemctl stop smart-fire-detection.service
```

จากนั้นใช้ Commissioning shell ตามขั้นตอนเดิม

เมื่อเสร็จ

```bash
sudo systemctl start smart-fire-detection.service
sudo systemctl start smart-fire-dashboard.service
```

---

# 54. Troubleshooting Detection Service

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
9. Calibration files
10. preflight.py
11. test_camera.py
12. test_ptz_frame_sync.py
```

อย่าเปลี่ยนหลายค่าในเวลาเดียวกัน

---

# 55. Troubleshooting Dashboard

ตรวจ

```text
1. systemctl status smart-fire-dashboard
2. journalctl
3. app.py
4. Flask dependency
5. STATIC_DIR
6. status.json
7. latest_frame.jpg
8. Port 5000
9. Network/firewall
```

---

# 56. Production Backup

ก่อน Update ควร Backup อย่างน้อย

```text
/etc/smart-fire-detection/production.env

calibration/camera_intrinsics.json
calibration/site.json
calibration/distance_global.json
```

รวม Calibration files อื่นที่ใช้งานจริง

Model ที่ใช้ Production ก็ควรมีสำเนาที่ระบุ Version ได้

---

# 57. Update Source Code

ก่อน Update

```bash
sudo systemctl stop smart-fire-dashboard.service
sudo systemctl stop smart-fire-detection.service
```

Backup ก่อน

จากนั้น Update Source

---

# 58. หลัง Update

รัน Installer อีกครั้งได้

```bash
cd /opt/smart-fire-detection-v2
sudo ./deploy/install.sh
```

Installer ไม่ควรเขียนทับ Production Environment หรือ Site Calibration เดิมโดยไม่ตั้งใจ

---

# 59. Regression Test หลัง Update

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

# 60. Restart หลัง Update

```bash
sudo systemctl start smart-fire-detection.service
sudo systemctl start smart-fire-dashboard.service
```

ดู Logs ทั้งสอง

---

# 61. เมื่อเปลี่ยน AI Model

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

อย่าสมมติ Model ใหม่มี Accuracy/Performance เหมือนเดิม

---

# 62. เมื่อเปลี่ยน Backend

ตัวอย่าง

```text
PyTorch
 ↓
OpenVINO
```

ทำใหม่

```text
Benchmark
Preflight
AI Test
Full Sweep
```

---

# 63. เมื่อเปลี่ยน Camera

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
Full Sweep
```

---

# 64. เมื่อเปลี่ยน Lens/Zoom/Crop/Resolution

อย่างน้อย

```text
Intrinsics
HFOV
Bearing Verification
Distance Verification
Full Sweep
```

และ Calibration ใหม่เมื่อ Geometry ไม่ตรงชุดเดิม

---

# 65. เมื่อย้าย Site

ห้ามใช้ Site Calibration เดิมทันที

ต้องทำ

```text
Production coordinate
Bearing Calibration
Distance Calibration
Bearing Verification
Distance Verification
Full Preflight
Full Sweep
```

---

# 66. Production Security Checklist

```text
[ ] ไม่มี Camera Password ใน Git
[ ] ไม่มี Telegram Token ใน Git
[ ] ไม่มี production.env ใน Git
[ ] ไม่มี Site GPS จริงใน Public Repository
[ ] production.env permission ถูกจำกัด
[ ] Services รันด้วย smartfire
[ ] Dashboard ไม่ถูก expose Public Internet โดยตรง
[ ] Model source/version ถูกบันทึก
[ ] Calibration version ถูกบันทึก
```

---

# 67. Production Acceptance Checklist

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

[ ] Site coordinate ถูกต้อง
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

[ ] journalctl ไม่มี Error ต่อเนื่อง

[ ] Reboot Test PASS
[ ] Detection Auto Start PASS
[ ] Dashboard Auto Start PASS

[ ] Dashboard เปิดได้จาก Network ที่อนุญาต
```

---

# 68. Production Ready

ให้ใช้สถานะ

```text
Production Ready
```

เมื่อ Checklist ด้านบนผ่านครบตาม Deployment scope เท่านั้น

การที่

```text
main.py เปิดได้
```

หรือ

```text
AI ตรวจพบ object ได้
```

เพียงอย่างเดียวไม่เพียงพอ

---

# 69. Final Production Principle

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
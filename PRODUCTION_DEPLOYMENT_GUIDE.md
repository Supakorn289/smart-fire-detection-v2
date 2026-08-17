# Smart Fire Detection v2
# Production Deployment Guide

คู่มือการติดตั้ง ทดสอบ Calibration และเปิดใช้งานระบบ  
**Smart Fire Detection v2**

เอกสารนี้จัดทำสำหรับผู้พัฒนา ผู้ดูแลระบบ หรือผู้ที่ได้รับโปรเจกต์นี้ไปติดตั้งบนเครื่องใหม่ โดยอธิบายขั้นตอนตั้งแต่ Development Environment ไปจนถึง Production Server ตามลำดับที่ควรทำจริง

---

# 1. ภาพรวมระบบ

Smart Fire Detection v2 เป็นระบบตรวจจับ Fire/Smoke จากกล้อง IP PTZ โดยมีขั้นตอนการทำงานหลักดังนี้

```text
PTZ Move
   ↓
Camera Stop
   ↓
Fresh / Stable Frame
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

ระบบไม่ได้ประมวลผลวิดีโอแบบ Continuous FPS เป็นหลัก แต่ใช้ลักษณะ

```text
หมุน → หยุด → ตรวจ → หมุนต่อ
```

---

# 2. กฎสำคัญที่สุด

เมื่อได้รับโปรเจกต์นี้มาใหม่

## ห้ามเริ่มด้วย

```bash
python main.py
```

ทันที

ต้องทดสอบระบบเป็น Layer ก่อน

ลำดับที่แนะนำคือ

```text
Environment
    ↓
Preflight
    ↓
AI Benchmark
    ↓
Camera Test
    ↓
PTZ Test
    ↓
PTZ / Frame Sync
    ↓
Camera Calibration
    ↓
Bearing Calibration
    ↓
Distance Calibration
    ↓
Verification
    ↓
Full Sweep Test
    ↓
Production Service
```

ถ้าขั้นใดขึ้น `FAIL` หรือ Error ให้หยุดแก้ขั้นนั้นก่อน

---

# 3. โครงสร้างไฟล์สำคัญ

ตัวอย่างโครงสร้างหลัก

```text
smart-fire-detection-v2/
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
├── preflight.py
├── benchmark_inference.py
├── export_openvino.py
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
├── test_full_sweep.py
├── test_telegram.py
│
├── requirements.txt
├── TESTING.md
├── PRODUCTION_DEPLOYMENT_GUIDE.md
│
├── deploy/
│   ├── production.env.example
│   ├── smart-fire-detection.service
│   └── install.sh
│
├── models/
│   ├── fire.pt
│   └── fire_openvino_model/
│
├── calibration/
│   ├── camera_intrinsics.json
│   ├── site.json
│   └── distance_global.json
│
└── static/
```

ไฟล์บางรายการอาจยังไม่มีจนกว่าจะทำ Calibration หรือ Export Model

---

# 4. หน้าที่ของไฟล์หลัก

## `main.py`

Runtime หลักของระบบ

ทำหน้าที่ควบคุม

```text
Camera
PTZ
AI Detection
Consensus
Bearing
Distance
Alert
Dashboard
Logging
```

ไฟล์นี้ควรรันหลังจากระบบผ่านการทดสอบแล้วเท่านั้น

---

## `config.py`

Configuration หลักของระบบ

อ่านค่าจาก Environment Variables เช่น

```text
Camera IP
RTSP
PTZ
Resolution
HFOV
AI Backend
Model Path
Inference Device
Threshold
Camera Location
Telegram
```

Production ควรส่งค่าผ่าน Environment แทนการฝังค่าเฉพาะ Site ลง Source Code

---

## `preflight.py`

เครื่องมือตรวจสอบความพร้อมของระบบ

มี 2 Mode

### Offline

```bash
python preflight.py --offline
```

ใช้ตอน

- ยังไม่ต่อกล้อง
- ยังไม่ได้ติดตั้ง Site
- ต้องการตรวจ Software
- ต้องการตรวจ Python
- Dependencies
- Model Path
- Intrinsics / HFOV

Offline Mode จะไม่เชื่อม RTSP และไม่โหลด Model จริง

---

### Full

```bash
python preflight.py
```

ใช้เมื่อ Hardware พร้อมแล้ว

Full Mode จะตรวจ

```text
Python
Dependencies
Configuration
Calibration
AI Model
RTSP Camera
Telegram configuration
```

ก่อน Production ควรมี

```text
FAIL : 0
```

---

# 5. `benchmark_inference.py`

ใช้ Benchmark AI โดยไม่ต้องใช้กล้อง

รองรับ

```text
PyTorch
OpenVINO
```

ใช้เพื่อเปรียบเทียบ

```text
Mean latency
Median latency
P95
Min / Max
FPS โดยประมาณ
RAM
CPU
Warm-up
```

อย่าดู FPS เพียงค่าเดียว

สำหรับระบบลักษณะนี้ควรดูอย่างน้อย

```text
Median
P95
Standard Deviation
Peak RAM
CPU
```

ด้วย

---

# 6. `export_openvino.py`

ใช้ Export

```text
models/fire.pt
        ↓
OpenVINO
        ↓
models/fire_openvino_model/
```

ตัวอย่าง

```bash
python export_openvino.py
```

ช่วงแรกแนะนำให้ Export OpenVINO FP ก่อน

อย่าเริ่มจาก INT8 ทันที

INT8 ควรทำเมื่อมี Dataset สำหรับ Validation และต้องตรวจ Accuracy หลัง Quantization

---

# 7. Development Environment

ก่อนนำขึ้น Production ให้ตรวจโปรเจกต์บนเครื่อง Development ก่อน

---

## 7.1 เปิด Virtual Environment

Windows

```bat
venv\Scripts\activate
```

Linux

```bash
source venv/bin/activate
```

---

## 7.2 ตรวจ Python

```bash
python --version
```

Project baseline ปัจจุบัน

```text
Python 3.12.x
```

---

## 7.3 ตรวจ Dependencies

```bash
python -m pip list
```

หรือ

```bash
python preflight.py --offline
```

---

## 7.4 Unit Tests

ถ้ามี `pytest`

```bash
python -m pytest -q
```

ควรแก้ Unit Test ที่ Fail ก่อน Deploy

---

# 8. Offline Preflight

เมื่อยังไม่มีกล้อง

```bash
python preflight.py --offline
```

รายการเกี่ยวกับ Site เช่น

```text
Bearing calibration
Distance calibration
RTSP camera
```

สามารถเป็น

```text
SKIP
```

ได้ในช่วง Development

แต่ Software Configuration อื่นไม่ควรมี `FAIL`

---

# 9. Development AI Benchmark

ผล Benchmark บน Development Computer ใช้สำหรับตรวจว่า Pipeline ทำงาน

## ไม่ใช่ผลของ Production Server

---

## 9.1 PyTorch

```bash
python benchmark_inference.py \
--backend pt \
--warmup 10 \
--runs 200
```

Windows สามารถเขียนบรรทัดเดียวได้

```bat
python benchmark_inference.py --backend pt --warmup 10 --runs 200
```

---

## 9.2 OpenVINO

```bash
python benchmark_inference.py \
--backend openvino \
--device intel:cpu \
--warmup 10 \
--runs 200
```

Windows

```bat
python benchmark_inference.py --backend openvino --device intel:cpu --warmup 10 --runs 200
```

---

## 9.3 Benchmark Output

ผลจะถูกบันทึกประมาณ

```text
static/
└── benchmark_runs/
    ├── benchmark_pt_*.json
    └── benchmark_openvino_*.json
```

เก็บไฟล์เหล่านี้ไว้สำหรับเปรียบเทียบ

---

# 10. ห้ามใช้ Development Benchmark เป็น Production Benchmark

ถ้า Development Laptop ได้

```text
PyTorch = X ms
OpenVINO = Y ms
```

ไม่ได้หมายความว่า Production Server จะได้ผลเหมือนกัน

ต้อง Benchmark ใหม่บน Production Hardware

---

# 11. Production Deployment Structure

กำหนด Path มาตรฐานของ Production ดังนี้

## Project

```text
/opt/smart-fire-detection-v2
```

## Production Environment

```text
/etc/smart-fire-detection/production.env
```

## systemd Service

```text
/etc/systemd/system/smart-fire-detection.service
```

---

# 12. ไฟล์ใน `deploy/`

```text
deploy/
├── production.env.example
├── smart-fire-detection.service
└── install.sh
```

---

## `production.env.example`

Template Configuration สำหรับ Production

ไฟล์นี้สามารถอยู่ใน Git ได้

แต่ห้ามใส่ข้อมูลจริง เช่น

```text
Camera Password
Telegram Token
Site GPS
Secret
```

---

## `production.env`

ไฟล์จริงของ Production

ตัวอย่าง Path

```text
/etc/smart-fire-detection/production.env
```

ไฟล์นี้ไม่ควร Commit เข้า Git

---

## `smart-fire-detection.service`

systemd Service ของโปรแกรม

ทำหน้าที่

```text
Debian Boot
    ↓
systemd
    ↓
โหลด production.env
    ↓
เปิด Python venv
    ↓
รัน main.py
```

---

## `install.sh`

Production Installer

ใช้สำหรับเตรียม

```text
Service User
venv
Dependencies
PyTorch CPU
OpenVINO
Environment Directory
systemd Service
Runtime Directories
```

Installer ไม่ควรเปิด `main.py` อัตโนมัติทันที

เพราะต้องผ่านการทดสอบก่อน

---

# 13. เตรียม Production Server

ตรวจ OS

```bash
cat /etc/os-release
```

ตรวจ Architecture

```bash
uname -m
```

ตรวจ RAM

```bash
free -h
```

ตรวจ Disk

```bash
df -h
```

ตรวจ CPU

```bash
lscpu
```

---

# 14. ตรวจ Python

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

อย่าเพิ่งสร้าง venv ด้วย Python คนละ Version

ให้จัดการ Python Environment ให้ถูกต้องก่อน

---

# 15. นำ Project ขึ้น Server

Project ต้องอยู่ที่

```text
/opt/smart-fire-detection-v2
```

จากนั้น

```bash
cd /opt/smart-fire-detection-v2
```

ตรวจ

```bash
ls
```

ควรเห็นอย่างน้อย

```text
main.py
config.py
requirements.txt
preflight.py
benchmark_inference.py
deploy/
models/
calibration/
static/
```

---

# 16. รัน Production Installer

ให้สิทธิ์

```bash
chmod +x deploy/install.sh
```

จากนั้น

```bash
sudo ./deploy/install.sh
```

Installer ควรเตรียม

```text
smartfire user
venv
Python packages
PyTorch CPU
OpenVINO
production.env
systemd unit
```

เมื่อ Installer จบ

## ยังไม่ต้องเปิด Production Service

---

# 17. Production Environment

เปิด

```bash
sudo nano /etc/smart-fire-detection/production.env
```

กำหนดค่าจริงของ Site

เช่น

```text
Camera IP
Camera User
Camera Password
RTSP
HFOV
AI Backend
AI Model
Inference Device
Camera Location
Telegram
```

จากนั้นตั้ง Permission

```bash
sudo chmod 600 /etc/smart-fire-detection/production.env
```

---

# 18. Environment Security

ห้าม Commit

```text
production.env
.env
Camera Password
Telegram Token
Site Coordinates
```

ขึ้น Public Repository

ควร Commit เฉพาะ Template

```text
production.env.example
.env.example
```

---

# 19. Offline Preflight บน Production

ก่อนเชื่อม Camera

```bash
sudo -u smartfire bash -c '
set -a
source /etc/smart-fire-detection/production.env
set +a

cd /opt/smart-fire-detection-v2

./venv/bin/python preflight.py --offline
'
```

เป้าหมายคือ Software Environment ไม่มี `FAIL`

Calibration ที่ยังไม่ได้ทำสามารถเป็น `SKIP`

---

# 20. Production Benchmark

ต้อง Benchmark ใหม่บน Production Server

---

## PyTorch

```bash
sudo -u smartfire bash -c '
set -a
source /etc/smart-fire-detection/production.env
set +a

cd /opt/smart-fire-detection-v2

./venv/bin/python benchmark_inference.py \
--backend pt \
--warmup 10 \
--runs 200
'
```

---

## OpenVINO

```bash
sudo -u smartfire bash -c '
set -a
source /etc/smart-fire-detection/production.env
set +a

cd /opt/smart-fire-detection-v2

./venv/bin/python benchmark_inference.py \
--backend openvino \
--device intel:cpu \
--warmup 10 \
--runs 200
'
```

---

# 21. เปรียบเทียบ Backend

เปรียบเทียบอย่างน้อย

| Metric | PyTorch | OpenVINO |
|---|---:|---:|
| Mean | | |
| Median | | |
| P95 | | |
| Max | | |
| Std Dev | | |
| FPS | | |
| Peak RAM | | |
| CPU | | |

อย่าเลือก Backend จาก FPS เพียงอย่างเดียว

---

# 22. เลือก Production Backend

หลัง Benchmark จึงแก้

```bash
sudo nano /etc/smart-fire-detection/production.env
```

ถ้าเลือก PyTorch

```ini
MODEL_BACKEND=pt
INFERENCE_DEVICE=cpu
```

ถ้าเลือก OpenVINO

```ini
MODEL_BACKEND=openvino
INFERENCE_DEVICE=intel:cpu
```

หลังเปลี่ยน Backend ให้ Preflight ใหม่

---

# 23. Camera Test

หลัง Server เชื่อมต่อ Network ของ Camera แล้ว

รัน

```bash
./venv/bin/python test_camera.py
```

ตรวจ

```text
RTSP เชื่อมต่อได้
Frame ถูกอ่านได้
Resolution ถูกต้อง
Frame ไม่ค้าง
```

ถ้า Camera Test ไม่ผ่าน

```text
STOP
```

อย่าไปขั้น PTZ

---

# 24. PTZ Test

หลัง Camera ผ่าน

```bash
./venv/bin/python test_ptz.py
```

ตรวจ Preset

```text
1
2
3
4
5
6
7
8
9
```

ต้องไปยังตำแหน่งที่ถูกต้อง

---

# 25. PTZ / Frame Synchronization Test

รัน

```bash
./venv/bin/python test_ptz_frame_sync.py
```

ต้องตรวจว่า Sequence เป็น

```text
PTZ Move
    ↓
Camera Stop
    ↓
Fresh Frame
    ↓
Stable Frame
```

AI ไม่ควรใช้ Frame เก่าก่อนกล้องหยุด

---

# 26. Camera Intrinsics Calibration

ไฟล์

```text
calibrate_intrinsics.py
```

ใช้ Calibration กล้องและ Lens

ผลประมาณ

```text
calibration/camera_intrinsics.json
```

ข้อมูลสำคัญ เช่น

```text
fx
fy
cx
cy
Distortion
HFOV
VFOV
```

---

# 27. เมื่อไรต้องทำ Intrinsics ใหม่

หากเปลี่ยนสิ่งต่อไปนี้

```text
Camera
Lens
Optical Zoom
Digital Crop
Resolution
Image Pipeline
```

ควรตรวจหรือ Calibration ใหม่

---

# 28. HFOV

Runtime ต้องใช้ HFOV ที่ตรงกับ Calibration

Production ปัจจุบันควรกำหนดผ่าน

```ini
HFOV_DEG=<ค่าที่ได้จาก Calibration>
```

อย่าใช้ค่าเก่าโดยไม่ตรวจสอบ

---

# 29. Bearing Calibration

เมื่อ Camera ถูกติดตั้งในตำแหน่งจริงแล้ว

รัน

```bash
./venv/bin/python calibrate_bearing.py
```

ไฟล์นี้ใช้เชื่อมทิศของระบบเข้ากับทิศจริงของ Site

ผล

```text
calibration/site.json
```

---

# 30. Bearing Calibration เป็น Site-specific

เมื่อย้าย Camera

```text
Site A
   ↓
ย้ายกล้อง
   ↓
Site B
```

อย่าใช้ `site.json` เดิมโดยอัตโนมัติ

ต้อง Calibration Bearing ใหม่

---

# 31. Distance Calibration

รัน

```bash
./venv/bin/python calibrate_distance.py
```

ผลหลัก

```text
calibration/distance_global.json
```

Calibration ควรใช้หลายจุดระยะ

และควรครอบคลุมช่วงระยะที่ระบบต้องใช้งานจริง

---

# 32. การทำ Distance Calibration อย่างปลอดภัย

ใช้ Target หรือวัตถุอ้างอิงธรรมดาในพื้นที่จริง

ไม่จำเป็นต้องสร้าง Fire หรือ Smoke จริงเพื่อ Calibration

จุดที่ใช้วัดควรสามารถระบุตำแหน่งพื้นได้ชัด

---

# 33. Bearing Verification

หลัง Bearing Calibration

```bash
./venv/bin/python verify_bearing.py
```

ไฟล์นี้ใช้ตรวจ Error

เช่น

```text
Angular Error
Bearing MAE
Bearing RMSE
Maximum Error
```

`verify_bearing.py`

```text
ไม่แก้ site.json
```

---

# 34. Distance Verification

หลัง Distance Calibration

```bash
./venv/bin/python verify_distance.py
```

ควรใช้ระยะ Verification ที่ไม่ได้ใช้เป็น Calibration Points เดิมทั้งหมด

ไฟล์นี้

```text
ไม่แก้ distance_global.json
```

---

# 35. Calibration กับ Verification ต่างกันอย่างไร

```text
Calibration
    ↓
สร้าง / ปรับ Model
```

แต่

```text
Verification
    ↓
ตรวจว่า Model ที่สร้างไว้แม่นแค่ไหน
```

อย่าสับสนสองขั้นนี้

---

# 36. Full Preflight

หลัง Hardware และ Calibration พร้อม

รัน

```bash
sudo -u smartfire bash -c '
set -a
source /etc/smart-fire-detection/production.env
set +a

cd /opt/smart-fire-detection-v2

./venv/bin/python preflight.py
'
```

เป้าหมาย

```text
FAIL : 0
```

ถ้ามี `WARN` ให้อ่านรายละเอียดก่อน

อย่าข้าม Warning โดยไม่รู้สาเหตุ

---

# 37. Full Sweep Test

ก่อน Production

```bash
./venv/bin/python test_full_sweep.py --cycles 1
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

ต้องไม่มี Exception สำคัญ

---

# 38. AI Test

การทดสอบ AI สามารถใช้

```text
Public Dataset
Existing Test Image
Existing Video
Recorded Media
Screen Playback
```

ได้

ไม่จำเป็นต้องสร้างเหตุการณ์อันตรายจริงเพื่อทดสอบระบบ

---

# 39. Telegram Test

ถ้าเปิด Telegram

```bash
./venv/bin/python test_telegram.py
```

ตรวจว่า Server สามารถส่ง Notification ได้

ถ้ายังไม่ใช้ Telegram สามารถปิดไว้ในช่วง Development ได้ตาม Configuration

---

# 40. ตรวจ Output Directory

ตรวจ

```bash
ls -lah static/
```

ควรมี Permission ให้ Runtime เขียนไฟล์ได้

ระบบอาจสร้าง

```text
latest_frame.jpg
latest_alert.jpg
status.json
alert_spool/
benchmark_runs/
sweep_runs/
```

ตามส่วนที่ใช้งาน

---

# 41. เปิด Production Service

ทำขั้นนี้หลังจาก

```text
Preflight PASS
Camera PASS
PTZ PASS
Frame Sync PASS
Bearing Calibration COMPLETE
Distance Calibration COMPLETE
Verification COMPLETE
Full Sweep PASS
```

แล้วเท่านั้น

---

## Reload systemd

```bash
sudo systemctl daemon-reload
```

---

## Enable Auto Start

```bash
sudo systemctl enable smart-fire-detection.service
```

---

## Start

```bash
sudo systemctl start smart-fire-detection.service
```

---

# 42. ตรวจ Production Service

```bash
sudo systemctl status smart-fire-detection.service
```

ควรเห็น

```text
active (running)
```

---

# 43. ดู Log

Log ล่าสุด

```bash
sudo journalctl \
-u smart-fire-detection.service \
-n 100 \
--no-pager
```

Log แบบ Live

```bash
sudo journalctl \
-u smart-fire-detection.service \
-f
```

---

# 44. คำสั่ง Service ที่ใช้บ่อย

## Start

```bash
sudo systemctl start smart-fire-detection.service
```

## Stop

```bash
sudo systemctl stop smart-fire-detection.service
```

## Restart

```bash
sudo systemctl restart smart-fire-detection.service
```

## Status

```bash
sudo systemctl status smart-fire-detection.service
```

## Enable

```bash
sudo systemctl enable smart-fire-detection.service
```

## Disable

```bash
sudo systemctl disable smart-fire-detection.service
```

---

# 45. Reboot Test

หลัง Service ทำงานถูกต้อง

```bash
sudo reboot
```

หลัง Server กลับมา

```bash
sudo systemctl status smart-fire-detection.service
```

ต้องกลับมาเป็น

```text
active (running)
```

โดยไม่ต้องเปิด `main.py` เอง

---

# 46. หาก Service เปิดไม่ขึ้น

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
9. preflight.py
```

ดู Error ล่าสุด

```bash
sudo journalctl \
-u smart-fire-detection.service \
-n 100 \
--no-pager
```

แก้ Error ที่ชัดเจนที่สุดก่อน

อย่าเปลี่ยนหลายค่าในเวลาเดียวกัน

---

# 47. การ Update Source Code

ก่อน Update

```bash
sudo systemctl stop smart-fire-detection.service
```

---

# 48. ไฟล์ที่ควร Backup ก่อน Update

อย่างน้อย

```text
/etc/smart-fire-detection/production.env

calibration/camera_intrinsics.json

calibration/site.json

calibration/distance_global.json
```

และไฟล์ Calibration อื่นที่ใช้งานจริง

---

# 49. หลัง Update

รัน Installer ได้อีกครั้งตาม Workflow ของโปรเจกต์

```bash
sudo ./deploy/install.sh
```

Installer ไม่ควรเขียนทับ

```text
production.env
Calibration
Site Configuration
```

โดยไม่แจ้ง

---

# 50. Test หลัง Update

ตามลำดับ

```text
Offline Preflight
       ↓
Unit Test
       ↓
ส่วนที่แก้ไข
       ↓
Full Preflight
       ↓
Full Sweep
       ↓
Restart Service
```

---

# 51. Restart หลัง Update

```bash
sudo systemctl restart smart-fire-detection.service
```

ดู Log

```bash
sudo journalctl \
-u smart-fire-detection.service \
-f
```

---

# 52. ถ้าเปลี่ยน AI Model

เมื่อเปลี่ยน

```text
models/fire.pt
```

ควรทำ

```text
Model Inspection
       ↓
AI Benchmark
       ↓
Detection Test
       ↓
Full Sweep
       ↓
Production
```

ห้ามสมมติว่า Model ใหม่ทำงานเหมือน Model เดิม

---

# 53. ถ้าเปลี่ยน AI Backend

ตัวอย่าง

```text
PyTorch
   ↓
OpenVINO
```

ต้องทำ

```text
Benchmark
Preflight
Detection Test
Full Sweep
```

ใหม่

---

# 54. ถ้าเปลี่ยน Camera

ต้องตรวจอย่างน้อย

```text
RTSP
Resolution
Intrinsics
HFOV
PTZ
Bearing
Distance
```

---

# 55. ถ้าเปลี่ยน Optical Zoom

ต้องถือว่า Camera Geometry อาจเปลี่ยน

ควรตรวจ

```text
Intrinsics
HFOV
Bearing
Distance
```

ก่อน Production

---

# 56. ถ้าย้าย Site

ต้องทำใหม่อย่างน้อย

```text
Camera Coordinates
Bearing Calibration
Distance Calibration
Bearing Verification
Distance Verification
Full Preflight
Full Sweep
```

อย่านำ Site Calibration เก่ามาใช้โดยไม่ตรวจ

---

# 57. Production Readiness Checklist

ก่อนประกาศว่า Production Ready ให้ตรวจทุกข้อ

```text
[ ] Python 3.12 ถูกต้อง

[ ] Python venv ใช้งานได้

[ ] Dependencies ครบ

[ ] Unit Tests ผ่าน

[ ] production.env ตั้งค่าครบ

[ ] ไม่มี Password จริงอยู่ใน Git

[ ] ไม่มี Telegram Token จริงอยู่ใน Git

[ ] ไม่มี Site GPS จริงใน Public Repository

[ ] models/fire.pt พร้อม

[ ] OpenVINO model พร้อม ถ้าเลือก OpenVINO

[ ] Production Benchmark PyTorch เสร็จ

[ ] Production Benchmark OpenVINO เสร็จ ถ้าใช้เปรียบเทียบ

[ ] Backend ถูกเลือกจาก Production Hardware

[ ] test_camera.py ผ่าน

[ ] test_ptz.py ผ่าน

[ ] test_ptz_frame_sync.py ผ่าน

[ ] Resolution ถูกต้อง

[ ] Intrinsics ถูกต้อง

[ ] HFOV ถูกต้อง

[ ] Bearing Calibration เสร็จ

[ ] Bearing Verification ผ่าน

[ ] Distance Calibration เสร็จ

[ ] Distance Verification ผ่าน

[ ] Full Preflight FAIL = 0

[ ] test_full_sweep.py ผ่าน

[ ] Telegram Test ผ่าน ถ้าเปิดใช้

[ ] static/ เขียนไฟล์ได้

[ ] systemd Service ติดตั้งแล้ว

[ ] Service Start ได้

[ ] Service Restart ได้

[ ] Service Auto Start หลัง Reboot ได้

[ ] ตรวจ journalctl แล้วไม่มี Error ต่อเนื่อง
```

---

# 58. Workflow ฉบับย่อ

```text
┌─────────────────────┐
│     DEVELOPMENT     │
└──────────┬──────────┘
           │
           ├─ Python / venv
           ├─ Unit Tests
           ├─ Offline Preflight
           ├─ PyTorch Benchmark
           └─ OpenVINO Benchmark
           │
           ▼
┌─────────────────────┐
│       DEPLOY        │
└──────────┬──────────┘
           │
           ├─ Copy / Clone Project
           ├─ Python Environment
           ├─ install.sh
           └─ production.env
           │
           ▼
┌─────────────────────┐
│ PRODUCTION BENCHMARK│
└──────────┬──────────┘
           │
           ├─ PyTorch
           ├─ OpenVINO
           └─ Select Backend
           │
           ▼
┌─────────────────────┐
│   HARDWARE TEST     │
└──────────┬──────────┘
           │
           ├─ Camera
           ├─ PTZ
           └─ Frame Sync
           │
           ▼
┌─────────────────────┐
│    CALIBRATION      │
└──────────┬──────────┘
           │
           ├─ Intrinsics / HFOV
           ├─ Bearing
           └─ Distance
           │
           ▼
┌─────────────────────┐
│    VERIFICATION     │
└──────────┬──────────┘
           │
           ├─ Bearing
           └─ Distance
           │
           ▼
┌─────────────────────┐
│     FINAL TEST      │
└──────────┬──────────┘
           │
           ├─ Full Preflight
           ├─ Full Sweep
           └─ Telegram
           │
           ▼
┌─────────────────────┐
│       SYSTEMD       │
└──────────┬──────────┘
           │
           ├─ Enable
           ├─ Start
           ├─ Check Log
           └─ Reboot Test
           │
           ▼
┌─────────────────────┐
│  PRODUCTION READY   │
└─────────────────────┘
```

---

# 59. ลำดับคำสั่งแบบเร็ว

สำหรับผู้ที่เคยติดตั้งระบบแล้ว

```text
1. ตรวจ Python

2. สร้าง / ตรวจ venv

3. Install dependencies

4. python preflight.py --offline

5. Benchmark AI

6. test_camera.py

7. test_ptz.py

8. test_ptz_frame_sync.py

9. ตรวจ Intrinsics / HFOV

10. calibrate_bearing.py

11. calibrate_distance.py

12. verify_bearing.py

13. verify_distance.py

14. python preflight.py

15. test_full_sweep.py --cycles 1

16. test_telegram.py

17. systemctl enable

18. systemctl start

19. journalctl

20. reboot test
```

---

# 60. กฎสรุปของระบบ

## Rule 1

อย่ารัน `main.py` เป็น Test แรก

---

## Rule 2

อย่าใช้ Development Benchmark เป็นผลของ Production Server

---

## Rule 3

เปลี่ยน Camera / Lens / Zoom / Resolution  
ต้องตรวจ Camera Geometry ใหม่

---

## Rule 4

ย้าย Site  
ต้องทำ Site Calibration ใหม่

---

## Rule 5

Calibration และ Verification เป็นคนละขั้นตอน

```text
Calibration = สร้างค่า

Verification = ตรวจค่าที่สร้าง
```

---

## Rule 6

`verify_bearing.py` และ `verify_distance.py`

ไม่ควรแก้ Calibration

---

## Rule 7

Production Secret ห้ามอยู่ใน Source Code หรือ Public Git

---

## Rule 8

เปลี่ยน Model หรือ Backend  
ต้อง Benchmark และ Test ใหม่

---

## Rule 9

เปิด systemd Service หลังจาก Full Preflight และ Full Sweep ผ่านแล้ว

---

## Rule 10

ถ้าไม่แน่ใจว่าปัญหาอยู่ตรงไหน

ให้กลับมาทดสอบทีละ Layer

```text
Environment
    ↓
Camera
    ↓
PTZ
    ↓
Frame Sync
    ↓
AI
    ↓
Geometry
    ↓
Alert
    ↓
Full Runtime
```

อย่าแก้หลาย Layer พร้อมกัน

---

# 61. สถานะของระบบ

สถานะของระบบควรแบ่งเป็น

```text
Development
        ↓
Integration Tested
        ↓
Field Test Candidate
        ↓
Site Calibrated
        ↓
Production Benchmark Passed
        ↓
Full Validation Passed
        ↓
Production Ready
```

อย่าใช้คำว่า `Production Ready` จนกว่าการทดสอบบน Hardware และ Site จริงจะเสร็จครบ

---

# 62. เอกสารที่ควรอ่านเพิ่มเติม

ภายใน Repository ควรอ่านร่วมกับ

```text
README.md

DEVELOPER_GUIDE.md

TESTING.md

PRODUCTION_DEPLOYMENT_GUIDE.md
```

หน้าที่ของแต่ละไฟล์

```text
README.md
= ภาพรวม Project

DEVELOPER_GUIDE.md
= คู่มือสำหรับผู้พัฒนา Source Code

TESTING.md
= วิธีทดสอบแต่ละ Component

PRODUCTION_DEPLOYMENT_GUIDE.md
= วิธีนำระบบขึ้น Production ตั้งแต่ต้นจนจบ
```

---

# 63. Final Principle

หลักสำคัญของการ Deploy ระบบนี้คือ

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
ทดสอบเต็มระบบ
   ↓
Production
```

เมื่อเกิดปัญหาให้ย้อนกลับไปยัง Layer ก่อนหน้าและตรวจทีละส่วน

ไม่ควรแก้หลายค่าพร้อมกันโดยไม่มีผลการวัดรองรับ
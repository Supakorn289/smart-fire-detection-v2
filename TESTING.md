# Smart Fire Detection v2
# Testing Guide

เอกสารนี้เป็น Test Procedure หลักของ Smart Fire Detection v2

ใช้สำหรับ

```text
Development
Regression Test
Hardware Validation
Site Calibration
Production Acceptance
Release Gate
```

---

# 1. หลักการ

ห้ามเริ่ม Test ด้วย

```bash
python main.py
```

ให้ตรวจจาก Layer ล่างขึ้นบน

```text
Software
 ↓
Model
 ↓
Camera
 ↓
PTZ
 ↓
Frame Sync
 ↓
AI
 ↓
Calibration
 ↓
Verification
 ↓
Full Pipeline
 ↓
Runtime
```

ถ้าขั้นใด FAIL ให้หยุดแก้ขั้นนั้นก่อน

---

# 2. Test Environment Record

ก่อน Test ให้จด

```text
Date:
Tester:
Machine:
Operating System:
Python:
CPU:
RAM:
Camera:
Camera Resolution:
Lens/Zoom:
Model:
Model Backend:
Inference Device:
Site:
Git Commit:
```

ห้ามบันทึก Password, Token หรือข้อมูลลับลง Test Report

---

# 3. Test Levels

```text
LEVEL 1
Software-only

LEVEL 2
AI-only

LEVEL 3
Camera/Hardware

LEVEL 4
Calibration/Verification

LEVEL 5
Full Integration

LEVEL 6
Production Service
```

---

# T01 — Unit Tests

รัน

```bash
python -m pytest -q
```

Pass Criteria

```text
ไม่มี FAILED
ไม่มี ERROR
Exit code = 0
```

`pytest.ini` จำกัด discovery ไปที่

```text
tests/
```

จึงไม่รัน Hardware scripts ที่ Root

Result

```text
T01 Unit Tests: PASS / FAIL
```

---

# T02 — Model Inspection

ต้องมี

```text
models/fire.pt
```

รัน

```bash
python inspect_model.py
```

ตรวจว่า Model สามารถ map Classes ที่ต้องการเป็น

```text
fire
smoke
```

Pass Criteria

```text
Model load สำเร็จ
Fire class พร้อม
Smoke class พร้อม
ไม่มี Class mapping error
```

Result

```text
T02 Model Inspection: PASS / FAIL
```

---

# T03 — Offline Preflight

รัน

```bash
python preflight.py --offline
```

ใช้เมื่อ

```text
ยังไม่ต่อ Camera
หรือ
ต้องการตรวจ Software ก่อน Hardware
```

Pass Criteria หลัก

```text
FAIL : 0
```

รายการ Hardware/Site สามารถ `SKIP` ได้

Warning ต้องอ่านและเข้าใจสาเหตุ

Result

```text
T03 Offline Preflight: PASS / FAIL
```

---

# T04 — AI Benchmark

## PyTorch

```bash
python benchmark_inference.py --backend pt --warmup 10 --runs 200
```

## OpenVINO

```bash
python benchmark_inference.py --backend openvino --device intel:cpu --warmup 10 --runs 200
```

เก็บค่า

```text
Backend:
Model load:
Warm-up first:
Mean:
Median:
P95:
Min:
Max:
Std Dev:
Approx FPS:
Peak RAM:
CPU:
```

ผลจะอยู่ประมาณ

```text
static/benchmark_runs/
```

Development Benchmark ใช้ตรวจ Pipeline

Production Server ต้อง Benchmark ใหม่

Result

```text
T04 AI Benchmark: PASS / FAIL
```

---

# T05 — RTSP Camera

ตั้ง Camera Environment ให้ครบก่อน

รัน

```bash
python test_camera.py
```

Pass Criteria

```text
RTSP connection success
ได้รับ Frame
Frame มีการ Update
Resolution ถูกต้อง
ไม่มี Timeout
```

ตรวจภาพที่ถูกบันทึกด้วย

Result

```text
T05 RTSP Camera: PASS / FAIL
```

---

# T06 — PTZ

รัน

```bash
python test_ptz.py
```

ระบบจะเดินตาม Sweep sequence

ตรวจด้วยสายตา

```text
P1
P2
P3
P4
P5
P4
P3
P2
P1
P6
P7
P8
P9
P8
P7
P6
P1
```

Pass Criteria

```text
HTTP command success
กล้องไป Preset จริง
ไม่ติดขัด
ไม่มี PTZ exception
```

อย่าตัดสิน PASS จาก HTTP status เพียงอย่างเดียว

Result

```text
T06 PTZ: PASS / FAIL
```

---

# T07 — PTZ / Frame Sync

รัน

```bash
python test_ptz_frame_sync.py
```

Test sequence เน้นตำแหน่งที่ต่างกันชัด

Flow

```text
PTZ move
 ↓
wait
 ↓
arrival sequence
 ↓
fresh frames
 ↓
stable frame
 ↓
save image
```

Pass Criteria

```text
RTSP ready
PTZ success
Fresh frame success
Stable frame success
Frame หลัง Move ไม่ใช่ภาพก่อน Move
```

ตรวจ

```text
static/sync_preset_*.jpg
```

ด้วยสายตา

Result

```text
T07 PTZ Frame Sync: PASS / FAIL
```

---

# T08 — Live Detection Pipeline

รัน

```bash
python test_detection_live.py
```

ตรวจ

```text
Camera
PTZ
Fresh/stable frame
AI loading
Warm-up
Inference
Class mapping
Consensus
Bearing
Distance เมื่อ Calibration มี
GPS เมื่อ Calibration valid
Image output
```

การทดสอบ Detection ที่ต้องมี Fire/Smoke ให้ใช้

```text
Public dataset
Existing media
Recorded media
Screen playback
```

ไม่จำเป็นต้องสร้างเหตุการณ์อันตรายจริง

Pass Criteria

```text
Pipeline ทำงานจบ
ไม่มี Exception
Model output ถูก parse
Output ถูกบันทึก
```

Result

```text
T08 Live Detection: PASS / FAIL
```

---

# T09 — Detection Stability

รันตาม Options ของ Script

```bash
python test_detection_stability.py --help
```

จากนั้นเลือก Preset/จำนวน Frame ตาม Test Plan

ตรวจ

```text
Detection frequency
Confidence variation
BBox stability
IoU
False positive behavior
Inference latency
```

T09 แนะนำเมื่อ

```text
เปลี่ยน Model
เปลี่ยน threshold
เปลี่ยน Camera
เปลี่ยน Scene
พบ False Positive
```

Result

```text
T09 Detection Stability: PASS / WARN / FAIL
```

---

# T10 — Camera Intrinsics

ทำขั้นนี้เมื่อ

```text
ยังไม่มี camera_intrinsics.json
หรือ
Camera/Lens/Zoom/Crop/Resolution เปลี่ยน
```

Generate Checkerboard

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

Pass Criteria

```text
Calibration สำเร็จ
มีจำนวน View เพียงพอ
Reprojection error อยู่ในเกณฑ์ที่ Script ยอมรับ
valid_for_production = true
Frame dimensions ถูกต้อง
HFOV ถูกต้อง
```

ถ้า Hardware geometry ไม่เปลี่ยนและมี Calibration ที่ผ่านแล้ว สามารถใช้ Test นี้เป็น Validation แทนการ Capture ใหม่ได้

Result

```text
T10 Intrinsics: PASS / SKIP / FAIL
```

---

# T11 — Bearing Calibration & Verification

## Calibration

ติด Camera ใน Orientation จริงก่อน

รัน

```bash
python calibrate_bearing.py
```

Output

```text
calibration/site.json
```

ตรวจ

```text
Preset 1 reference ถูกต้อง
Measured bearing ถูกต้อง
site.json ถูกสร้าง
```

## Verification

```bash
python verify_bearing.py
```

ใช้ Reference directions ที่ไม่ได้ใช้สร้าง Calibration เพียงอย่างเดียว

บันทึก

```text
MAE:
RMSE:
Max Error:
```

Pass Criteria ต้องกำหนดตาม Requirement ของงานวิจัย/Deployment

Result

```text
T11 Bearing:
Calibration PASS / FAIL
Verification PASS / WARN / FAIL
```

หากย้าย Camera หรือเปลี่ยน Orientation ต้องทำใหม่

---

# T12 — Distance Calibration & Verification

## Calibration

```bash
python calibrate_distance.py
```

ใช้ Reference object ธรรมดา

จำนวนจุด

```text
ขั้นต่ำ 3
แนะนำ 5–8
```

กระจายระยะให้ครอบคลุม Working Range

ใช้ค่า

```text
Y ของจุดล่างสุดที่วัตถุสัมผัสพื้น
```

Output

```text
calibration/distance_global.json
```

## Verification

ใช้ระยะที่ไม่ได้ใช้ในการ Fit

ตัวอย่าง

```text
Calibration:
6 m
8 m
10 m

Verification:
7 m
9 m
```

รัน

```bash
python verify_distance.py
```

บันทึก

```text
MAE
RMSE
MAPE
Max Error
```

แนวทางจาก Script

```text
≤ 5%    ดีมาก
≤ 10%   ดี
≤ 15%   พอใช้
> 15%   ควรตรวจ/Calibration ใหม่
```

Result

```text
T12 Distance:
Calibration PASS / FAIL
Verification PASS / WARN / FAIL
```

---

# T13 — Telegram

ถ้าเปิดใช้งาน Telegram

กำหนด

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

รัน

```bash
python test_telegram.py
```

Pass Criteria

```text
ข้อความทดสอบถูกส่ง
ไม่มี Network/API error
Exit code = 0
```

หาก Deployment ไม่ใช้ Telegram

```text
T13 = SKIP
```

Result

```text
T13 Telegram: PASS / SKIP / FAIL
```

---

# T14 — Full Preflight

หลัง Hardware และ Calibration พร้อม

รัน

```bash
python preflight.py
```

ตรวจ

```text
Python
Dependencies
Production environment
Camera credentials
Backend/device
Runtime parameters
Resolution
HFOV
Camera coordinates
PTZ configuration
RTSP
Intrinsics
Bearing calibration
Distance calibration
Telegram
AI model
AI classes
Camera
```

Pass Criteria

```text
FAIL : 0
```

Warning ต้องอ่านทุกตัว

Result

```text
T14 Full Preflight: PASS / FAIL
```

---

# T15 — Full Sweep

รัน

```bash
python test_full_sweep.py --cycles 1
```

Pipeline

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
Annotated output
 ↓
Summary JSON
```

Output

```text
static/sweep_runs/
```

Pass Criteria

```text
Sweep จบครบ
ไม่มี Critical Exception
ทุก Preset ที่ต้องใช้เข้าถึงได้
Fresh/Stable ทำงาน
AI ทำงาน
Summary JSON ถูกสร้าง
Images ถูกบันทึก
```

จำนวน Detection ไม่ใช่เกณฑ์ PASS โดยตัวมันเอง

Scene ที่ไม่มี Fire/Smoke สามารถมี

```text
0 confirmed detections
```

และยังถือว่า Pipeline Test ผ่านได้

Result

```text
T15 Full Sweep: PASS / FAIL
```

---

# T16 — Runtime & Dashboard

## Runtime

```bash
python main.py
```

ตรวจหลาย Sweep cycles

Pass Criteria

```text
RTSP stable
PTZ loop ต่อเนื่อง
ไม่มี Exception ต่อเนื่อง
Status ถูก Update
latest_frame ถูก Update
Alert logic ทำงาน
Memory/CPU ไม่ผิดปกติ
```

หยุด

```text
Ctrl+C
```

## Dashboard

อีก Terminal

```bash
python app.py
```

เปิด

```text
http://127.0.0.1:5000
```

ตรวจ

```text
Latest frame
Last alert
Status
```

API

```text
/api/status
```

Result

```text
T16 Runtime: PASS / FAIL
T16 Dashboard: PASS / FAIL
```

---

# P01 — Production Services

ทำเฉพาะ Production Server

ตรวจ

```bash
sudo systemctl status smart-fire-detection.service
sudo systemctl status smart-fire-dashboard.service
```

ต้องเป็น

```text
active (running)
active (running)
```

Restart

```bash
sudo systemctl restart smart-fire-detection.service
sudo systemctl restart smart-fire-dashboard.service
```

ตรวจ Log

```bash
sudo journalctl -u smart-fire-detection.service -n 100 --no-pager
sudo journalctl -u smart-fire-dashboard.service -n 100 --no-pager
```

Pass Criteria

```text
Detection start ได้
Dashboard start ได้
Restart ได้
ไม่มี Crash loop
```

---

# P02 — Reboot Test

หลัง Enable Services

```bash
sudo reboot
```

เมื่อกลับมา

```bash
systemctl is-active smart-fire-detection.service
systemctl is-active smart-fire-dashboard.service
```

Expected

```text
active
active
```

เปิด Dashboard และตรวจ Runtime Output อีกครั้ง

Result

```text
P02 Reboot: PASS / FAIL
```

---

# Optional — PTZ Repeatability

เมื่อสงสัยว่า Preset ไม่ Repeatable

```bash
python test_ptz_repeatability_v1.py --help
```

ใช้ Test approach จากคนละทิศ เช่น

```text
P3 → P4
P5 → P4
```

ภาพปลายทางควรใกล้เคียงกันถ้า Preset repeatable

---

# Optional — Advanced Bearing Geometry

```text
calibrate_bearing_v2.py
refine_overlap_marks_v3.py
fit_preset_geometry_v3.py
fit_preset_geometry_v3_1.py
```

ใช้สำหรับ Research/Diagnostic Geometry

ไม่แทน Standard Site Bearing Calibration

---

# Optional — Hard Negative Workflow

เก็บ Candidate

```bash
python collect_hard_negatives.py --help
```

Review

```bash
python review_hard_negatives.py --run-dir <RUN_DIR>
```

เปิด

```text
http://127.0.0.1:5055
```

Labels

```text
true_negative
actual_fire
actual_smoke
discard
```

Prepare Add-on

```bash
python prepare_hard_negative_addon.py --run-dir <RUN_DIR> --output <OUTPUT_DIR>
```

นำเฉพาะ `true_negative` ที่ Review แล้วไปเป็น Negative data

---

# Regression Matrix

| Source changed | Minimum tests |
|---|---|
| `geometry.py` | T01, T11, T12, T15 |
| `calibration.py` | T01, T12, T15 |
| `camera.py` | T05, T07, T15, T16 |
| `ptz.py` | T06, T07, T15, T16 |
| `detection.py` | T01, T02, T08, T09, T15 |
| `notify.py` | T13, T16 |
| `overlay.py` | T08, T15, T16 |
| `app.py` | T16, P01 |
| `config.py` | T03 + tests related to changed values + T14 |
| `preflight.py` | T03, T14 |
| Model | T02, T04, T08, T09, T15 |
| Backend | T04, T08, T14, T15 |
| Camera/Lens/Zoom | T05, T07, T10, T11, T12, T15 |
| Production service files | P01, P02 |

---

# Test Result Template

```text
Smart Fire Detection v2
Test Report

Date:
Tester:
Git Commit:

Machine:
OS:
Python:
CPU:
RAM:

Camera:
Resolution:
Lens/Zoom:

Model:
Backend:
Device:

Site:

T01 Unit Tests               PASS / FAIL
T02 Model Inspection         PASS / FAIL
T03 Offline Preflight        PASS / FAIL
T04 AI Benchmark             PASS / FAIL
T05 RTSP Camera              PASS / FAIL
T06 PTZ                      PASS / FAIL
T07 PTZ Frame Sync           PASS / FAIL
T08 Live Detection           PASS / FAIL
T09 Detection Stability      PASS / WARN / FAIL
T10 Intrinsics               PASS / SKIP / FAIL
T11 Bearing Calibration      PASS / FAIL
T11 Bearing Verification     PASS / WARN / FAIL
T12 Distance Calibration     PASS / FAIL
T12 Distance Verification    PASS / WARN / FAIL
T13 Telegram                 PASS / SKIP / FAIL
T14 Full Preflight           PASS / FAIL
T15 Full Sweep               PASS / FAIL
T16 Runtime                  PASS / FAIL
T16 Dashboard                PASS / FAIL

P01 Detection Service        PASS / FAIL
P01 Dashboard Service        PASS / FAIL
P02 Reboot Test              PASS / FAIL

PyTorch Mean:
PyTorch Median:
PyTorch P95:
PyTorch Peak RAM:

OpenVINO Mean:
OpenVINO Median:
OpenVINO P95:
OpenVINO Peak RAM:

Distance MAE:
Distance RMSE:
Distance MAPE:
Distance Max Error:

Bearing MAE:
Bearing RMSE:
Bearing Max Error:

Notes:
```

---

# Development Release Gate

ก่อน Merge Runtime-critical changes

```text
[ ] T01 PASS
[ ] T02 PASS
[ ] T03 PASS
[ ] Regression tests ของ Module ที่แก้ PASS
[ ] T15 PASS ถ้าแก้ Runtime pipeline
```

---

# Field Test Gate

ก่อนนำระบบไป Site

```text
[ ] T01 PASS
[ ] T02 PASS
[ ] T03 PASS
[ ] T04 PASS
[ ] T05 PASS
[ ] T06 PASS
[ ] T07 PASS
[ ] T08 PASS
[ ] T10 PASS หรือ Calibration เดิมได้รับการ Validate
```

---

# Production Release Gate

ก่อนเรียกว่า Production Ready

```text
[ ] Production Environment ถูกต้อง
[ ] ไม่มี Secrets ใน Git

[ ] T01 PASS
[ ] T02 PASS
[ ] T03 PASS

[ ] Production T04 Benchmark เสร็จ
[ ] Backend ถูกเลือกจาก Production Hardware

[ ] T05 PASS
[ ] T06 PASS
[ ] T07 PASS
[ ] T08 PASS

[ ] T10 PASS
[ ] T11 Calibration PASS
[ ] T11 Verification PASS/Accepted
[ ] T12 Calibration PASS
[ ] T12 Verification PASS/Accepted

[ ] T13 PASS ถ้าใช้ Telegram

[ ] T14 FAIL = 0
[ ] T15 PASS
[ ] T16 PASS

[ ] P01 Detection Service PASS
[ ] P01 Dashboard Service PASS
[ ] P02 Reboot PASS

[ ] journalctl ไม่มี Error ต่อเนื่อง
```

ถ้ายังไม่ครบ อย่าเรียกสถานะว่า `Production Ready`
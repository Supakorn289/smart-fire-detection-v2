# Smart Fire Detection v2
# Developer Guide

คู่มือสำหรับผู้พัฒนา Source Code ของ Smart Fire Detection v2

เอกสารนี้อธิบาย Architecture, Module responsibilities, Configuration, Runtime flow, Testing strategy, Calibration, AI backend, Alert, Dashboard และกฎเมื่อมีการแก้ Source Code

สำหรับวิธี Deploy จริงอ่าน

```text
PRODUCTION_DEPLOYMENT_GUIDE.md
```

สำหรับ Test Procedures อ่าน

```text
TESTING.md
```

---

# 1. Architecture

Runtime หลัก

```text
Camera RTSP
    ↓
LatestFrameCamera
    ↓
PTZ Controller
    ↓
Fresh Frame
    ↓
Stable Frame
    ↓
FireDetector
    ↓
Multi-frame Consensus
    ↓
Geometry
    ├── Bearing
    ├── Distance
    └── GPS
    ↓
Overlay
    ↓
Alert Deduplicator
    ↓
Telegram Worker
    ↓
Static Outputs
    ↓
Dashboard
```

---

# 2. Runtime Principle

ระบบใช้ Step Scan

```text
PTZ Move
   ↓
Wait
   ↓
Discard stale frames
   ↓
Fresh frames
   ↓
Stable image
   ↓
AI inference
   ↓
Confirmation
   ↓
Output
```

เหตุผลสำคัญคือไม่ให้ AI ประมวลผลภาพที่

```text
เกิดก่อน PTZ move
หรือ
เกิดระหว่างกล้องยังเคลื่อนที่
```

---

# 3. Main Modules

## `main.py`

Production Runtime หลัก

รับผิดชอบ

```text
RTSP startup
AI startup
AI warm-up
PTZ sweep
Fresh/stable frame
Detection
Consensus
Bearing
Distance
GPS safety
Overlay
Dashboard outputs
Alert deduplication
Telegram queue
Runtime status
```

ไม่ควรใช้ `main.py` เป็น Test ตัวแรก

---

## `config.py`

Configuration layer

อ่านค่าจาก Environment Variables

ครอบคลุม

```text
Camera / RTSP
Resolution
HFOV
PTZ
Model
Inference device
Detection thresholds
Consensus
Calibration
Site coordinates
Telegram
Alert
Static output
Headless mode
```

ค่าที่เป็น Path แบบ Relative จะถูก Resolve จาก Project root

ดังนั้น

```text
models/fire.pt
```

หมายถึง

```text
<PROJECT_ROOT>/models/fire.pt
```

ไม่ขึ้นกับ Current Working Directory

---

## `camera.py`

รับผิดชอบ RTSP frame acquisition

หลักสำคัญ

```text
Latest-frame model
Sequence number
Timestamp
wait_for_newer()
Stable-frame support
```

Code ส่วนอื่นไม่ควรเปิด `cv2.VideoCapture` ซ้ำโดยไม่จำเป็น

---

## `ptz.py`

ควบคุม PTZ Presets ผ่าน Camera HTTP interface

รับผิดชอบ

```text
goto_preset()
save_preset()
PTZ travel estimation
Preset bearing lookup
```

`goto_preset()` คืน

```text
success
estimated wait time
```

การได้ HTTP Success ไม่ได้ยืนยันว่าภาพสุดท้ายถูกทิศ

จึงต้องใช้ `test_ptz_frame_sync.py` ร่วมด้วย

---

## `detection.py`

รับผิดชอบ

```text
Load AI model
Normalize class names
Fire/Smoke threshold
Bounding boxes
Bearing
Distance
Distance quality
GPS
IoU
Multi-frame consensus
```

Canonical classes

```text
fire
smoke
```

Aliases สามารถ map ชื่อ Model ที่ใกล้เคียงเข้ากับสอง Class นี้ได้

---

## `geometry.py`

รับผิดชอบ Geometry

เช่น

```text
Bearing normalization
Pixel X → bearing
Compass direction
GPS from bearing + distance
Longitude normalization
```

Geometry functions ควรมี Unit Test ก่อนนำไปใช้จริง

---

## `calibration.py`

รับผิดชอบ

```text
Distance model fitting
Distance model loading
Distance model saving
Site calibration
Calibration range
```

Distance model หลัก

```text
y = H + K/Z
```

โดย

```text
y = vertical image coordinate
Z = distance
H/K = fitted parameters
```

---

## `notify.py`

รับผิดชอบ Telegram

Runtime ใช้ Worker/Queue เพื่อไม่ให้ Telegram network latency block PTZ scan loop

ถ้า Telegram ไม่ได้ Configure ระบบควรยังทำ Local Alert ได้

---

## `overlay.py`

วาด

```text
Bounding box
Class
Confidence
Distance
Bearing
Compass direction
Preset status
```

---

## `app.py`

Web Dashboard

อ่าน Runtime output จาก

```text
static/
```

แสดง

```text
Latest frame
Latest alert
Status
```

API

```text
/api/status
```

Default port

```text
5000
```

Dashboard ไม่ได้ควบคุม PTZ หรือ AI โดยตรง

---

# 4. Production Services

Production แยกเป็นสอง Process

```text
smart-fire-detection.service
        ↓
      main.py
```

และ

```text
smart-fire-dashboard.service
        ↓
      app.py
```

เหตุผลที่แยก Service

```text
Dashboard failure
ไม่ได้หมายความว่า
Detection Runtime ต้องหยุด
```

ทั้งสองอ่าน Environment จาก

```text
/etc/smart-fire-detection/production.env
```

---

# 5. Configuration Strategy

Development และ Production ต้องไม่ฝัง

```text
Camera IP จริง
Camera Password
Telegram Token
Telegram Chat ID
Site GPS
```

ใน Source Code

ใช้ Environment Variables แทน

---

# 6. `.env.example`

`.env.example` เป็นเอกสารตัวอย่าง

`config.py` ไม่ได้ auto-load `.env`

ดังนั้นการ Copy

```text
.env.example
→
.env
```

เพียงอย่างเดียวจะไม่ทำให้ Environment ถูกโหลด

ค่าต้องมาจาก

```text
Shell
IDE
systemd
EnvironmentFile
```

---

# 7. Production Environment

Production ใช้

```text
/etc/smart-fire-detection/production.env
```

Template

```text
deploy/production.env.example
```

ระหว่างยังไม่ตั้ง Site

```env
CAMERA_LAT=nan
CAMERA_LON=nan
```

ก่อน Production Ready ต้องใช้ Coordinate จริง

---

# 8. Current Important Defaults

Runtime baseline

```text
FRAME_WIDTH=1280
FRAME_HEIGHT=720

HFOV_DEG=60.195288

MODEL_BACKEND=pt
INFERENCE_DEVICE=cpu
IMGSZ=640

FIRE_THRESHOLD=0.50
SMOKE_THRESHOLD=0.60

FRAMES_PER_SCAN=3
MIN_CONFIRM_FRAMES=2

FRAME_SAMPLE_GAP_SEC=0.15
CONSENSUS_IOU_THRESHOLD=0.30

MIN_VALID_DISTANCE_M=1.0
MAX_VALID_DISTANCE_M=200.0
```

ค่าเหล่านี้เป็น Configuration baseline

อย่าถือว่าเหมาะกับทุก Model/Camera/Site โดยไม่ Validate

---

# 9. PTZ Geometry

Physical pan coordinates

```text
P1 =    0.0
P2 =  +45.0
P3 =  +90.0
P4 = +135.0
P5 = +177.5

P6 =  -45.0
P7 =  -90.0
P8 = -135.0
P9 = -177.5
```

Nominal bearing

```text
P1 =   0.0
P2 =  45.0
P3 =  90.0
P4 = 135.0
P5 = 177.5

P6 = 315.0
P7 = 270.0
P8 = 225.0
P9 = 182.5
```

Sweep

```text
[1,2,3,4,5,4,3,2,1,6,7,8,9,8,7,6,1]
```

Nominal values เป็น Software Geometry

True North ต้องอาศัย Site Bearing Calibration

---

# 10. Camera Fresh-frame Contract

หลัง PTZ Move

ห้ามใช้ Frame ที่ได้มาก่อน movement

Flow ที่ถูกต้อง

```text
seq_before
 ↓
PTZ move
 ↓
wait
 ↓
arrival_seq
 ↓
POST_MOVE_FRESH_FRAMES
 ↓
fresh packet
 ↓
wait_until_stable()
 ↓
stable packet
```

หากแก้ `camera.py` หรือ `ptz.py` ต้อง Regression Test ส่วนนี้เสมอ

---

# 11. Stable-frame Detection

Stable-frame logic ใช้ Frame difference เพื่อตรวจว่าภาพหยุดนิ่งเพียงพอ

ค่าที่เกี่ยวข้อง

```text
STABLE_DIFF_THRESHOLD
STABLE_REQUIRED_PAIRS
STABLE_TIMEOUT_SEC
```

อย่าปรับหลายค่าในเวลาเดียวกัน

ควรวัดผลก่อนและหลังทุกครั้ง

---

# 12. Multi-frame Detection

Runtime ไม่ยืนยัน Detection จาก Frame เดียวทันที

Default

```text
FRAMES_PER_SCAN = 3
MIN_CONFIRM_FRAMES = 2
```

แนวคิด

```text
Frame 1
Frame 2
Frame 3
   ↓
match class + overlapping bbox
   ↓
2/3 confirmed
```

IoU threshold

```text
CONSENSUS_IOU_THRESHOLD
```

---

# 13. Bearing

Bearing ของ Detection มาจาก

```text
Preset center bearing
+
Pixel X angular offset
+
Site north offset
```

Site north offset มาจาก

```text
calibration/site.json
```

หากไม่มี `site.json`

ระบบยังคำนวณ Software Bearing ได้

แต่ไม่ควรถือเป็น Site-calibrated True North result

---

# 14. Distance

Distance ใช้

```text
BBox bottom Y
        ↓
Distance calibration model
        ↓
Estimated distance
```

Model ถูกสร้างจาก

```text
calibrate_distance.py
```

Global output

```text
calibration/distance_global.json
```

ค่าที่อยู่นอก Calibration range ต้องถูกมองว่า Reliability ต่ำกว่าค่าภายในช่วงที่เคย Calibration

---

# 15. GPS

GPS ต้องมี

```text
Camera latitude/longitude
Bearing
Distance
Valid calibration state
```

ห้ามสร้างความเชื่อมั่นว่า GPS ถูกต้อง หาก Bearing/Distance ยังไม่ Validate

---

# 16. Camera Intrinsics

ไฟล์

```text
calibration/camera_intrinsics.json
```

ประกอบด้วยข้อมูล เช่น

```text
Camera matrix
fx
fy
cx
cy
Distortion coefficients
HFOV
VFOV
Frame dimensions
Calibration quality
```

ต้องทำใหม่หรือ Validate ใหม่เมื่อเปลี่ยน

```text
Camera
Lens
Zoom
Crop
Resolution
Image processing pipeline
```

---

# 17. Standard Bearing Calibration

Production workflow มาตรฐาน

```bash
python calibrate_bearing.py
```

ใช้ Preset 1 เป็น Site reference

Output

```text
calibration/site.json
```

---

# 18. Advanced Bearing Geometry

ไฟล์เหล่านี้เป็น Research/Diagnostic tools

```text
calibrate_bearing_v2.py
refine_overlap_marks_v3.py
fit_preset_geometry_v3.py
fit_preset_geometry_v3_1.py
```

`calibrate_bearing_v2.py`

หา Relative Geometry เช่น

```text
Effective HFOV
Principal X
Relative preset centers
```

Output หลักเป็น Relative Geometry

**ไม่ใช่ True North**

จึงไม่แทนที่

```text
calibrate_bearing.py
```

ใน Standard Production Workflow

---

# 19. PTZ Repeatability

ใช้

```bash
python test_ptz_repeatability_v1.py
```

เมื่อสงสัยว่า Preset เดียวกันกลับมาไม่ตรงตำแหน่งเดิมเมื่อเข้าจากคนละทิศ

เป็น Diagnostic Test

ไม่จำเป็นต้องรันทุกครั้งถ้า PTZ behavior ไม่ได้เปลี่ยน

---

# 20. AI Backend

รองรับ

```text
pt
openvino
```

PyTorch

```text
MODEL_BACKEND=pt
INFERENCE_DEVICE=cpu
```

OpenVINO

```text
MODEL_BACKEND=openvino
INFERENCE_DEVICE=intel:cpu
```

อย่าเปลี่ยน Backend โดยไม่ Benchmark และ Regression Test

---

# 21. AI Benchmark

```bash
python benchmark_inference.py --backend pt --warmup 10 --runs 200
```

และ

```bash
python benchmark_inference.py --backend openvino --device intel:cpu --warmup 10 --runs 200
```

Metrics สำคัญ

```text
Median
P95
Max
Standard deviation
Peak RAM
CPU
Warm-up
```

FPS อย่างเดียวไม่เพียงพอ

---

# 22. OpenVINO

Export

```bash
python export_openvino.py
```

Output

```text
models/fire_openvino_model/
```

ให้เริ่มจาก Floating-point export และ Validation ก่อน

Quantization ต้องมี Accuracy Validation แยกต่างหาก

---

# 23. Alert Architecture

Confirmed detections ถูกส่งเข้า Event Deduplicator

พิจารณาจาก

```text
Class
Preset
BBox IoU
Cooldown
```

ถ้า Event ใหม่

```text
latest_alert.jpg
 ↓
Alert message
 ↓
Telegram queue / local alert
```

ถ้า Duplicate

```text
Alert suppressed
```

---

# 24. Telegram Worker

Telegram ใช้ Queue เพื่อไม่ block Runtime

หาก

```text
spool creation fail
หรือ
queue reject
```

Runtime ไม่ควรบันทึก Event ว่าส่งสำเร็จ เพื่อให้สามารถ Retry ในรอบถัดไปได้

---

# 25. Dashboard Outputs

`main.py` เขียน

```text
static/latest_frame.jpg
static/latest_alert.jpg
static/status.json
```

`app.py` อ่านไฟล์เหล่านี้

ดังนั้น Dashboard เป็น Consumer ของ Runtime output

ไม่ควรเพิ่ม Camera/AI control ลง Dashboard โดยไม่มีเหตุผลทาง Architecture

---

# 26. Atomic Output

Runtime output ที่ Dashboard อ่านควรเขียนแบบ Atomic เมื่อเป็นไปได้ เพื่อไม่ให้ Browser อ่านไฟล์ขณะกำลังเขียนครึ่งหนึ่ง

เมื่อแก้ Output logic ต้องทดสอบ

```text
main.py
app.py
```

พร้อมกัน

---

# 27. Development Dependencies

Development

```bash
python -m pip install -r requirements-dev.txt
```

Production Runtime

```bash
python -m pip install -r requirements.txt
```

`pytest` เป็น Development dependency

---

# 28. Unit Tests

```bash
python -m pytest -q
```

Test files อยู่ใน

```text
tests/
```

ครอบคลุมอย่างน้อย

```text
Distance calibration
Calibration range
Detection utilities
Geometry/GPS
```

---

# 29. Preflight

Offline

```bash
python preflight.py --offline
```

Full

```bash
python preflight.py
```

Preflight เป็น Readiness Checker

ไม่ใช่ Replacement ของ Hardware Test หรือ Full Sweep

---

# 30. Standard Development Test Order

```text
T01 Unit Tests
 ↓
T02 Model Inspection
 ↓
T03 Offline Preflight
 ↓
T04 AI Benchmark
 ↓
T05 Camera
 ↓
T06 PTZ
 ↓
T07 Frame Sync
 ↓
T08 Live Detection
 ↓
T09 Stability
 ↓
T10 Intrinsics
 ↓
T11 Bearing
 ↓
T12 Distance
 ↓
T13 Telegram
 ↓
T14 Full Preflight
 ↓
T15 Full Sweep
 ↓
T16 Runtime / Dashboard
```

รายละเอียดอยู่ใน

```text
TESTING.md
```

---

# 31. Hard Negative Workflow

เมื่อ Model เกิด False Positive

ใช้

```text
collect_hard_negatives.py
```

เพื่อเก็บ Candidate

จากนั้น

```text
review_hard_negatives.py
```

ให้คน Review

Labels

```text
true_negative
actual_fire
actual_smoke
discard
```

จากนั้นสร้าง Add-on

```text
prepare_hard_negative_addon.py
```

เฉพาะ `true_negative`

ห้ามนำ Candidate ทั้งหมดเป็น Negative อัตโนมัติ

---

# 32. Safe AI Validation

Positive Fire/Smoke tests สามารถใช้

```text
Public dataset
Existing images
Existing video
Recorded media
Screen playback
```

ไม่จำเป็นต้องสร้างเหตุการณ์จริงเพื่อทดสอบ Model

---

# 33. Error-handling Principle

Runtime component ควร

```text
Fail clearly
Log context
Clean resources
Avoid hiding exceptions
```

Camera ต้องถูก stop ใน `finally` เมื่อ Script เป็นเจ้าของ Camera lifecycle

---

# 34. Adding a New Configuration Variable

ขั้นตอน

```text
1. เพิ่มใน config.py
2. ตั้ง Safe Default หรือไม่มี Default ตามความเหมาะสม
3. เพิ่ม .env.example
4. เพิ่ม deploy/production.env.example ถ้า Production ต้องใช้
5. เพิ่ม validation ใน preflight.py ถ้าค่า critical
6. Update documentation
7. Unit/Integration test
```

ห้ามเพิ่ม Secret เป็น Source default

---

# 35. Adding a New Production Requirement

ถ้าค่าใหม่เป็น Production-critical ต้องตรวจ

```text
preflight.py
deploy/production.env.example
deploy/install.sh
systemd services
PRODUCTION_DEPLOYMENT_GUIDE.md
```

พร้อมกัน

---

# 36. Regression Matrix

ถ้าแก้ `geometry.py`

```text
Unit tests
Bearing verification
Distance/GPS related tests
Full Sweep
```

ถ้าแก้ `calibration.py`

```text
Unit tests
Distance calibration
Distance verification
```

ถ้าแก้ `camera.py`

```text
Camera test
Frame Sync
Full Sweep
Runtime
```

ถ้าแก้ `ptz.py`

```text
PTZ test
Frame Sync
Full Sweep
Runtime
```

ถ้าแก้ `detection.py`

```text
Model inspection
Unit tests
Live detection
Stability
Full Sweep
```

ถ้าแก้ `notify.py`

```text
Telegram test
Runtime alert test
```

ถ้าแก้ `app.py`

```text
Dashboard test
API test
Dashboard service test
```

ถ้าแก้ `config.py`

```text
Offline Preflight
Tests ของค่าที่แก้
Full Preflight
```

ถ้าแก้ systemd

```text
systemd-analyze verify
Service start
Service stop
Service restart
Reboot test
```

---

# 37. Production Boundary

การที่

```text
Unit Test PASS
หรือ
main.py เปิดได้
```

ไม่ได้แปลว่า Production Ready

Production ต้องผ่าน

```text
Production Benchmark
Hardware Test
Site Calibration
Verification
Full Preflight
Full Sweep
Service Test
Reboot Test
```

---

# 38. Git Safety

ก่อน Commit

```bash
git status
git diff --check
```

ตรวจว่าไม่มี

```text
.env
production.env
Camera Password
Telegram Token
Site GPS
models/fire.pt
Calibration output ที่ไม่ควรเผยแพร่
```

อยู่ใน Staged Files

---

# 39. Production Service Ownership

Production runtime user

```text
smartfire
```

Runtime directories ที่ต้องเขียนได้

```text
static/
calibration/
```

Environment file ควรได้รับการป้องกันและไม่ควรเปิดสิทธิ์โดยไม่จำเป็น

---

# 40. Dashboard Security

`app.py` ปัจจุบันไม่มี Login/Authentication

ดังนั้น Port

```text
5000
```

ควรใช้ใน Trusted/Internal Network

อย่า expose โดยตรงสู่ Public Internet จนกว่าจะเพิ่ม Authentication/Reverse Proxy/TLS ตาม Deployment requirements

---

# 41. Developer Final Checklist

ก่อนส่ง Code ใหม่

```text
[ ] Unit Tests PASS
[ ] Offline Preflight FAIL=0
[ ] ไม่มี Secret ใน Git
[ ] Regression tests ของ Module ที่แก้ PASS
[ ] Documentation Update แล้ว
[ ] Full Sweep PASS ถ้าแก้ Runtime critical path
[ ] Production deployment docs ยังตรงกับ Code
```

---

# 42. Documentation Responsibilities

```text
README.md
= Project overview / Quick Start

DEVELOPER_GUIDE.md
= Source architecture / Development rules

TESTING.md
= Test procedure / Acceptance criteria

PRODUCTION_DEPLOYMENT_GUIDE.md
= Installation / Commissioning / Operations
```

อย่าเขียนข้อมูลเดียวกันแบบขัดกันระหว่างเอกสาร

เมื่อ Architecture เปลี่ยน ต้องแก้เอกสารที่เกี่ยวข้องพร้อมกัน
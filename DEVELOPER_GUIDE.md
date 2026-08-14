Smart Fire Detection v2 — Developer Guide

เอกสารหลักสำหรับนักพัฒนา: เริ่มตั้งแต่ Clone โปรเจกต์ครั้งแรก, ตั้งค่าเครื่อง, ทดสอบ Hardware/AI, Calibration, Human Review, เก็บ Hard Negative Dataset, ไปจนถึงการรันระบบจริงและพัฒนาต่อ

หลักสำคัญ: อย่าเริ่มด้วย python main.py บนเครื่องหรือสถานที่ติดตั้งใหม่ ควรทดสอบแต่ละ Layer ก่อน เพื่อแยกปัญหา Camera / PTZ / AI / Calibration / Geometry / Notification ให้ชัดเจน

1. เป้าหมายของระบบ

Smart Fire Detection v2 ใช้กล้อง PTZ + AI เพื่อตรวจจับ Fire และ Smoke ตามจุด Preset รอบพื้นที่ แล้วคำนวณ:

PTZ Preset
  ↓
Fresh RTSP Frame
  ↓
Stable Frame
  ↓
AI Detection
  ↓
Multi-frame + Spatial/IoU Consensus
  ↓
Pixel X → Bearing
  ↓
Pixel Y → Distance
  ↓
Bearing + Distance → GPS (เฉพาะช่วง Distance ที่ผ่าน Calibration)
  ↓
Annotated Image / Dashboard / Telegram

Preset ปัจจุบัน:

1 =   0.0°  N
2 =  45.0°  NE
3 =  90.0°  E
4 = 135.0°  SE
5 = 177.5°
6 = 315.0°  NW
7 = 270.0°  W
8 = 225.0°  SW
9 = 182.5°

Sweep sequence:

1 → 2 → 3 → 4 → 5 → 4 → 3 → 2 → 1
  → 6 → 7 → 8 → 9 → 8 → 7 → 6 → 1

2. โครงสร้างไฟล์

smart-fire-detection-v2/
├── README.md
├── DEVELOPER_GUIDE.md
├── TESTING.md
│
├── main.py
├── app.py
│
├── config.py
├── camera.py
├── ptz.py
├── detection.py
├── geometry.py
├── calibration.py
├── overlay.py
├── notify.py
│
├── inspect_model.py
├── export_openvino.py
│
├── calibrate_bearing.py
├── calibrate_distance.py
├── verify_distance.py
├── verify_bearing.py
│
├── test_camera.py
├── test_ptz.py
├── test_ptz_frame_sync.py
├── test_detection_live.py
├── test_detection_stability.py
├── test_full_sweep.py
├── test_telegram.py
│
├── collect_hard_negatives.py
├── review_hard_negatives.py
├── prepare_hard_negative_addon.py
│
├── requirements.txt
├── .env.example
│
├── models/
├── calibration/
├── static/
└── tests/

3. เริ่มจากศูนย์ — Clone และ Setup

3.1 Clone

git clone <REPOSITORY_URL>
cd smart-fire-detection-v2

ตรวจสอบว่าอยู่ใน root ที่มี:

main.py
config.py
requirements.txt
models/
calibration/
static/

3.2 Python

แนะนำ Python 3.12

Windows

py -0p
py -3.12 -m venv venv
venv\Scripts\activate
python --version

Linux / Ubuntu

python3.12 -m venv venv
source venv/bin/activate
python --version

3.3 ติดตั้ง Dependencies

python -m pip install --upgrade pip
pip install -r requirements.txt

ทดสอบ import:

python -c "import cv2, numpy, ultralytics, flask, requests; print('dependencies OK')"

4. Configuration

ไฟล์ .env.example เป็นตัวอย่างค่าที่ต้องตั้ง แต่ โค้ดปัจจุบันอ่านด้วย os.getenv() โดยตรง และยังไม่ได้เรียก python-dotenv/load_dotenv()

ดังนั้นการสร้าง .env อย่างเดียว ยังไม่ได้หมายความว่าโปรแกรมจะโหลดค่าอัตโนมัติ

วิธี A — ตั้ง Environment Variables จาก OS/Shell

Windows CMD

set CAMERA_IP=192.168.x.x
set CAMERA_USER=admin
set CAMERA_PWD=YOUR_PASSWORD
set CAMERA_LAT=YOUR_LATITUDE
set CAMERA_LON=YOUR_LONGITUDE
set MODEL_PATH_PT=models/fire.pt

PowerShell

$env:CAMERA_IP="192.168.x.x"
$env:CAMERA_USER="admin"
$env:CAMERA_PWD="YOUR_PASSWORD"
$env:CAMERA_LAT="YOUR_LATITUDE"
$env:CAMERA_LON="YOUR_LONGITUDE"
$env:MODEL_PATH_PT="models/fire.pt"

Linux

export CAMERA_IP="192.168.x.x"
export CAMERA_USER="admin"
export CAMERA_PWD="YOUR_PASSWORD"
export CAMERA_LAT="YOUR_LATITUDE"
export CAMERA_LON="YOUR_LONGITUDE"
export MODEL_PATH_PT="models/fire.pt"

วิธี B — พัฒนาต่อให้โหลด .env

หากต้องการ workflow แบบ .env ปกติ ให้เพิ่ม python-dotenv และเรียก load_dotenv() ก่อนโหลดค่า config

ห้าม Commit .env, Camera Password, Telegram Token หรือ Secret จริงเข้า Git

ค่าที่ควรตั้งให้ถูก Site:

CAMERA_IP
CAMERA_PORT
CAMERA_USER
CAMERA_PWD
RTSP_PORT
RTSP_PATH
CAMERA_LAT
CAMERA_LON
HFOV_DEG
MODEL_BACKEND
MODEL_PATH_PT
MODEL_PATH_OPENVINO
INFERENCE_DEVICE
IMGSZ
FIRE_THRESHOLD
SMOKE_THRESHOLD
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID

5. ใส่ Model

Default path:

models/fire.pt

ตรวจ Model:

python inspect_model.py

ควรเห็น class ที่ระบบ map ได้ เช่น:

Fire
Smoke

Model ที่ใช้ Integration Test ไม่จำเป็นต้องเป็นโมเดล Final แต่ class interface ต้องเข้ากับระบบ

6. Test Pipeline มาตรฐานก่อนใช้งาน

Unit Tests
   ↓
Model Inspection
   ↓
RTSP Camera
   ↓
PTZ
   ↓
PTZ + Fresh Frame + Stability
   ↓
Bearing Calibration
   ↓
Distance Calibration
   ↓
Distance Verification
   ↓
Bearing Verification (Optional)
   ↓
Live Detection ทุก Preset
   ↓
Human Review / Hard Negative Mining (Optional แต่แนะนำ)
   ↓
Full Sweep
   ↓
Telegram
   ↓
Runtime
   ↓
Dashboard

7. Unit Tests

python -m unittest discover -s tests -v

ต้องไม่มี FAILED หรือ ERROR

8. RTSP Camera Test

python test_camera.py

ตรวจ:

frame sequence เพิ่มขึ้น
frame age ต่ำ
resolution ถูกต้อง
ภาพล่าสุดไม่ค้าง

Output:

static/camera_test.jpg

9. PTZ Test

python test_ptz.py

ตรวจด้วยสายตาว่า Preset ไปถูกทิศจริง อย่าดูแค่ HTTP success

10. PTZ + Fresh Frame + Stability

python test_ptz_frame_sync.py

ต้องเห็น:

seq before move
PTZ wait
seq after movement
fresh seq
STABLE

ภาพหลัง PTZ ต้องเป็นภาพของ Preset ใหม่ ไม่ใช่ stale frame จากทิศเดิม

11. Bearing Calibration

python calibrate_bearing.py

Output:

calibration/site.json

ทำใหม่เมื่อย้ายกล้อง หมุนฐาน หรือเปลี่ยน Orientation

12. Distance Calibration

Global Calibration

python calibrate_distance.py

ใน Global Mode โปรแกรมจะ ไม่สั่ง PTZ และจะใช้มุมกล้องปัจจุบัน
ก่อนเริ่ม โปรแกรมจะให้ผู้พัฒนายืนยันว่ากล้องอยู่ในตำแหน่งที่ต้องการ และตรวจ Fresh+Stable Frame ก่อน Calibration

ขั้นต่ำ 3 จุด แนะนำ 5–8 จุด กระจายครอบคลุม Working Range

โปรแกรมจะ:

ยืนยัน Fresh + Stable Frame
→ ถ่ายภาพ
→ อ่าน Y pixel ของจุดล่างสุดที่วัตถุสัมผัสพื้น
→ Least-Squares Fit
→ บันทึก H/K
→ บันทึก min/max calibrated range อัตโนมัติ

Output:

calibration/distance_global.json

Per-Preset Calibration

หากพื้นที่แต่ละทิศมีระดับพื้น/ความลาดชันต่างกัน สามารถ Calibration แยก Preset ได้:

python calibrate_distance.py --preset 4

เมื่อระบุ --preset N โปรแกรมจะทำอัตโนมัติ:

สั่ง PTZ → Preset N
→ รอเวลาหมุน
→ ข้ามเฟรมช่วงเคลื่อนที่
→ รอ Fresh Frame
→ ตรวจ Stable Frame
→ เริ่ม Distance Calibration
→ บันทึก calibration/distance_preset_NN.json

ดังนั้นไม่ต้องหมุนกล้องไป Preset ด้วยมือก่อนรัน

ระบบ Detection จะเลือก Per-Preset Calibration เมื่อมีไฟล์ของ Preset นั้น และ fallback ไป Global Calibration เมื่อไม่มีไฟล์เฉพาะ Preset

หากย้ายกล้อง เปลี่ยนความสูง เปลี่ยนมุมก้ม/เงย หรือสภาพพื้นที่เปลี่ยน ควร Calibration ใหม่

13. Distance Verification

ใช้ระยะที่ไม่ได้ใช้ตอน Calibration

python verify_distance.py

ดู:

MAE
RMSE
MAPE
Max Error

เกณฑ์เบื้องต้น:

≤ 5%     ดีมาก
5–10%    ดี
10–15%   พอใช้
> 15%    ควรตรวจ Calibration ใหม่

14. Bearing Verification — Optional

python verify_bearing.py --preset 1

ใช้ตรวจ Actual Bearing เทียบ Calculated Bearing

ขั้นนี้ไม่จำเป็นต่อ Runtime แต่แนะนำสำหรับงานวิจัยหรือ Site ที่ต้องการความแม่นยำตำแหน่งสูง

15. Live AI Integration Test ทุก Preset

python test_detection_live.py --preset 1
python test_detection_live.py --preset 2
python test_detection_live.py --preset 3
python test_detection_live.py --preset 4
python test_detection_live.py --preset 5
python test_detection_live.py --preset 6
python test_detection_live.py --preset 7
python test_detection_live.py --preset 8
python test_detection_live.py --preset 9

Output:

static/detection_runs/

ภาพ annotated จะแสดง class, confidence, bbox, bearing, distance quality และ GPS ถ้าระยะอยู่ใน calibrated range

16. Pre-Deployment Preset Review — Optional แต่แนะนำ

ขั้นนี้เป็น Optional Quality Gate

Runtime สามารถทำงานได้แม้ไม่ทำ แต่ก่อน Deploy Site ใหม่หรือหลังเปลี่ยน Model แนะนำให้ทดสอบทุก Preset และให้คนตรวจผลจริง

สำหรับ Preset 1–9:

1. รัน Detection
2. เปิด annotated image
3. ให้คนตรวจว่า AI ตรวจถูกหรือไม่
4. ถ้าเป็น Positive จริง → ผ่าน
5. ถ้า AI ตรวจพบแต่ไม่ใช่ Fire/Smoke จริง → False Positive Candidate
6. นำ False Positive ไป Hard Negative Review
7. Export เป็น Negative Dataset สำหรับ Train รอบอนาคต

Checklist:

Preset 1   PASS / FALSE POSITIVE / NO TARGET
Preset 2   PASS / FALSE POSITIVE / NO TARGET
Preset 3   PASS / FALSE POSITIVE / NO TARGET
Preset 4   PASS / FALSE POSITIVE / NO TARGET
Preset 5   PASS / FALSE POSITIVE / NO TARGET
Preset 6   PASS / FALSE POSITIVE / NO TARGET
Preset 7   PASS / FALSE POSITIVE / NO TARGET
Preset 8   PASS / FALSE POSITIVE / NO TARGET
Preset 9   PASS / FALSE POSITIVE / NO TARGET

ขั้นนี้ใช้หา failure pattern ของ Model ใน Site จริง ไม่ใช่การแทน validation dataset ของ Model หลัก

17. Detection Stability Test — Optional / Diagnostic

กรณีภาพคล้ายเดิมแต่ AI บางครั้งเจอ บางครั้งไม่เจอ:

python test_detection_stability.py --preset 1 --samples 30 --gap 0.25 --diag-conf 0.05 --label positive_fire

Known negative scene:

python test_detection_stability.py --preset 4 --samples 30 --gap 0.25 --diag-conf 0.05 --label hard_negative

ใช้ดู confidence distribution, production pass rate, bbox IoU, inference time, frame age และ seq delta

18. Hard Negative Feedback Loop

Model ตรวจ Candidate
       ↓
คนตรวจภาพจริง
       ↓
ไม่ใช่ Fire/Smoke จริง
       ↓
TRUE NEGATIVE
       ↓
Export Hard Negative Dataset
       ↓
เก็บเป็น Batch
       ↓
นำไปรวมกับ Dataset หลักในการ Train รอบถัดไป

18.1 Collect Candidate — Preset เดียว

python collect_hard_negatives.py --mode fixed --preset 4 --samples 100 --gap 0.30 --diag-conf 0.05 --min-save-conf 0.30 --scene-label preset4_false_positive

18.2 Collect ทุก Preset

python collect_hard_negatives.py --mode sweep --cycles 1 --samples-per-preset 5 --gap 0.30 --diag-conf 0.05 --min-save-conf 0.30 --scene-label predeploy_all_presets

Output:

static/hard_negative_runs/<RUN_NAME>/

19. Human Review — ต้องทำก่อนสร้าง Negative Dataset

ห้ามนำ Candidate ที่ AI ตรวจมาเป็น Negative อัตโนมัติ

python review_hard_negatives.py --run-dir "static/hard_negative_runs/<RUN_NAME>"

เปิด:

http://127.0.0.1:5055

Label:

N = true_negative
    ไม่มี Fire/Smoke จริง
    → ใช้เป็น Hard Negative ได้

F = actual_fire
    มี Fire จริง
    → ห้ามใส่ Negative

S = actual_smoke
    มี Smoke จริง
    → ห้ามใส่ Negative

X = discard
    ภาพซ้ำ / ไม่ชัด / ตัดสินไม่ได้

Human Review เป็นข้อบังคับก่อน Export Negative Dataset

20. Export Negative Dataset

python prepare_hard_negative_addon.py --run-dir "static/hard_negative_runs/<RUN_NAME>" --output "negative_datasets/batch_001_<DESCRIPTION>"

โครงสร้าง:

negative_datasets/
└── batch_001_light_person/
    ├── images/
    │   └── train/
    ├── labels/
    │   └── train/
    ├── hard_negative_manifest.csv
    ├── summary.json
    └── README.txt

สำหรับ True Negative ให้เก็บภาพเต็มเป็น background image และ ห้ามนำ bbox ที่ Model ทำนายผิดไปทำ Ground Truth

ตัวอย่างคนถูก AI ทำนายว่า Smoke:

ถูก: ภาพเต็ม + ไม่มี Smoke annotation
ผิด: สร้าง Smoke bbox รอบคน

21. การเก็บ Negative Dataset ระยะยาว

negative_datasets/
├── batch_001_light_person/
├── batch_002_vehicle_lights/
├── batch_003_reflection/
├── batch_004_cloud_fog/
└── ...

ควรเก็บ manifest.csv และ summary.json เพื่อ trace Model version, confidence, preset และผล Human Review

22. Full Sweep Test

python test_full_sweep.py --cycles 1

ตรวจครบ:

1,2,3,4,5,4,3,2,1,6,7,8,9,8,7,6,1

Output:

static/sweep_runs/

ตรวจทุก Step ว่า PTZ ถูก, fresh/stable, AI ทำงาน, consensus ถูก, distance quality ถูก และ GPS มีเฉพาะ calibrated range

23. Telegram Test

ตั้ง TELEGRAM_TOKEN และ TELEGRAM_CHAT_ID

python test_telegram.py

ถ้าไม่ใช้ Telegram สามารถข้ามได้

24. Runtime

หลัง tests ผ่าน:

python main.py

ตรวจ RTSP, PTZ, fresh frame, stable frame, AI, consensus, dashboard files และ exception

หยุดด้วย Ctrl+C

25. Dashboard

python app.py

เปิด:

http://<SERVER-IP>:5000

มี Latest frame, Last alert, Status และ /api/status

26. OpenVINO — Optional

python export_openvino.py

INT8:

python export_openvino.py --int8 --data <DATASET_YAML>

ควร benchmark เทียบกับ PyTorch ก่อนเลือกใช้จริง

27. Workflow สำหรับนักพัฒนาที่เข้ามาพัฒนาต่อ

ก่อนแก้:

git pull
# activate venv
pip install -r requirements.txt
python -m unittest discover -s tests -v

หลังแก้ให้ Regression Test ตาม Layer

geometry.py

Unit tests
Bearing calibration/verification
Live detection

calibration.py

Unit tests
Distance calibration
Distance verification
Live detection

camera.py

test_camera.py
test_ptz_frame_sync.py
test_full_sweep.py

ptz.py

test_ptz.py
test_ptz_frame_sync.py
test_full_sweep.py

detection.py

Unit tests
inspect_model.py
test_detection_live.py
test_detection_stability.py (ถ้าแก้ threshold/consensus)
test_full_sweep.py

เปลี่ยน Model

อย่างน้อย:

inspect_model.py
test_detection_live.py
test_full_sweep.py

แนะนำเพิ่ม:

Preset Review 1–9
Detection Stability
Hard Negative Review

28. Release Gate ก่อนใช้งานจริง

Required

[ ] Unit Tests PASS
[ ] Model Inspection PASS
[ ] RTSP Camera PASS
[ ] PTZ Presets PASS
[ ] PTZ Fresh Frame / Stability PASS
[ ] Bearing Calibration DONE
[ ] Distance Calibration DONE
[ ] Distance Verification PASS
[ ] Live Detection Integration PASS
[ ] Full Sweep PASS
[ ] Runtime Smoke Test PASS

Optional / Recommended

[ ] Bearing Verification
[ ] Detection Stability Test
[ ] Human Review ทุก Preset
[ ] Hard Negative Collection ทุก Preset
[ ] Negative Dataset Export
[ ] Telegram Test
[ ] Dashboard Test
[ ] OpenVINO Benchmark

การ Review ทุก Preset และสร้าง Negative Dataset เป็น Optional แต่แนะนำมากก่อน Deploy Site ใหม่หรือหลังเปลี่ยน Model

29. Generated Data และการล้างไฟล์

ลบได้เมื่อไม่ต้องใช้ผลทดสอบ:

static/detection_runs/
static/stability_runs/
static/sweep_runs/

static/hard_negative_runs/ ลบได้เมื่อ:

Review เสร็จ
→ Export ไป negative_datasets/batch_xxx
→ ตรวจ images + manifest + summary ครบ

ถ้ายังไม่ได้ Review/Export ห้ามลบ

30. Calibration Files

ควรเก็บ:

calibration/site.json
calibration/distance_global.json
calibration/distance_preset_XX.json

ภาพ helper สามารถลบได้หลังบันทึกผลและไม่ต้องตรวจย้อนหลัง:

calibration/captures/
calibration/verification/
calibration/bearing_verification/

31. Files ที่ไม่ควรลบ

Core Runtime:

main.py
config.py
camera.py
ptz.py
detection.py
geometry.py
calibration.py
overlay.py
notify.py

Developer/Calibration/Test tools ที่ยังใช้งาน:

calibrate_bearing.py
calibrate_distance.py
verify_distance.py
inspect_model.py
test_camera.py
test_ptz.py
test_ptz_frame_sync.py
test_detection_live.py
test_full_sweep.py
collect_hard_negatives.py
review_hard_negatives.py
prepare_hard_negative_addon.py

Unit Tests:

tests/

32. Files ที่ Optional แต่ยังมีประโยชน์

verify_bearing.py              # Angular validation
test_detection_stability.py    # Model confidence diagnostic
test_telegram.py               # เมื่อใช้ Telegram
export_openvino.py             # CPU/OpenVINO optimization
app.py                         # เมื่อใช้ Dashboard

ไฟล์เหล่านี้ไม่ใช่ obsolete เพียงแต่ขึ้นกับ deployment scope

33. TESTING.md

ไม่ใช่ไฟล์เสีย แต่เนื้อหาซ้ำกับ Developer Guide บางส่วน

แนะนำ:

DEVELOPER_GUIDE.md = Full onboarding / workflow
TESTING.md         = Quick testing reference

ถ้าต้องการ Single Source of Truth จริง ๆ จึงค่อยลบ TESTING.md

34. Known Issues / Technical Debt ก่อน Production Final

34.1 main.py ข้าม Preset 1 ตัวแรกของ Sweep

Runtime ปัจจุบัน initial goto_preset(1) แล้ว loop ด้วย:

for preset in SWEEP_SEQUENCE[1:]:

ดังนั้น Preset 1 ตัวแรกถูกใช้เป็น initial position แต่ไม่ได้ inference ในตำแหน่งแรกของแต่ละ sweep แบบเดียวกับ test_full_sweep.py

ควรแก้ก่อน Production Final ให้ behavior ตรงกับ sequence ที่ต้องการจริง

34.2 .env ยังไม่ Auto-load

ควรเลือกอย่างใดอย่างหนึ่ง:

A. ใช้ OS Environment Variables อย่างเป็นทางการ
B. เพิ่ม python-dotenv + load_dotenv()

34.3 Credential/Site GPS ไม่ควรมีค่า Default จริงใน config.py

ก่อน Public Repo/Production release ให้เปลี่ยน Camera password, Site IP และ Site GPS เป็น placeholder หรือ required environment variable

35. Suggested Clean Layout ในอนาคต

smart-fire-detection-v2/
├── src/
├── tools/
│   ├── calibration/
│   ├── diagnostics/
│   ├── hard_negative/
│   └── migrations/
├── tests/
│   ├── unit/
│   └── integration/
├── models/
├── calibration/
├── static/
├── negative_datasets/
├── main.py
├── app.py
└── DEVELOPER_GUIDE.md

อย่า refactor layout ก่อนมี regression tests ครบ

36. Developer Checklist Template

Date:
Developer:
Git Commit:
Model Version:
Site:
OS:
Python:

SETUP
[ ] Dependencies
[ ] Environment variables
[ ] Model inspection

HARDWARE
[ ] Camera
[ ] PTZ
[ ] Fresh frame
[ ] Stability

CALIBRATION
[ ] Bearing
[ ] Distance
[ ] Distance verification
[ ] Bearing verification (optional)

AI INTEGRATION
[ ] Preset 1
[ ] Preset 2
[ ] Preset 3
[ ] Preset 4
[ ] Preset 5
[ ] Preset 6
[ ] Preset 7
[ ] Preset 8
[ ] Preset 9
[ ] Full sweep

MODEL FEEDBACK (optional)
[ ] Human review completed
[ ] False positives collected
[ ] Negative candidates reviewed
[ ] Hard-negative dataset exported
[ ] Batch archived for future training

DEPLOYMENT
[ ] Telegram
[ ] Dashboard
[ ] Runtime
[ ] Long-run test

37. หลักการสำคัญของโปรเจกต์

Software Test และ Model Quality เป็นคนละเรื่อง

Model ที่ยัง train ไม่เสร็จสามารถใช้ Integration Test ได้

ห้ามเชื่อ AI Candidate ว่าเป็น Negative โดยอัตโนมัติ — ต้อง Human Review

ห้ามใช้ False Bounding Box เป็น Ground Truth

GPS เชื่อได้เฉพาะเมื่อ Distance อยู่ใน calibrated range

ทุก Site ต้อง Calibration ใหม่

หลังเปลี่ยน Model ควรทดสอบทุก Preset

Human Review + Hard Negative Mining เป็น Optional แต่แนะนำ

Generated test data ไม่ควร Commit เข้า Git

End of Developer Guide
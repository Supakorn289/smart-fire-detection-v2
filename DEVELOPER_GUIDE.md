Developer Guide — Smart Fire Detection v2
เอกสารนี้สำหรับนักพัฒนาที่ เพิ่งเปิดโปรเจกต์ครั้งแรก และต้องการเข้าใจว่า:
ระบบประกอบด้วยอะไร
ต้องตั้งค่าอะไร
ต้องทดสอบอะไรก่อน
ไฟล์ไหนควรแก้เมื่อเกิดปัญหา
จุดใดของระบบห้ามเปลี่ยนโดยไม่ทดสอบซ้ำ
---
1. Mental Model ของระบบ
ระบบนี้ไม่ใช่แค่ YOLO + Camera
มันเป็น Pipeline หลายชั้น:
```text
                     ┌──────────────────────┐
                     │      IP Camera       │
                     │    RTSP + PTZ CGI    │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │   LatestFrameCamera  │
                     │      camera.py       │
                     └──────────┬───────────┘
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
        ┌─────────────────┐          ┌─────────────────┐
        │ PTZ Controller  │          │ Stability Check │
        │     ptz.py      │          │    camera.py    │
        └─────────────────┘          └────────┬────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ YOLO Detection  │
                                    │  detection.py   │
                                    └────────┬────────┘
                                              │
                                    3 Frames / Consensus
                                              │
                                              ▼
                          ┌─────────────────────────────────┐
                          │ Bounding Box                    │
                          │ X → Bearing                     │
                          │ Y-bottom → Distance             │
                          └───────────────┬─────────────────┘
                                          │
                                          ▼
                                  ┌──────────────┐
                                  │ geometry.py  │
                                  │ GPS Estimate │
                                  └──────┬───────┘
                                         │
                                         ▼
                              ┌────────────────────┐
                              │ Telegram + Output  │
                              │ notify.py/overlay  │
                              └────────────────────┘
```
`main.py` เป็น Orchestrator ไม่ควรย้าย logic ทุกอย่างกลับไปกองไว้ใน `main.py`
---
2. Environment ที่แนะนำ
Python
ใช้ Python 3.12 สำหรับ Development Environment เพื่อให้ตรงกับ environment ที่โปรเจกต์ใช้พัฒนาและทดสอบ
ตรวจสอบ:
```bash
python --version
```
---
3. Setup ครั้งแรก
3.1 สร้าง Virtual Environment
Windows
```bat
py -3.12 -m venv venv
venv\Scripts\activate
```
Linux
```bash
python3 -m venv venv
source venv/bin/activate
```
จากนั้น:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
Dependencies หลัก:
```text
numpy
requests
opencv-python-headless
ultralytics
psutil
Flask
```
OpenVINO เป็น Optional dependency สำหรับ optimization ภายหลัง
---
4. Configuration
Configuration ทั้งหมดอยู่ที่:
```text
config.py
```
และอ่านค่าด้วย:
```python
os.getenv(...)
```
สำคัญ: `.env.example` ไม่ได้ถูกโหลดอัตโนมัติ
ในโค้ดปัจจุบันไม่มี `load_dotenv()` ดังนั้น:
```text
.env.example
```
เป็น Template สำหรับดูชื่อ Variable เท่านั้น
การสร้าง `.env` อย่างเดียวจะไม่ทำให้ Python อ่านค่าโดยอัตโนมัติ
ต้องตั้ง Environment Variables ใน Shell/Service ที่ใช้รันโปรแกรม
---
5. Environment Variables สำคัญ
ตัวอย่างค่าที่โปรเจกต์รองรับ:
```text
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
```
Windows CMD
```bat
set CAMERA_IP=192.168.0.105
set CAMERA_USER=admin
set CAMERA_PWD=YOUR_PASSWORD
set CAMERA_LAT=18.xxxxx
set CAMERA_LON=98.xxxxx
```
PowerShell
```powershell
$env:CAMERA_IP="192.168.0.105"
$env:CAMERA_USER="admin"
$env:CAMERA_PWD="YOUR_PASSWORD"
$env:CAMERA_LAT="18.xxxxx"
$env:CAMERA_LON="98.xxxxx"
```
Linux
```bash
export CAMERA_IP='192.168.0.105'
export CAMERA_USER='admin'
export CAMERA_PWD='YOUR_PASSWORD'
export CAMERA_LAT='18.xxxxx'
export CAMERA_LON='98.xxxxx'
```
ถ้า Deploy ด้วย `systemd` ให้ตั้ง Environment ใน Service/EnvironmentFile แทนการ Export ด้วยมือทุกครั้ง
---
6. AI Model
วางโมเดลที่:
```text
models/fire.pt
```
Default config:
```text
MODEL_BACKEND=pt
MODEL_PATH_PT=models/fire.pt
```
ตรวจโมเดล:
```bash
python inspect_model.py
```
ระบบปัจจุบันรู้จัก canonical class:
```text
fire
smoke
```
และรองรับ alias เช่น:
```text
Fire
fire
flame
Smoke
smoke
```
ถ้าโมเดลมี class อื่น ระบบจะ ignore class ที่ไม่ได้ map
ก่อนเปลี่ยนโมเดลทุกครั้ง ให้รัน `inspect_model.py`
---
7. Camera Layer
ไฟล์:
```text
camera.py
```
ใช้ Thread อ่าน RTSP ต่อเนื่อง และ expose เฉพาะ Frame ล่าสุดผ่าน `LatestFrameCamera`
เหตุผล:
```text
RTSP Buffer
    ↓
ถ้าอ่านไม่ทัน
    ↓
อาจได้ภาพเก่า
```
แนวทางของโปรเจกต์:
```text
Decoder Thread
    ↓
FramePacket(seq, timestamp, frame)
    ↓
เก็บเฉพาะ packet ล่าสุด
```
ห้ามเปลี่ยนกลับเป็น `cv2.VideoCapture.read()` แบบ Sequential ใน Main Loop โดยไม่ทดสอบ stale frame ใหม่
---
8. PTZ Layer
ไฟล์:
```text
ptz.py
```
Preset Call ใช้ CGI command:
```text
Preset 1 → command 31
Preset 2 → command 33
Preset 3 → command 35
...
```
ระบบแยก:
```text
Physical Pan
```
ออกจาก:
```text
Compass Bearing
```
เพราะ Physical Pan ใช้สำหรับประเมินเวลาเดินทางของมอเตอร์ ส่วน Bearing ใช้ในการคำนวณตำแหน่งบนโลก
---
9. Fresh Frame + Stability
หลัง PTZ Move:
```text
goto_preset()
      ↓
wait_sec
      ↓
บันทึก arrival sequence
      ↓
POST_MOVE_FRESH_FRAMES
      ↓
wait_until_stable()
      ↓
AI
```
`wait_until_stable()` จะ resize ภาพเป็นขนาดเล็กและวัด Mean Absolute Difference
ค่าควบคุม:
```text
STABLE_DIFF_THRESHOLD
STABLE_REQUIRED_PAIRS
STABLE_TIMEOUT_SEC
POST_MOVE_FRESH_FRAMES
```
หากแก้ค่าเหล่านี้ ต้องรัน:
```bash
python test_ptz_frame_sync.py
```
ใหม่
---
10. Detection Layer
ไฟล์:
```text
detection.py
```
ลำดับ:
```text
YOLO Predict
   ↓
Class Mapping
   ↓
Class Threshold
   ↓
Bounding Box
   ↓
Bearing
   ↓
Distance
   ↓
GPS
```
ระบบไม่ควรแจ้งเตือนจาก Detection Frame เดียว
`main.py` จะเก็บ Detection หลายเฟรมแล้วใช้:
```text
FRAMES_PER_SCAN = 3
MIN_CONFIRM_FRAMES = 2
```
หลักการ:
```text
Frame 1 = Fire
Frame 2 = Fire
Frame 3 = no detection

→ Confirm Fire
```
---
11. Bearing Calculation
ไฟล์:
```text
geometry.py
```
ใช้ Horizontal Pinhole Projection:
```text
Bounding Box Center X
      ↓
Pixel Offset จาก Principal Center
      ↓
Angular Offset
      ↓
Preset Bearing
      +
North Offset
      ↓
Final Bearing
```
อย่าแทนกลับด้วย `HFOV / frame_width` แบบ linear โดยไม่ Verify ใหม่
---
12. Distance Calculation
Distance Model:
```text
y = H + K/Z
```
แก้กลับเป็น:
```text
Z = K/(y-H)
```
โดย:
```text
Y = ขอบล่างของ Bounding Box
```
Calibration fit ด้วย Least Squares และต้องมีอย่างน้อย 3 จุด
แนะนำให้ใช้หลายระยะครอบคลุม Working Range
ตัวอย่าง:
```text
6 m
8 m
10 m
```
แต่ในการติดตั้งจริงควรใช้ 5-8 จุดถ้าพื้นที่รองรับ
---
13. Calibration Files
Global Distance:
```text
calibration/distance_global.json
```
Site/North:
```text
calibration/site.json
```
Preset-specific Distance ถ้ามี:
```text
calibration/distance_preset_01.json
calibration/distance_preset_02.json
...
```
ห้ามถือว่า Calibration จากเครื่องอื่นใช้ได้
Calibration ผูกกับ:
ตำแหน่งกล้อง
ความสูง
Tilt
Resolution
HFOV
ลักษณะพื้น
ตำแหน่ง Preset
ถ้าย้ายกล้อง ควรถือว่า Calibration ต้องตรวจใหม่
---
14. Distance Calibration Workflow
รัน:
```bash
python calibrate_distance.py
```
โปรแกรมจะ:
```text
ถามระยะจริง
    ↓
ถ่ายภาพจาก RTSP
    ↓
บันทึกภาพ
    ↓
Windows: เปิด Paint
Linux: เปิดภาพด้วยโปรแกรมภายนอก
    ↓
อ่าน Y ของจุดสัมผัสพื้น
    ↓
Fit H/K
    ↓
Save JSON
```
จุดที่ใช้คือ:
```text
"จุดล่างสุดที่วัตถุสัมผัสพื้น"
```
ไม่ใช่ Center ของ Bounding Box
---
15. Distance Verification
หลัง Calibration:
```bash
python verify_distance.py
```
ต้องใช้ระยะที่ ไม่ได้ใช้สร้าง Calibration
ตัวอย่าง:
```text
Calibration:
6, 8, 10 m

Verification:
7, 9 m
```
อย่าใช้ผล fit จาก Training Points มาเรียกว่า Verification Accuracy
---
16. Bearing Calibration
รัน:
```bash
python calibrate_bearing.py
```
Preset 1 คือ Reference Center
โปรแกรมจะถาม:
```text
Bearing จริงของจุดกลางภาพ
```
แล้วบันทึก:
```text
north_offset_deg
```
---
17. Bearing Verification
รัน:
```bash
python verify_bearing.py
```
ขั้นนี้เป็น Verification
การไม่รันไม่ได้ทำให้ `main.py` ใช้งานไม่ได้ แต่จะทำให้ไม่มีข้อมูลเชิงทดลองว่า Pixel → Bearing มี Error จริงเท่าไร
ดังนั้น:
```text
Runtime Required       : ไม่บังคับ
Research Validation    : แนะนำ
```
---
18. GPS Estimation
GPS เป้าหมายคำนวณจาก:
```text
Camera Latitude/Longitude
+
Estimated Distance
+
Estimated Bearing
```
ดังนั้นความคลาดเคลื่อนสุดท้ายสะสมจาก:
```text
Camera GPS Error
+
Bearing Error
+
Distance Error
+
Detection Bounding Box Error
```
อย่าระบุพิกัดที่คำนวณได้ว่าเป็น GPS measurement โดยตรง ให้เรียกว่า:
```text
Estimated Target Location
```
---
19. Telegram
ไฟล์:
```text
notify.py
```
ทำงานผ่าน Background Worker Queue เพื่อไม่ให้ HTTP Request ไป block Scan Loop
ถ้าไม่ได้ตั้ง:
```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```
ระบบจะ Disable Telegram และแจ้งใน Console
ทดสอบ:
```bash
python test_telegram.py
```
---
20. Dashboard
รัน:
```bash
python app.py
```
เปิด:
```text
http://<SERVER-IP>:5000
```
แสดง:
```text
Latest Frame
Last Alert
Status JSON
```
Dashboard อ่านข้อมูลที่ `main.py` สร้างไว้ใน `static/`
---
21. Main Runtime
`main.py` ทำงานประมาณนี้:
```text
Start Camera
   ↓
Load AI
   ↓
Init PTZ
   ↓
Init Telegram Worker
   ↓
Goto Preset 1
   ↓
for preset in SWEEP_SEQUENCE:
       ↓
   PTZ Move
       ↓
   Fresh Frame
       ↓
   Stable Frame
       ↓
   AI Multi-Frame
       ↓
   Consensus
       ↓
   Overlay
       ↓
   Dashboard
       ↓
   Telegram
```
---
22. ลำดับ Debug เมื่อมีปัญหา
อย่าเริ่ม Debug ที่ `main.py` ก่อน
ใช้ลำดับนี้:
กล้องไม่มีภาพ
```bash
python test_camera.py
```
ตรวจ:
```text
CAMERA_IP
CAMERA_USER
CAMERA_PWD
RTSP_PORT
RTSP_PATH
Network
```
กล้องไม่หมุน
```bash
python test_ptz.py
```
ตรวจ:
```text
CAMERA_PORT
CGI endpoint
Preset ที่บันทึกในกล้อง
```
หมุนแล้วภาพยังเป็นมุมเก่า
```bash
python test_ptz_frame_sync.py
```
ตรวจ:
```text
POST_MOVE_FRESH_FRAMES
STABLE_DIFF_THRESHOLD
DEG_PER_SEC
PTZ_BUFFER_SEC
```
AI โหลดไม่ได้
```bash
python inspect_model.py
```
ตรวจ:
```text
models/fire.pt
MODEL_BACKEND
MODEL_PATH_PT
Ultralytics installation
```
ระยะผิด
```bash
python verify_distance.py
```
ถ้า Error สูง:
```text
ตรวจ Y pixel
ตรวจ Tilt
ตรวจว่ากล้องถูกขยับหรือไม่
ทำ Calibration ใหม่
```
Telegram ไม่ส่ง
```bash
python test_telegram.py
```
ตรวจ:
```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
Internet
```
---
23. สิ่งที่ Developer ไม่ควรทำ
อย่า Hard-code Password/Token ลง Git
อย่า Commit `venv/`
อย่า Commit AI weight ถ้า Repository ไม่ได้ตั้งใจเก็บ Large File
อย่าใช้ Calibration ของ Site หนึ่งกับอีก Site โดยไม่ Verify
อย่าแก้ Preset Bearing แล้วไม่ทดสอบ PTZ
อย่าแก้ HFOV แล้วใช้ Calibration เดิมทันที
อย่าตัด Fresh Frame/Stability Layer เพื่อให้ระบบ "เร็วขึ้น"
อย่าเปลี่ยน Consensus เป็น Single-frame Alert โดยไม่มีการทดสอบ False Positive
อย่าถือ Smoke Distance ว่าแม่นเท่ากับ Ground-contact Object
อย่าทดสอบระบบด้วยการสร้างเหตุเพลิงไหม้จริงเพื่อ Debug ซอฟต์แวร์ ใช้ภาพ/วิดีโอทดสอบหรือชุดข้อมูลที่ปลอดภัยแทน
---
24. Definition of Ready
เครื่อง/สถานที่ใหม่พร้อมรัน `main.py` เมื่อ:
```text
[PASS] Unit Tests
[PASS] Model Inspection
[PASS] RTSP Camera
[PASS] PTZ Presets
[PASS] PTZ + Fresh Frame
[PASS] Image Stability
[PASS] Bearing Calibration
[PASS] Distance Calibration
[PASS] Distance Verification
[PASS/OPTIONAL] Bearing Verification
[PASS/OPTIONAL] Telegram
```
จากนั้นค่อย:
```bash
python main.py
```
---
25. จุดเริ่มต้นสำหรับ Developer ใหม่
วันแรกให้ทำแค่นี้:
```text
1. อ่าน README.md
2. สร้าง venv
3. pip install
4. ตั้ง Environment Variables
5. วาง models/fire.pt
6. รัน Unit Tests
7. รัน inspect_model.py
8. รัน test_camera.py
9. รัน test_ptz.py
10. อ่าน TESTING.md ก่อนทำ Calibration
```
ถ้าทั้ง 10 ข้อนี้ผ่านแล้ว จึงเริ่มแก้หรือพัฒนา Feature ต่อ
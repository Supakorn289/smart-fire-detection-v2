Testing Guide — Smart Fire Detection v2
เอกสารนี้กำหนด ลำดับทดสอบมาตรฐาน สำหรับเครื่องหรือสถานที่ติดตั้งใหม่
> หลักสำคัญ: อย่ารัน `main.py` เป็น Test แรก  
> แต่ละ Layer ต้องผ่านแยกกันก่อน เพื่อให้รู้ว่าปัญหาเกิดที่ Camera, PTZ, AI, Geometry, Calibration หรือ Notification
---
Test Order
```text
T01 Unit Tests
 ↓
T02 Model Inspection
 ↓
T03 RTSP Camera
 ↓
T04 PTZ Presets
 ↓
T05 PTZ + Fresh Frame + Stability
 ↓
T06 Bearing Calibration
 ↓
T07 Distance Calibration
 ↓
T08 Distance Verification
 ↓
T09 Bearing Verification (Optional)
 ↓
T10 Telegram
 ↓
T11 Full Runtime
 ↓
T12 Dashboard
```
---
T01 — Unit Tests
รัน:
```bash
python -m unittest discover -s tests -v
```
ต้องไม่มี:
```text
FAILED
ERROR
```
ถ้า Unit Test ไม่ผ่าน ห้ามไปต่อที่ Hardware Test
ไฟล์ที่เกี่ยวข้อง:
```text
tests/test_geometry.py
tests/test_calibration.py
geometry.py
calibration.py
```
---
T02 — Inspect AI Model
ก่อนรัน:
```text
models/fire.pt
```
ต้องมีอยู่จริง
รัน:
```bash
python inspect_model.py
```
ตัวอย่างผลที่ยอมรับได้:
```text
Classes:
Fire
Smoke
```
ชื่ออาจต่างเรื่องตัวพิมพ์ใหญ่/เล็กได้ถ้า alias mapping รองรับ
ถ้าไม่มี `fire` หรือ `smoke` ที่ระบบ map ได้ ต้องตรวจ `CLASS_ALIASES`
---
T03 — RTSP Camera
รัน:
```bash
python test_camera.py
```
Expected:
```text
ได้รับ Frame ต่อเนื่อง
shape ตรงกับ FRAME_WIDTH x FRAME_HEIGHT
age ต่ำและไม่ค้าง
```
โปรแกรมจะสร้าง:
```text
static/camera_test.jpg
```
เปิดภาพแล้วตรวจว่าเป็นภาพล่าสุดจริง
ถ้า Fail ให้หยุดตรงนี้ก่อน
---
T04 — PTZ Preset
รัน:
```bash
python test_ptz.py
```
ตรวจด้วยสายตาว่า Preset:
```text
1 2 3 4 5 4 3 2 1 6 7 8 9 8 7 6 1
```
ไปยังตำแหน่งที่กำหนดจริง
อย่าดูแค่:
```text
HTTP 200
```
เพราะ HTTP Success ไม่ได้ยืนยันว่าตำแหน่งภาพถูกต้อง
---
T05 — PTZ + Fresh Frame + Stability
รัน:
```bash
python test_ptz_frame_sync.py
```
ต้องเห็น:
```text
seq before move
seq after movement
fresh seq
STABLE
```
และ `fresh seq` / `stable seq` ต้องใหม่กว่าช่วงก่อนกล้องหมุน
ไฟล์ภาพจะถูกเก็บใน:
```text
static/sync_preset_*.jpg
```
เปิดตรวจด้วยสายตาว่าแต่ละภาพตรงกับ Preset จริง
Pass Criteria:
```text
PTZ command success
Fresh frame success
Stable frame success
ภาพไม่ใช่ทิศเก่า
```
---
T06 — Bearing Calibration
Preset 1 ต้องใช้เป็น Reference
รัน:
```bash
python calibrate_bearing.py
```
วัด Bearing จริงของจุดกึ่งกลางภาพ แล้วป้อนค่า 0-360°
ระบบจะบันทึก:
```text
calibration/site.json
```
ถ้าย้ายกล้องหรือเปลี่ยน Orientation ต้องทำขั้นนี้ใหม่
---
T07 — Distance Calibration
รัน:
```bash
python calibrate_distance.py
```
ใช้วัตถุอ้างอิงที่ปลอดภัยและเห็นจุดสัมผัสพื้นได้ชัด
ขั้นต่ำ:
```text
3 จุด
```
แนะนำ:
```text
5-8 จุด
```
ระยะควรกระจายครอบคลุม Working Range
โปรแกรมจะ:
```text
Capture RTSP
→ Save image
→ อ่าน Y
→ Least-Squares Fit
→ Save H/K
```
Global output:
```text
calibration/distance_global.json
```
หลักการอ่าน Y:
```text
ใช้จุดล่างสุดที่วัตถุสัมผัสพื้น
```
ไม่ใช้:
```text
Bounding Box Center
```
---
T08 — Distance Verification
ใช้ระยะที่ไม่ได้ใช้ตอน Calibration
ตัวอย่าง:
```text
Calibration = 6, 8, 10 m
Verification = 7, 9 m
```
รัน:
```bash
python verify_distance.py
```
ดู:
```text
MAE
RMSE
MAPE
Max Error
```
แนวทางตีความในสคริปต์ปัจจุบัน:
```text
≤ 5%     ดีมาก
≤ 10%    ดี
≤ 15%    พอใช้
> 15%    ควรตรวจ/Calibration ใหม่
```
อย่า Verify ด้วยระยะเดียวกับ Calibration Points
---
T09 — Bearing Verification
Optional สำหรับ Runtime แต่แนะนำสำหรับงานวิจัย
รัน:
```bash
python verify_bearing.py
```
เป้าหมายคือวัด:
```text
Actual Bearing
vs
Calculated Bearing
```
ถ้าข้ามขั้นนี้:
```text
main.py ยังทำงานได้
```
แต่จะไม่มี Angular Error จากการทดลองจริง
---
T10 — Telegram
ตั้ง:
```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```
แล้วรัน:
```bash
python test_telegram.py
```
Expected:
```text
ข้อความทดสอบถึง Telegram
Exit Code = 0
```
ถ้าไม่ได้ใช้ Telegram สามารถข้ามได้ แต่ Runtime จะไม่มี Remote Alert
---
T11 — Full Runtime
เมื่อ T01-T08 ผ่านแล้ว:
```bash
python main.py
```
ตรวจ Console:
```text
RTSP connected
Model loaded
PTZ moves
Fresh frame
Stable image
Scan continues
ไม่มี Exception ต่อเนื่อง
```
หยุดด้วย:
```text
Ctrl+C
```
---
T12 — Dashboard
Terminal แยก:
```bash
python app.py
```
เปิด:
```text
http://<SERVER-IP>:5000
```
ตรวจ:
```text
Latest frame
Last alert
Status
```
API:
```text
/api/status
```
---
Regression Test หลังแก้โค้ด
ถ้าแก้ไฟล์นี้:
`geometry.py`
ต้องรัน:
```text
T01
T06 (ถ้า logic bearing เปลี่ยน)
T08
T09
```
`calibration.py`
ต้องรัน:
```text
T01
T07
T08
```
`camera.py`
ต้องรัน:
```text
T03
T05
T11
```
`ptz.py`
ต้องรัน:
```text
T04
T05
T11
```
`detection.py`
ต้องรัน:
```text
T02
T11
```
และทดสอบด้วยภาพ/วิดีโอจากชุดข้อมูลที่ปลอดภัย
`notify.py`
ต้องรัน:
```text
T10
T11
```
`config.py`
ให้รัน Test ที่เกี่ยวข้องกับค่าที่แก้ทั้งหมด
---
Test Result Template
ใช้บันทึกผลแต่ละเครื่อง/แต่ละ Site:
```text
Date:
Developer:
Machine:
OS:
Python:
Camera:
Model:

T01 Unit Tests            PASS / FAIL
T02 Model Inspection      PASS / FAIL
T03 RTSP Camera           PASS / FAIL
T04 PTZ                   PASS / FAIL
T05 PTZ Frame Sync        PASS / FAIL
T06 Bearing Calibration   PASS / FAIL
T07 Distance Calibration  PASS / FAIL
T08 Distance Verification PASS / FAIL
T09 Bearing Verification  PASS / SKIP / FAIL
T10 Telegram              PASS / SKIP / FAIL
T11 Runtime               PASS / FAIL
T12 Dashboard             PASS / FAIL

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
Release Gate
ก่อนนำระบบไปใช้งานภาคสนาม:
```text
T01 PASS
T02 PASS
T03 PASS
T04 PASS
T05 PASS
T06 PASS
T07 PASS
T08 PASS
T11 PASS
```
`T09` และ `T10` ขึ้นกับขอบเขตการ Deploy แต่สำหรับงานวิจัยที่ต้องรายงานความแม่นยำของตำแหน่ง แนะนำให้ทำ T09 ด้วย
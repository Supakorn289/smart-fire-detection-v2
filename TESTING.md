# ขั้นตอนทดสอบ Smart Fire Detection v2

## 0) Config / security
- เปลี่ยน Telegram token เดิมที่เคยฝังใน source แล้วใช้ token ใหม่ผ่าน environment variable.
- ตรวจ IP, password กล้อง, CAMERA_LAT/LON, HFOV_DEG.
- ตั้ง Preset 1 ให้กลางภาพชี้ North ใกล้ที่สุด.

## 1) Unit test — ยังไม่ต้องมีกล้อง/โมเดล
```bash
python -m unittest discover -s tests -v
```
ต้องผ่านทั้งหมด.

## 2) ตรวจ class โมเดล
```bash
python inspect_model.py
```
ดูชื่อ class จริง. ระบบ map เฉพาะ alias ของ `fire` และ `smoke`; class อื่นจะถูก ignore. ถ้าชื่อไม่ตรงให้เพิ่มใน `CLASS_ALIASES`.

## 3) RTSP / fresh-frame
```bash
python test_camera.py
```
เลข frame ต้องเพิ่ม และเกิด `static/camera_test.jpg`.

ทดสอบ stale frame: หมุนกล้องจากแอป แล้วตรวจว่าหลังหยุดภาพล่าสุดเปลี่ยนตามจริง ไม่ค้างเป็นภาพมุมก่อนหน้า.

## 4) PTZ 9 จุด
ตั้ง preset กล้องเป็น physical pan:
`1=0, 2=45, 3=90, 4=135, 5=177.5, 6=-45, 7=-90, 8=-135, 9=-177.5`.

```bash
python test_ptz.py
```
ต้องกวาด `1→2→3→4→5→4→3→2→1→6→7→8→9→8→7→6→1`.
ถ้ายังหมุนไม่ถึงก่อนขั้นต่อไป ให้ลด `DEG_PER_SEC` หรือเพิ่ม `PTZ_BUFFER_SEC`.

## 5) Calibration ทิศ
หัน Preset 1 แล้ววัด bearing จริงของกลางภาพ:
```bash
python calibrate_bearing.py
```
จากนั้นทดสอบกลางภาพ Preset 3 ต้องประมาณ 90° + offset.

## 6) Calibration ระยะ
ใช้ 5-8 จุด เช่น 3,5,7,9,11m. จด y pixel ของจุดล่างสุดที่สัมผัสพื้น.
```bash
python calibrate_distance.py
```
ระบบ fit `y = H + K/Z` แบบ least squares.

ตรวจด้วยจุดใหม่ที่ไม่ได้ใช้ fit:
```bash
python verify_distance.py
```
ถ้าพื้นแต่ละทิศต่างกันมาก ให้ทำแยก preset:
```bash
python calibrate_distance.py --preset 3
python verify_distance.py --preset 3
```

## 7) Telegram
```bash
python test_telegram.py
```
ต้องได้รับข้อความจริง.

## 8) AI image test
ทดสอบภาพ fire, smoke, negative, แสง/เงาสะท้อน, หมอก/ไอน้ำ. บันทึก TP/FP/FN, confidence, inference time.

## 9) Integration test
ถอด Telegram token ชั่วคราว แล้ว:
```bash
python main.py
```
ดูอย่างน้อย 3 sweep เต็ม. ต้องไม่มี AI ระหว่างหมุน; ต้องรอ fresh frame + stable frame ก่อน AI; bearing ต้องตรง preset; CPU/RAM ไม่ขึ้นจน swap ต่อเนื่อง.

Dashboard:
```bash
python app.py
```
เปิด `http://SERVER_IP:5000`.

## 10) End-to-end localization
ใช้เป้าทดสอบที่ปลอดภัย/ภาพทดสอบแทนการก่อเปลวไฟจริง. สำหรับหลาย preset และหลายระยะ บันทึก:
- bearing จริง vs predicted
- distance จริง vs predicted
- GPS predicted
- angular error / distance error

## 11) Performance i5-7500 / 4GB
รันต่อเนื่อง 30-60 นาที เก็บ CPU%, RAM%, inference time, sweep time, RTSP reconnect, false alarms.
ถ้า RAM/CPU สูง ให้ลอง IMGSZ 512 หรือ 416 แล้วเทียบ accuracy ก่อนเลือก.

## 12) OpenVINO
FP32:
```bash
python export_openvino.py
export MODEL_BACKEND=openvino
```
เทียบเวลา inference/CPU/RAM กับ `.pt`.

INT8 ต้องใช้ representative calibration dataset และต้องวัด accuracy หลัง quantization; `half=False` ไม่ใช่ INT8.

## เกณฑ์ผ่านก่อนภาคสนาม
- Unit tests ผ่าน
- PTZ 9 จุดถูกลำดับ
- ไม่มี stale-frame หลังหมุน
- bearing error อยู่ในเกณฑ์งานวิจัย
- distance validation มี error ที่วัดได้
- class mapping ถูกต้อง
- Telegram/map สอดคล้องกับค่าคำนวณ
- เครื่องไม่ค้างหรือ swap ต่อเนื่อง

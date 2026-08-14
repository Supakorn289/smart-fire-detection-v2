import os
from dataclasses import dataclass
from ultralytics import YOLO
from calibration import load_distance_model, load_north_offset_deg
from config import (MODEL_BACKEND, MODEL_PATH_PT, MODEL_PATH_OPENVINO, INFERENCE_DEVICE, IMGSZ,
                    CLASS_THRESHOLDS, CLASS_ALIASES, FRAME_WIDTH, HFOV_DEG, CAMERA_LAT, CAMERA_LON,
                    PRESET_BEARING_DEG, MIN_VALID_DISTANCE_M, MAX_VALID_DISTANCE_M)
from geometry import pixel_to_bearing, gps_from_bearing_distance

@dataclass
class Detection:
    bbox: tuple[int, int, int, int]
    model_class: str
    canonical_class: str
    confidence: float
    distance_m: float | None
    bearing_deg: float
    gps: tuple[float, float] | None
    distance_quality: str

def _norm(name: str) -> str:
    return ''.join(ch for ch in name.strip().lower().replace('_', '-') if ch.isalnum() or ch == '-')

class FireDetector:
    def __init__(self):
        model_path = MODEL_PATH_OPENVINO if MODEL_BACKEND == 'openvino' else MODEL_PATH_PT
        if not os.path.exists(model_path):
            raise FileNotFoundError(f'ไม่พบโมเดล: {model_path}')
        self.model = YOLO(model_path)
        self.names = dict(self.model.names)
        self.class_map = {}
        self.unknown_names = []
        self._build_class_map()
        if not self.class_map:
            raise RuntimeError(f'โมเดลไม่มี class fire/smoke ที่ระบบรู้จัก. พบ: {list(self.names.values())}')
        print(f'📋 Model classes: {self.names}')
        print(f'✅ Active class map: {self.class_map}')
        if self.unknown_names:
            print(f'ℹ️ Ignored model classes: {self.unknown_names}')
        self.north_offset_deg = load_north_offset_deg()

    def _build_class_map(self):
        alias = {c: {_norm(x) for x in (a | {c})} for c, a in CLASS_ALIASES.items()}
        for cls_id, name in self.names.items():
            n = _norm(str(name))
            matched = next((canonical for canonical, aliases in alias.items() if n in aliases), None)
            if matched:
                self.class_map[int(cls_id)] = matched
            else:
                self.unknown_names.append(str(name))

    def inspect(self):
        return {'all_classes': self.names, 'canonical': self.class_map, 'ignored': self.unknown_names}

    def detect(self, frame, preset: int):
        if preset not in PRESET_BEARING_DEG:
            raise ValueError(f'Unknown preset {preset}')
        results = self.model.predict(source=frame, imgsz=IMGSZ, conf=min(CLASS_THRESHOLDS.values()),
                                     device=INFERENCE_DEVICE, verbose=False)
        distance_model = load_distance_model(preset)
        out = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in self.class_map:
                    continue
                canonical = self.class_map[cls_id]
                conf = float(box.conf[0])
                if conf < CLASS_THRESHOLDS[canonical]:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                bearing = pixel_to_bearing(PRESET_BEARING_DEG[preset], (x1+x2)/2.0,
                                           FRAME_WIDTH, HFOV_DEG, self.north_offset_deg)
                distance = None
                quality = 'unavailable'
                gps = None
                if distance_model is not None:
                    est = distance_model.estimate(y2)
                    if est is not None and MIN_VALID_DISTANCE_M <= est <= MAX_VALID_DISTANCE_M:
                        distance = est
                        quality = 'low' if canonical == 'smoke' else 'estimated'
                        gps = gps_from_bearing_distance(CAMERA_LAT, CAMERA_LON, distance, bearing)
                out.append(Detection((x1,y1,x2,y2), str(self.names.get(cls_id, cls_id)), canonical,
                                     conf, distance, bearing, gps, quality))
        out.sort(key=lambda d: d.confidence, reverse=True)
        return out

def consensus(detection_sets, min_frames: int):
    if not detection_sets:
        return []
    classes = {d.canonical_class for ds in detection_sets for d in ds}
    confirmed = []
    for cls in classes:
        hits = 0
        candidates = []
        for ds in detection_sets:
            same = [d for d in ds if d.canonical_class == cls]
            if same:
                hits += 1
                candidates.extend(same)
        if hits >= min_frames and candidates:
            confirmed.append(max(candidates, key=lambda d: d.confidence))
    return sorted(confirmed, key=lambda d: d.confidence, reverse=True)

import os
from dataclasses import dataclass

from ultralytics import YOLO

from calibration import load_distance_model, load_north_offset_deg
from config import (
    MODEL_BACKEND,
    MODEL_PATH_PT,
    MODEL_PATH_OPENVINO,
    INFERENCE_DEVICE,
    IMGSZ,
    CLASS_THRESHOLDS,
    CLASS_ALIASES,
    FRAME_WIDTH,
    HFOV_DEG,
    CAMERA_LAT,
    CAMERA_LON,
    PRESET_BEARING_DEG,
    MIN_VALID_DISTANCE_M,
    MAX_VALID_DISTANCE_M,
)
from geometry import pixel_to_bearing, gps_from_bearing_distance


# Config นี้เป็น optional เพื่อให้ไฟล์ทำงานกับ config.py เดิมได้ทันที
try:
    from config import CONSENSUS_IOU_THRESHOLD
except ImportError:
    CONSENSUS_IOU_THRESHOLD = 0.30


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
    return "".join(
        ch
        for ch in name.strip().lower().replace("_", "-")
        if ch.isalnum() or ch == "-"
    )


def bbox_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    """Intersection-over-Union ของ bounding boxes 2 กล่อง."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    intersection = iw * ih

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


class FireDetector:
    def __init__(self):
        model_path = (
            MODEL_PATH_OPENVINO
            if MODEL_BACKEND == "openvino"
            else MODEL_PATH_PT
        )

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ไม่พบโมเดล: {model_path}")

        self.model = YOLO(model_path)
        self.names = dict(self.model.names)
        self.class_map = {}
        self.unknown_names = []

        self._build_class_map()

        if not self.class_map:
            raise RuntimeError(
                "โมเดลไม่มี class fire/smoke ที่ระบบรู้จัก. "
                f"พบ: {list(self.names.values())}"
            )

        print(f"📋 Model classes: {self.names}")
        print(f"✅ Active class map: {self.class_map}")

        if self.unknown_names:
            print(f"ℹ️ Ignored model classes: {self.unknown_names}")

        self.north_offset_deg = load_north_offset_deg()

    def _build_class_map(self):
        alias = {
            c: {_norm(x) for x in (a | {c})}
            for c, a in CLASS_ALIASES.items()
        }

        for cls_id, name in self.names.items():
            n = _norm(str(name))

            matched = next(
                (
                    canonical
                    for canonical, aliases in alias.items()
                    if n in aliases
                ),
                None,
            )

            if matched:
                self.class_map[int(cls_id)] = matched
            else:
                self.unknown_names.append(str(name))

    def inspect(self):
        return {
            "all_classes": self.names,
            "canonical": self.class_map,
            "ignored": self.unknown_names,
        }

    def detect(self, frame, preset: int):
        if preset not in PRESET_BEARING_DEG:
            raise ValueError(f"Unknown preset {preset}")

        results = self.model.predict(
            source=frame,
            imgsz=IMGSZ,
            conf=min(CLASS_THRESHOLDS.values()),
            device=INFERENCE_DEVICE,
            verbose=False,
        )

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

                bearing = pixel_to_bearing(
                    PRESET_BEARING_DEG[preset],
                    (x1 + x2) / 2.0,
                    FRAME_WIDTH,
                    HFOV_DEG,
                    self.north_offset_deg,
                )

                distance = None
                quality = "unavailable"
                gps = None

                if distance_model is not None:
                    est = distance_model.estimate(y2)

                    if (
                        est is not None
                        and MIN_VALID_DISTANCE_M
                        <= est
                        <= MAX_VALID_DISTANCE_M
                    ):
                        # เก็บค่า estimate เพื่อแสดงผลได้ แม้อยู่นอกช่วง
                        distance = est

                        if distance_model.is_within_calibrated_range(est):
                            quality = (
                                "calibrated-low"
                                if canonical == "smoke"
                                else "calibrated"
                            )

                            # GPS สร้างเฉพาะระยะที่อยู่ในช่วงที่เคย Calibration
                            gps = gps_from_bearing_distance(
                                CAMERA_LAT,
                                CAMERA_LON,
                                distance,
                                bearing,
                            )
                        elif distance_model.has_calibrated_range():
                            quality = (
                                "extrapolated-low"
                                if canonical == "smoke"
                                else "extrapolated"
                            )
                            gps = None
                        else:
                            # JSON calibration รุ่นเก่าที่ยังไม่มี min/max
                            quality = (
                                "unverified-range-low"
                                if canonical == "smoke"
                                else "unverified-range"
                            )
                            gps = None

                out.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        model_class=str(
                            self.names.get(cls_id, cls_id)
                        ),
                        canonical_class=canonical,
                        confidence=conf,
                        distance_m=distance,
                        bearing_deg=bearing,
                        gps=gps,
                        distance_quality=quality,
                    )
                )

        out.sort(key=lambda d: d.confidence, reverse=True)
        return out


def consensus(
    detection_sets,
    min_frames: int,
    iou_threshold: float = CONSENSUS_IOU_THRESHOLD,
):
    """
    Spatial consensus:
    - ต้องเป็น class เดียวกัน
    - ต้องมี bounding box ซ้อน/ใกล้กันตาม IoU threshold
    - track เดียวกันต้องปรากฏอย่างน้อย min_frames คนละเฟรม

    รองรับหลาย Fire/Smoke ในภาพเดียวกันได้
    """
    if not detection_sets:
        return []

    if min_frames < 1:
        raise ValueError("min_frames must be >= 1")

    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be between 0 and 1")

    tracks = []

    for frame_index, detections in enumerate(detection_sets):
        used_track_ids = set()

        # confidence สูงก่อน เพื่อให้ match ตัวที่ชัดก่อน
        ordered = sorted(
            detections,
            key=lambda d: d.confidence,
            reverse=True,
        )

        for det in ordered:
            best_track_index = None
            best_iou = 0.0

            for track_index, track in enumerate(tracks):
                if track_index in used_track_ids:
                    continue

                if track["class"] != det.canonical_class:
                    continue

                last_det = track["detections"][-1][1]
                iou = bbox_iou(last_det.bbox, det.bbox)

                if iou >= iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_track_index = track_index

            if best_track_index is None:
                tracks.append(
                    {
                        "class": det.canonical_class,
                        "detections": [(frame_index, det)],
                    }
                )
                used_track_ids.add(len(tracks) - 1)
            else:
                tracks[best_track_index]["detections"].append(
                    (frame_index, det)
                )
                used_track_ids.add(best_track_index)

    confirmed = []

    for track in tracks:
        unique_frames = {
            frame_index
            for frame_index, _ in track["detections"]
        }

        if len(unique_frames) < min_frames:
            continue

        candidates = [
            det
            for _, det in track["detections"]
        ]

        # ใช้ detection ที่ confidence สูงสุดเป็นตัวแทน
        representative = max(
            candidates,
            key=lambda d: d.confidence,
        )
        confirmed.append(representative)

    return sorted(
        confirmed,
        key=lambda d: d.confidence,
        reverse=True,
    )

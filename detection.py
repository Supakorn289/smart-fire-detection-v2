#!/usr/bin/env python3
# detection.py

"""
Smart Fire Detection v2
Final AI Model R3-E6 Detection Runtime

หน้าที่:
- ตรวจ Final PT artifact ก่อนโหลด
- โหลด Frozen Final Model
- ตรวจ Class Contract
- รับ OpenCV BGR frame โดยตรง
- รัน YOLO.predict() ตาม Final Model Contract
- แปลง Model Detection -> Canonical Detection
- คำนวณ Bearing / Distance / GPS
- ทำ Multi-frame Spatial Consensus

Final Model Runtime Contract:
    Model       : models/fire.pt
    Class 0     : fire
    Class 1     : smoke
    IMGSZ       : 768
    Candidate   : 0.25
    NMS IoU     : 0.70
    max_det     : 300
    rect        : False
    batch       : 1
    device      : cpu

IMPORTANT:
- ห้าม preprocess OpenCV frame เองก่อน YOLO.predict()
- ห้ามแก้ / save / quantize / fuse Final PT artifact
"""

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

from calibration import (
    load_distance_model,
    load_north_offset_deg,
)

from config import (
    # Final Model
    FINAL_MODEL_RELEASE,
    EXPECTED_MODEL_SHA256,
    EXPECTED_MODEL_CLASSES,

    # Backend / Runtime
    MODEL_BACKEND,
    MODEL_PATH_PT,
    INFERENCE_DEVICE,

    # Final inference contract
    IMGSZ,
    MODEL_NMS_IOU,
    MODEL_MAX_DET,
    MODEL_RECT,
    MODEL_BATCH,

    # Detection
    CLASS_THRESHOLDS,
    CLASS_ALIASES,
    CONSENSUS_IOU_THRESHOLD,

    # Frame geometry
    FRAME_WIDTH,
    FRAME_HEIGHT,
    HFOV_DEG,

    # Site / PTZ
    CAMERA_LAT,
    CAMERA_LON,
    PRESET_BEARING_DEG,

    # Distance
    MIN_VALID_DISTANCE_M,
    MAX_VALID_DISTANCE_M,

    # Final contract validator
    validate_final_model_contract,
)

from geometry import (
    pixel_to_bearing,
    gps_from_bearing_distance,
)


# ============================================================
# Detection data model
# ============================================================

@dataclass
class Detection:
    """
    Detection ที่ผ่าน Candidate Threshold แล้ว

    หมายเหตุ:
    Detection object หนึ่งตัวตรงนี้ยังไม่ได้หมายความว่า
    เป็น Alert ทันที

    Runtime flow:

        Candidate Detection
                ↓
        Multi-frame Consensus
                ↓
        Confirmed Detection
                ↓
        Alert Deduplication
                ↓
        Notification
    """

    bbox: tuple[int, int, int, int]

    model_class: str

    canonical_class: str

    confidence: float

    distance_m: float | None

    bearing_deg: float

    gps: tuple[float, float] | None

    distance_quality: str


# ============================================================
# String normalization
# ============================================================

def _norm(
    name: str,
) -> str:
    """
    Normalize model/class names
    สำหรับ compatibility mapping
    """

    return "".join(
        ch
        for ch in (
            name
            .strip()
            .lower()
            .replace(
                "_",
                "-",
            )
        )
        if (
            ch.isalnum()
            or ch == "-"
        )
    )


# ============================================================
# Model artifact SHA256
# ============================================================

def calculate_sha256(
    path: Path,
) -> str:
    """
    คำนวณ SHA256 แบบ Streaming

    ไม่แก้ไขไฟล์
    ไม่โหลดไฟล์ทั้งหมดเข้า RAM
    """

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:

        while True:

            chunk = handle.read(
                1024
                * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


# ============================================================
# Ultralytics class metadata normalization
# ============================================================

def normalize_model_names(
    names,
) -> dict[int, str]:
    """
    Ultralytics ปกติคืน model.names เป็น dict

    ฟังก์ชันนี้ normalize ให้เป็น:

        {
            0: "fire",
            1: "smoke",
        }
    """

    if isinstance(
        names,
        dict,
    ):

        normalized = {}

        for (
            class_id,
            class_name,
        ) in names.items():

            try:

                class_id = int(
                    class_id
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise RuntimeError(
                    "Invalid model class ID: "
                    f"{class_id!r}"
                ) from exc

            normalized[
                class_id
            ] = str(
                class_name
            )

        return normalized


    if isinstance(
        names,
        (
            list,
            tuple,
        ),
    ):

        return {
            index: str(
                class_name
            )
            for (
                index,
                class_name,
            ) in enumerate(
                names
            )
        }


    raise RuntimeError(
        "Unsupported model.names format: "
        f"{type(names).__name__}"
    )


# ============================================================
# GPS availability
# ============================================================

def site_coordinates_available() -> bool:
    """
    GPS ของ Camera ใช้งานได้เมื่อ
    Latitude และ Longitude เป็นค่าจริงทั้งคู่
    """

    return (
        math.isfinite(
            CAMERA_LAT
        )
        and
        math.isfinite(
            CAMERA_LON
        )
    )


# ============================================================
# Bounding Box IoU
# ============================================================

def bbox_iou(
    a: tuple[
        int,
        int,
        int,
        int,
    ],
    b: tuple[
        int,
        int,
        int,
        int,
    ],
) -> float:
    """
    Intersection-over-Union
    ของ Bounding Box 2 กล่อง
    """

    (
        ax1,
        ay1,
        ax2,
        ay2,
    ) = a

    (
        bx1,
        by1,
        bx2,
        by2,
    ) = b


    ix1 = max(
        ax1,
        bx1,
    )

    iy1 = max(
        ay1,
        by1,
    )

    ix2 = min(
        ax2,
        bx2,
    )

    iy2 = min(
        ay2,
        by2,
    )


    intersection_width = max(
        0,
        ix2 - ix1,
    )

    intersection_height = max(
        0,
        iy2 - iy1,
    )

    intersection = (
        intersection_width
        * intersection_height
    )


    area_a = (
        max(
            0,
            ax2 - ax1,
        )
        *
        max(
            0,
            ay2 - ay1,
        )
    )


    area_b = (
        max(
            0,
            bx2 - bx1,
        )
        *
        max(
            0,
            by2 - by1,
        )
    )


    union = (
        area_a
        + area_b
        - intersection
    )


    if union <= 0:

        return 0.0


    return (
        intersection
        / union
    )


# ============================================================
# Fire Detector
# ============================================================

class FireDetector:
    """
    Final R3-E6 Production Detector

    Runtime flow:

        Validate Software Contract
                ↓
        Check Final PT exists
                ↓
        SHA256 verification
                ↓
        YOLO load
                ↓
        Exact Class Contract verification
                ↓
        Ready for inference
    """

    def __init__(
        self,
    ):

        # ====================================================
        # Final Software Contract
        # ====================================================
        #
        # ป้องกัน Runtime เปิดด้วย:
        #
        # - IMGSZ ผิด
        # - threshold ผิด
        # - NMS ผิด
        # - rect ผิด
        # - backend ที่ยังไม่ Approved
        #
        # ====================================================

        validate_final_model_contract()


        # ====================================================
        # Final PT Runtime
        # ====================================================

        if (
            MODEL_BACKEND
            != "pt"
        ):

            raise RuntimeError(
                "Final R3-E6 Production Runtime "
                "requires MODEL_BACKEND=pt"
            )


        self.model_path = Path(
            MODEL_PATH_PT
        ).resolve()


        # ====================================================
        # Model exists
        # ====================================================

        if not self.model_path.is_file():

            raise FileNotFoundError(
                "Final model not found: "
                f"{self.model_path}"
            )


        # ====================================================
        # SHA256 verification BEFORE YOLO load
        # ====================================================

        self.model_sha256 = (
            calculate_sha256(
                self.model_path
            )
        )


        if (
            self.model_sha256.lower()
            !=
            EXPECTED_MODEL_SHA256.lower()
        ):

            raise RuntimeError(
                "MODEL HASH MISMATCH\n"
                f"Model   : {self.model_path}\n"
                f"Expected: {EXPECTED_MODEL_SHA256}\n"
                f"Actual  : {self.model_sha256}\n"
                "Final model artifact must not be used."
            )


        # ====================================================
        # Load Frozen Final Model
        # ====================================================

        self.model = YOLO(
            str(
                self.model_path
            )
        )


        # ====================================================
        # Model class metadata
        # ====================================================

        self.names = (
            normalize_model_names(
                self.model.names
            )
        )


        # ====================================================
        # Exact Class Contract
        # ====================================================
        #
        # Final Model:
        #
        # 0 = fire
        # 1 = smoke
        #
        # ไม่อนุญาต:
        #
        # - class เพิ่ม
        # - class หาย
        # - class order สลับ
        # - alias แทน exact Final Contract
        #
        # ====================================================

        if (
            self.names
            != EXPECTED_MODEL_CLASSES
        ):

            raise RuntimeError(
                "MODEL CLASS CONTRACT MISMATCH\n"
                f"Expected: "
                f"{EXPECTED_MODEL_CLASSES}\n"
                f"Actual  : "
                f"{self.names}"
            )


        # ====================================================
        # Canonical mapping
        # ====================================================

        self.class_map = {}

        self.unknown_names = []

        self._build_class_map()


        if (
            self.class_map
            != EXPECTED_MODEL_CLASSES
        ):

            raise RuntimeError(
                "Canonical Class Map mismatch\n"
                f"Expected: "
                f"{EXPECTED_MODEL_CLASSES}\n"
                f"Actual  : "
                f"{self.class_map}"
            )


        # ====================================================
        # Site bearing calibration
        # ====================================================

        self.north_offset_deg = (
            load_north_offset_deg()
        )


        # ====================================================
        # Startup information
        # ====================================================

        print(
            "Final AI Model loaded"
        )

        print(
            f"  Release : "
            f"{FINAL_MODEL_RELEASE}"
        )

        print(
            f"  Model   : "
            f"{self.model_path}"
        )

        print(
            f"  SHA256  : "
            f"{self.model_sha256}"
        )

        print(
            f"  Classes : "
            f"{self.names}"
        )

        print(
            f"  Backend : "
            f"{MODEL_BACKEND}"
        )

        print(
            f"  Device  : "
            f"{INFERENCE_DEVICE}"
        )

        print(
            f"  IMGSZ   : "
            f"{IMGSZ}"
        )

        print(
            f"  Conf    : "
            f"{min(CLASS_THRESHOLDS.values()):.2f}"
        )

        print(
            f"  NMS IoU : "
            f"{MODEL_NMS_IOU:.2f}"
        )

        print(
            f"  max_det : "
            f"{MODEL_MAX_DET}"
        )

        print(
            f"  rect    : "
            f"{MODEL_RECT}"
        )

        print(
            f"  batch   : "
            f"{MODEL_BATCH}"
        )


    # ========================================================
    # Class Map
    # ========================================================

    def _build_class_map(
        self,
    ):
        """
        สร้าง Canonical Class Mapping

        Final model ถูกตรวจ Exact Contract ก่อนถึงจุดนี้แล้ว

        Alias mapping คงไว้เพื่อให้ Logic กลางของระบบ
        มีโครงสร้างเดิมและสามารถตรวจ compatibility ได้
        """

        alias = {
            canonical: {
                _norm(
                    value
                )
                for value
                in (
                    aliases
                    |
                    {
                        canonical
                    }
                )
            }
            for (
                canonical,
                aliases,
            ) in CLASS_ALIASES.items()
        }


        for (
            class_id,
            name,
        ) in self.names.items():

            normalized_name = (
                _norm(
                    str(
                        name
                    )
                )
            )


            matched = next(
                (
                    canonical
                    for (
                        canonical,
                        aliases,
                    ) in alias.items()
                    if (
                        normalized_name
                        in aliases
                    )
                ),
                None,
            )


            if matched:

                self.class_map[
                    int(
                        class_id
                    )
                ] = (
                    matched
                )

            else:

                self.unknown_names.append(
                    str(
                        name
                    )
                )


    # ========================================================
    # Runtime inspection
    # ========================================================

    def inspect(
        self,
    ):
        """
        Runtime Model / Inference information

        ไม่แก้ไข Model
        """

        return {
            "release":
                FINAL_MODEL_RELEASE,

            "model_path":
                str(
                    self.model_path
                ),

            "model_sha256":
                self.model_sha256,

            "sha256_expected":
                EXPECTED_MODEL_SHA256,

            "sha256_ok":
                (
                    self.model_sha256.lower()
                    ==
                    EXPECTED_MODEL_SHA256.lower()
                ),

            "all_classes":
                self.names,

            "expected_classes":
                EXPECTED_MODEL_CLASSES,

            "class_contract_ok":
                (
                    self.names
                    ==
                    EXPECTED_MODEL_CLASSES
                ),

            "canonical":
                self.class_map,

            "ignored":
                self.unknown_names,

            "backend":
                MODEL_BACKEND,

            "device":
                INFERENCE_DEVICE,

            "imgsz":
                IMGSZ,

            "candidate_confidence":
                min(
                    CLASS_THRESHOLDS.values()
                ),

            "class_thresholds":
                dict(
                    CLASS_THRESHOLDS
                ),

            "nms_iou":
                MODEL_NMS_IOU,

            "max_det":
                MODEL_MAX_DET,

            "rect":
                MODEL_RECT,

            "batch":
                MODEL_BATCH,
        }


    # ========================================================
    # Frame Contract
    # ========================================================

    @staticmethod
    def _validate_frame(
        frame,
    ):
        """
        Final Runtime รับ OpenCV BGR Frame ดิบ

        Geometry ของระบบต้องใช้ Resolution เดียวกับ
        Calibration Configuration
        """

        if frame is None:

            raise ValueError(
                "Detection frame is None"
            )


        if not hasattr(
            frame,
            "shape",
        ):

            raise TypeError(
                "Detection frame must be "
                "an OpenCV/Numpy image"
            )


        if len(
            frame.shape
        ) != 3:

            raise ValueError(
                "Detection frame must be "
                "a 3-dimensional BGR image"
            )


        if (
            frame.shape[2]
            != 3
        ):

            raise ValueError(
                "Detection frame must contain "
                "exactly 3 BGR channels"
            )


        actual_height = int(
            frame.shape[0]
        )

        actual_width = int(
            frame.shape[1]
        )


        if (
            actual_width
            != FRAME_WIDTH
            or
            actual_height
            != FRAME_HEIGHT
        ):

            raise ValueError(
                "Detection frame resolution mismatch: "
                f"expected "
                f"{FRAME_WIDTH}x{FRAME_HEIGHT}, "
                f"got "
                f"{actual_width}x{actual_height}. "
                "Bearing/Distance calibration "
                "must not run on a different resolution."
            )


    # ========================================================
    # Detection
    # ========================================================

    def detect(
        self,
        frame,
        preset: int,
    ):
        """
        Run Final R3-E6 inference

        IMPORTANT:

        frame ถูกส่งเข้า YOLO.predict() โดยตรง

        ห้าม:
            cv2.resize เป็น 768x768 เอง
            manual letterbox
            BGR->RGB เอง
            normalize /255 เอง
            tensor conversion เอง

        Ultralytics ทำ preprocessing ภายใน
        """

        # ----------------------------------------------------
        # Preset
        # ----------------------------------------------------

        if (
            preset
            not in PRESET_BEARING_DEG
        ):

            raise ValueError(
                f"Unknown preset {preset}"
            )


        # ----------------------------------------------------
        # Raw OpenCV BGR frame contract
        # ----------------------------------------------------

        self._validate_frame(
            frame
        )


        # ----------------------------------------------------
        # Candidate confidence floor
        # ----------------------------------------------------
        #
        # Final R3-E6:
        #
        # fire  = .25
        # smoke = .25
        #
        # ใช้ min() เพื่อรักษาโครงสร้างรองรับ
        # class-specific post-filter เดิม
        #
        # ----------------------------------------------------

        candidate_confidence = min(
            CLASS_THRESHOLDS.values()
        )


        # ====================================================
        # FINAL MODEL INFERENCE CONTRACT
        # ====================================================
        #
        # Effective batch = 1
        #
        # detect() รับหนึ่ง OpenCV frame ต่อหนึ่ง call
        #
        # ไม่ส่ง MODEL_BATCH เข้า YOLO.predict()
        # เพราะ source เป็น single numpy image อยู่แล้ว
        #
        # ====================================================

        results = (
            self.model.predict(
                source=frame,

                imgsz=IMGSZ,

                conf=(
                    candidate_confidence
                ),

                iou=(
                    MODEL_NMS_IOU
                ),

                max_det=(
                    MODEL_MAX_DET
                ),

                rect=(
                    MODEL_RECT
                ),

                device=(
                    INFERENCE_DEVICE
                ),

                verbose=False,
            )
        )


        # ====================================================
        # Distance model for current preset
        # ====================================================

        distance_model = (
            load_distance_model(
                preset
            )
        )


        detections = []


        # ====================================================
        # Prediction results
        # ====================================================

        for result in results:

            if (
                result.boxes
                is None
            ):

                continue


            for box in (
                result.boxes
            ):

                # --------------------------------------------
                # Class ID
                # --------------------------------------------

                class_id = int(
                    box.cls[0]
                )


                if (
                    class_id
                    not in self.class_map
                ):

                    continue


                canonical = (
                    self.class_map[
                        class_id
                    ]
                )


                # --------------------------------------------
                # Confidence
                # --------------------------------------------

                confidence = float(
                    box.conf[0]
                )


                if not math.isfinite(
                    confidence
                ):

                    continue


                # --------------------------------------------
                # Class-specific Candidate Threshold
                # --------------------------------------------

                if (
                    confidence
                    <
                    CLASS_THRESHOLDS[
                        canonical
                    ]
                ):

                    continue


                # --------------------------------------------
                # Bounding Box
                # --------------------------------------------

                coordinates = (
                    box.xyxy[0]
                    .tolist()
                )


                if (
                    len(
                        coordinates
                    )
                    != 4
                ):

                    continue


                (
                    x1,
                    y1,
                    x2,
                    y2,
                ) = (
                    int(
                        value
                    )
                    for value
                    in coordinates
                )


                # Invalid / zero-area box
                if (
                    x2 <= x1
                    or
                    y2 <= y1
                ):

                    continue


                # --------------------------------------------
                # Bearing
                # --------------------------------------------

                center_x = (
                    x1
                    + x2
                ) / 2.0


                bearing = (
                    pixel_to_bearing(
                        PRESET_BEARING_DEG[
                            preset
                        ],

                        center_x,

                        FRAME_WIDTH,

                        HFOV_DEG,

                        self.north_offset_deg,
                    )
                )


                # --------------------------------------------
                # Distance / GPS defaults
                # --------------------------------------------

                distance = None

                quality = (
                    "unavailable"
                )

                gps = None


                # =================================================
                # Distance estimation
                # =================================================

                if (
                    distance_model
                    is not None
                ):

                    estimate = (
                        distance_model
                        .estimate(
                            y2
                        )
                    )


                    if (
                        estimate
                        is not None
                    ):

                        try:

                            estimate = float(
                                estimate
                            )

                        except (
                            TypeError,
                            ValueError,
                        ):

                            estimate = None


                    if (
                        estimate
                        is not None
                        and
                        math.isfinite(
                            estimate
                        )
                        and
                        MIN_VALID_DISTANCE_M
                        <= estimate
                        <= MAX_VALID_DISTANCE_M
                    ):

                        distance = (
                            estimate
                        )


                        # =========================================
                        # Inside calibrated distance range
                        # =========================================

                        if (
                            distance_model
                            .is_within_calibrated_range(
                                estimate
                            )
                        ):

                            quality = (
                                "calibrated-low"
                                if canonical
                                == "smoke"
                                else
                                "calibrated"
                            )


                            # -------------------------------------
                            # GPS safety
                            # -------------------------------------
                            #
                            # ห้ามสร้าง NaN coordinate
                            #
                            # Smoke ยังคง quality = calibrated-low
                            # ตาม Geometry limitation
                            #
                            # -------------------------------------

                            if (
                                site_coordinates_available()
                            ):

                                gps = (
                                    gps_from_bearing_distance(
                                        CAMERA_LAT,
                                        CAMERA_LON,
                                        distance,
                                        bearing,
                                    )
                                )


                        # =========================================
                        # Outside calibrated range
                        # =========================================

                        elif (
                            distance_model
                            .has_calibrated_range()
                        ):

                            quality = (
                                "extrapolated-low"
                                if canonical
                                == "smoke"
                                else
                                "extrapolated"
                            )

                            # Extrapolated distance
                            # ห้ามสร้าง GPS
                            gps = None


                        # =========================================
                        # Legacy calibration without range
                        # =========================================

                        else:

                            quality = (
                                "unverified-range-low"
                                if canonical
                                == "smoke"
                                else
                                "unverified-range"
                            )

                            gps = None


                # =================================================
                # Detection object
                # =================================================

                detections.append(
                    Detection(
                        bbox=(
                            x1,
                            y1,
                            x2,
                            y2,
                        ),

                        model_class=str(
                            self.names.get(
                                class_id,
                                class_id,
                            )
                        ),

                        canonical_class=(
                            canonical
                        ),

                        confidence=(
                            confidence
                        ),

                        distance_m=(
                            distance
                        ),

                        bearing_deg=(
                            bearing
                        ),

                        gps=(
                            gps
                        ),

                        distance_quality=(
                            quality
                        ),
                    )
                )


        # ====================================================
        # Highest confidence first
        # ====================================================

        detections.sort(
            key=lambda detection:
                detection.confidence,
            reverse=True,
        )


        return detections


# ============================================================
# Multi-frame Spatial Consensus
# ============================================================

def consensus(
    detection_sets,
    min_frames: int,
    iou_threshold: float = (
        CONSENSUS_IOU_THRESHOLD
    ),
):
    """
    Spatial / Temporal Consensus

    เงื่อนไข:
    - Class ต้องเหมือนกัน
    - Bounding Box ต้องสัมพันธ์กันตาม IoU
    - Object ต้องปรากฏอย่างน้อย min_frames คนละ Frame

    Final R3-E6 System Contract:

        FRAMES_PER_SCAN = 3
        MIN_CONFIRM     = 2
        IoU             = 0.30

    รองรับหลาย Fire/Smoke
    ในภาพเดียวกันได้

    IMPORTANT:

    Consensus = Detection confirmation

    ไม่ใช่:

    Alert Deduplication
    """

    # ========================================================
    # Empty input
    # ========================================================

    if not detection_sets:

        return []


    # ========================================================
    # Parameters
    # ========================================================

    if (
        min_frames
        < 1
    ):

        raise ValueError(
            "min_frames must be >= 1"
        )


    if not (
        0.0
        <= iou_threshold
        <= 1.0
    ):

        raise ValueError(
            "iou_threshold must be "
            "between 0 and 1"
        )


    # ========================================================
    # Tracks
    # ========================================================

    tracks = []


    for (
        frame_index,
        frame_detections,
    ) in enumerate(
        detection_sets
    ):

        # ป้องกัน Detection เดียวกันใน Frame เดียว
        # เข้า track เดิมมากกว่าหนึ่งครั้ง

        used_track_ids = set()


        # Confidence สูงก่อน
        # เพื่อ match Detection ที่ชัดก่อน

        ordered = sorted(
            frame_detections,
            key=lambda detection:
                detection.confidence,
            reverse=True,
        )


        for detection in ordered:

            best_track_index = None

            best_iou = 0.0


            for (
                track_index,
                track,
            ) in enumerate(
                tracks
            ):

                if (
                    track_index
                    in used_track_ids
                ):

                    continue


                if (
                    track["class"]
                    !=
                    detection.canonical_class
                ):

                    continue


                last_detection = (
                    track[
                        "detections"
                    ][-1][1]
                )


                current_iou = (
                    bbox_iou(
                        last_detection.bbox,
                        detection.bbox,
                    )
                )


                if (
                    current_iou
                    >= iou_threshold
                    and
                    current_iou
                    > best_iou
                ):

                    best_iou = (
                        current_iou
                    )

                    best_track_index = (
                        track_index
                    )


            # =================================================
            # New Track
            # =================================================

            if (
                best_track_index
                is None
            ):

                tracks.append(
                    {
                        "class":
                            detection
                            .canonical_class,

                        "detections": [
                            (
                                frame_index,
                                detection,
                            )
                        ],
                    }
                )


                used_track_ids.add(
                    len(
                        tracks
                    )
                    - 1
                )


            # =================================================
            # Existing Track
            # =================================================

            else:

                tracks[
                    best_track_index
                ][
                    "detections"
                ].append(
                    (
                        frame_index,
                        detection,
                    )
                )


                used_track_ids.add(
                    best_track_index
                )


    # ========================================================
    # Confirmation
    # ========================================================

    confirmed = []


    for track in tracks:

        unique_frames = {
            frame_index
            for (
                frame_index,
                _,
            ) in track[
                "detections"
            ]
        }


        # ----------------------------------------------------
        # Not enough frames
        # ----------------------------------------------------

        if (
            len(
                unique_frames
            )
            < min_frames
        ):

            continue


        # ----------------------------------------------------
        # Candidate detections in this track
        # ----------------------------------------------------

        candidates = [
            detection
            for (
                _,
                detection,
            ) in track[
                "detections"
            ]
        ]


        # ----------------------------------------------------
        # Representative Detection
        # ----------------------------------------------------
        #
        # ใช้ Detection confidence สูงที่สุด
        # เป็นข้อมูลของ Confirmed Detection
        #
        # ----------------------------------------------------

        representative = max(
            candidates,
            key=lambda detection:
                detection.confidence,
        )


        confirmed.append(
            representative
        )


    # ========================================================
    # Highest confidence first
    # ========================================================

    return sorted(
        confirmed,
        key=lambda detection:
            detection.confidence,
        reverse=True,
    )
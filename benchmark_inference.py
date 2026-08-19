#!/usr/bin/env python3
# benchmark_inference.py

"""
Smart Fire Detection v2
Final AI Model R3-E6 Runtime Performance Benchmark

หน้าที่:
- Benchmark Runtime AI โดยไม่ต้องใช้กล้อง
- วัด Model Load Time
- วัด Warm-up latency
- วัด Mean / Median / P95 / Min / Max / StdDev
- คำนวณ Approximate single-frame FPS
- วัด Process RAM
- วัด Process CPU โดยประมาณ
- บันทึกผลเป็น JSON

IMPORTANT
=========
ไฟล์นี้เป็น PERFORMANCE BENCHMARK เท่านั้น

ไฟล์นี้ไม่ได้วัด:
- Accuracy
- Precision
- Recall
- mAP
- False Positive Rate
- False Negative Rate
- PT <-> ONNX equivalence
- PT <-> OpenVINO equivalence
- End-to-end PTZ sweep throughput

Final R3-E6 inference contract:
- source = original OpenCV BGR frame
- imgsz = 768
- conf = 0.25
- iou = 0.70
- max_det = 300
- rect = False
- device = cpu
- effective batch = 1

ห้ามทำ Manual Model Preprocessing ก่อน YOLO.predict():
- ห้าม resize เป็น 768x768 เอง
- ห้าม manual letterbox
- ห้าม BGR -> RGB เอง
- ห้าม normalize /255 เอง
- ห้าม tensor conversion เอง
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import psutil
from ultralytics import YOLO

from config import (
    CLASS_THRESHOLDS,

    EXPECTED_MODEL_CLASSES,
    EXPECTED_MODEL_SHA256,
    EXPECTED_ULTRALYTICS_VERSION,

    FINAL_MODEL_RELEASE,

    FRAME_HEIGHT,
    FRAME_WIDTH,

    IMGSZ,
    INFERENCE_DEVICE,

    MODEL_BACKEND,
    MODEL_BATCH,
    MODEL_MAX_DET,
    MODEL_NMS_IOU,
    MODEL_PATH_OPENVINO,
    MODEL_PATH_PT,
    MODEL_RECT,

    STARTUP_WARMUP_RUNS,

    STATIC_DIR,

    validate_final_model_contract,
    validate_runtime_config,
)


# ============================================================
# Benchmark constants
# ============================================================

BENCHMARK_TYPE = (
    "runtime_performance_only"
)

PRODUCTION_BACKEND = (
    "pt"
)

EXPERIMENTAL_BACKEND = (
    "openvino"
)


# ============================================================
# Generic helpers
# ============================================================

def bytes_to_mb(
    value,
):
    return (
        float(value)
        / 1024.0
        / 1024.0
    )


def percentile(
    values,
    percent,
):
    """
    Linear-interpolated percentile
    """

    if not values:
        raise ValueError(
            "values is empty"
        )

    ordered = sorted(
        float(value)
        for value in values
    )

    if len(ordered) == 1:
        return ordered[0]

    position = (
        (len(ordered) - 1)
        * (percent / 100.0)
    )

    low = math.floor(
        position
    )

    high = math.ceil(
        position
    )

    if low == high:
        return ordered[low]

    weight = (
        position
        - low
    )

    return (
        ordered[low]
        * (1.0 - weight)
        +
        ordered[high]
        * weight
    )


def package_version(
    name,
):
    try:

        return (
            importlib.metadata.version(
                name
            )
        )

    except (
        importlib.metadata.PackageNotFoundError,
    ):

        return None

    except Exception:

        return None


def sha256_file(
    path,
):
    """
    Read-only SHA256
    """

    path = Path(
        path
    )

    digest = (
        hashlib.sha256()
    )

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

    return (
        digest.hexdigest()
    )


def normalize_model_names(
    names_object,
):
    """
    Normalize model.names เป็น:

        {
            0: "fire",
            1: "smoke",
        }
    """

    if isinstance(
        names_object,
        dict,
    ):

        normalized = {}

        for (
            class_id,
            class_name,
        ) in names_object.items():

            normalized[
                int(class_id)
            ] = (
                str(class_name)
                .strip()
                .lower()
            )

        return normalized


    if isinstance(
        names_object,
        (
            list,
            tuple,
        ),
    ):

        return {

            index:
                (
                    str(class_name)
                    .strip()
                    .lower()
                )

            for (
                index,
                class_name,
            ) in enumerate(
                names_object
            )
        }


    raise RuntimeError(
        "Unsupported model.names format: "
        f"{type(names_object).__name__}"
    )


# ============================================================
# Final Benchmark Contract
# ============================================================

def validate_benchmark_contract():
    """
    Benchmark ต้องใช้ Inference Contract
    เดียวกับ Production detection.py

    Backend ของ Production config ยังคงต้องเป็น pt

    --backend openvino ของ Benchmark
    เป็น Experimental Performance Measurement เท่านั้น
    ไม่ได้เปลี่ยน Production Backend
    """

    validate_runtime_config()
    validate_final_model_contract()


    confidence = min(
        float(value)
        for value
        in CLASS_THRESHOLDS.values()
    )


    checks = {

        "MODEL_BACKEND":
            MODEL_BACKEND
            == "pt",

        "INFERENCE_DEVICE":
            (
                str(
                    INFERENCE_DEVICE
                )
                .strip()
                .lower()
                == "cpu"
            ),

        "IMGSZ":
            IMGSZ
            == 768,

        "Candidate confidence":
            math.isclose(
                confidence,
                0.25,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),

        "Fire threshold":
            math.isclose(
                float(
                    CLASS_THRESHOLDS[
                        "fire"
                    ]
                ),
                0.25,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),

        "Smoke threshold":
            math.isclose(
                float(
                    CLASS_THRESHOLDS[
                        "smoke"
                    ]
                ),
                0.25,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),

        "MODEL_NMS_IOU":
            math.isclose(
                float(
                    MODEL_NMS_IOU
                ),
                0.70,
                rel_tol=0.0,
                abs_tol=1e-12,
            ),

        "MODEL_MAX_DET":
            MODEL_MAX_DET
            == 300,

        "MODEL_RECT":
            MODEL_RECT
            is False,

        "MODEL_BATCH":
            MODEL_BATCH
            == 1,
    }


    failed = [

        name

        for (
            name,
            okay,
        ) in checks.items()

        if not okay
    ]


    if failed:

        raise RuntimeError(
            (
                "Final R3-E6 Benchmark Contract "
                "mismatch: "
                + ", ".join(
                    failed
                )
            )
        )


    # --------------------------------------------------------
    # Ultralytics strict version
    # --------------------------------------------------------

    ultralytics_version = (
        package_version(
            "ultralytics"
        )
    )


    if (
        ultralytics_version
        !=
        EXPECTED_ULTRALYTICS_VERSION
    ):

        raise RuntimeError(
            (
                "Ultralytics version mismatch: "
                f"installed="
                f"{ultralytics_version or 'missing'} "
                f"required="
                f"{EXPECTED_ULTRALYTICS_VERSION}"
            )
        )


    return confidence


# ============================================================
# Synthetic benchmark frame
# ============================================================

def create_synthetic_frame():
    """
    สร้าง Neutral Synthetic BGR Frame

    ใช้สำหรับ Performance Timing เท่านั้น

    ไม่ใช่ Accuracy Dataset
    """

    frame = np.zeros(
        (
            FRAME_HEIGHT,
            FRAME_WIDTH,
            3,
        ),
        dtype=np.uint8,
    )


    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    x_gradient = np.linspace(
        20,
        180,
        FRAME_WIDTH,
        dtype=np.uint8,
    )

    y_gradient = np.linspace(
        20,
        120,
        FRAME_HEIGHT,
        dtype=np.uint8,
    )


    frame[
        :,
        :,
        0,
    ] = (
        x_gradient[
            np.newaxis,
            :
        ]
    )


    frame[
        :,
        :,
        1,
    ] = (
        y_gradient[
            :,
            np.newaxis,
        ]
    )


    frame[
        :,
        :,
        2,
    ] = 70


    # --------------------------------------------------------
    # Neutral shapes
    # --------------------------------------------------------

    cv2.rectangle(
        frame,
        (
            int(
                FRAME_WIDTH
                * 0.10
            ),
            int(
                FRAME_HEIGHT
                * 0.20
            ),
        ),
        (
            int(
                FRAME_WIDTH
                * 0.35
            ),
            int(
                FRAME_HEIGHT
                * 0.70
            ),
        ),
        (
            110,
            110,
            110,
        ),
        -1,
    )


    cv2.circle(
        frame,
        (
            int(
                FRAME_WIDTH
                * 0.70
            ),
            int(
                FRAME_HEIGHT
                * 0.45
            ),
        ),
        max(
            10,
            int(
                min(
                    FRAME_WIDTH,
                    FRAME_HEIGHT,
                )
                * 0.10
            ),
        ),
        (
            150,
            150,
            150,
        ),
        -1,
    )


    cv2.putText(
        frame,
        (
            "Smart Fire Detection v2 "
            "Performance Benchmark"
        ),
        (
            30,
            max(
                40,
                int(
                    FRAME_HEIGHT
                    * 0.10
                ),
            ),
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (
            220,
            220,
            220,
        ),
        2,
        cv2.LINE_AA,
    )


    return frame


# ============================================================
# Input image
# ============================================================

def load_benchmark_frame(
    image_path=None,
):
    """
    รับ Original OpenCV BGR Frame

    ถ้าระบุ --image:
    ภาพต้องมี Resolution ตรง Runtime อยู่แล้ว

    ไฟล์นี้จะไม่ resize ภาพให้อัตโนมัติ

    เหตุผล:
    Benchmark ต้องวัด Model Runtime
    ไม่ใช่วัดขั้นตอนเตรียมภาพเพิ่มเติม
    """

    # --------------------------------------------------------
    # Synthetic
    # --------------------------------------------------------

    if image_path is None:

        return (
            create_synthetic_frame(),
            "synthetic",
        )


    # --------------------------------------------------------
    # File
    # --------------------------------------------------------

    path = (
        Path(
            image_path
        )
        .expanduser()
        .resolve()
    )


    if not path.is_file():

        raise FileNotFoundError(
            (
                "ไม่พบภาพ Benchmark: "
                f"{path}"
            )
        )


    frame = cv2.imread(
        str(
            path
        ),
        cv2.IMREAD_COLOR,
    )


    if frame is None:

        raise RuntimeError(
            (
                "OpenCV อ่านภาพไม่ได้: "
                f"{path}"
            )
        )


    # --------------------------------------------------------
    # BGR contract
    # --------------------------------------------------------

    if (
        frame.ndim
        != 3
        or
        frame.shape[2]
        != 3
    ):

        raise ValueError(
            (
                "Benchmark image must be "
                "a 3-channel OpenCV BGR image"
            )
        )


    height, width = (
        frame.shape[
            :2
        ]
    )


    # --------------------------------------------------------
    # Production geometry
    # --------------------------------------------------------

    if (
        width
        != FRAME_WIDTH

        or

        height
        != FRAME_HEIGHT
    ):

        raise ValueError(
            (
                "Benchmark image resolution mismatch: "
                f"expected "
                f"{FRAME_WIDTH}x{FRAME_HEIGHT}, "
                f"got "
                f"{width}x{height}. "
                "ไฟล์ Benchmark จะไม่ resize "
                "ภาพอัตโนมัติ"
            )
        )


    return (
        frame,
        str(
            path
        ),
    )


# ============================================================
# Model selection
# ============================================================

def resolve_model(
    backend,
):

    backend = (
        backend
        .strip()
        .lower()
    )


    if (
        backend
        == PRODUCTION_BACKEND
    ):

        return (
            Path(
                MODEL_PATH_PT
            )
            .resolve()
        )


    if (
        backend
        == EXPERIMENTAL_BACKEND
    ):

        return (
            Path(
                MODEL_PATH_OPENVINO
            )
            .resolve()
        )


    raise ValueError(
        (
            "Backend ไม่รองรับ: "
            f"{backend}"
        )
    )


# ============================================================
# Backend validation
# ============================================================

def validate_backend(
    backend,
    model_path,
):

    if (
        backend
        not in {
            PRODUCTION_BACKEND,
            EXPERIMENTAL_BACKEND,
        }
    ):

        raise ValueError(
            (
                "--backend ต้องเป็น "
                "pt หรือ openvino"
            )
        )


    if not model_path.exists():

        raise FileNotFoundError(
            (
                "ไม่พบ Model: "
                f"{model_path}"
            )
        )


    # --------------------------------------------------------
    # PT
    # --------------------------------------------------------

    if (
        backend
        == PRODUCTION_BACKEND
    ):

        if not model_path.is_file():

            raise RuntimeError(
                (
                    "PyTorch Runtime Model "
                    "ต้องเป็นไฟล์"
                )
            )


    # --------------------------------------------------------
    # Experimental OpenVINO
    # --------------------------------------------------------

    if (
        backend
        == EXPERIMENTAL_BACKEND
    ):

        if (
            importlib.util.find_spec(
                "openvino"
            )
            is None
        ):

            raise RuntimeError(
                (
                    "เลือก OpenVINO "
                    "แต่ยังไม่พบ package openvino"
                )
            )


# ============================================================
# PT Artifact verification
# ============================================================

def verify_pt_artifact(
    model_path,
):
    """
    Final PT ต้องผ่าน SHA256
    ก่อน YOLO load
    """

    actual_sha256 = (
        sha256_file(
            model_path
        )
    )


    if (
        actual_sha256.lower()
        !=
        EXPECTED_MODEL_SHA256.lower()
    ):

        raise RuntimeError(
            (
                "MODEL ARTIFACT VERIFICATION FAIL\n"
                f"Expected: "
                f"{EXPECTED_MODEL_SHA256}\n"
                f"Actual  : "
                f"{actual_sha256}"
            )
        )


    return actual_sha256


# ============================================================
# Exact Class Contract
# ============================================================

def verify_loaded_classes(
    model,
):

    names = (
        normalize_model_names(
            model.names
        )
    )


    if (
        names
        != EXPECTED_MODEL_CLASSES
    ):

        raise RuntimeError(
            (
                "MODEL CLASS CONTRACT MISMATCH\n"
                f"Expected: "
                f"{EXPECTED_MODEL_CLASSES}\n"
                f"Actual  : "
                f"{names}"
            )
        )


    return names


# ============================================================
# Final Runtime Prediction
# ============================================================

def run_prediction(
    model,
    frame,
    *,
    confidence,
):
    """
    Final R3-E6 High-level YOLO.predict Contract

    source เป็น Original OpenCV BGR frame

    ไม่มี Manual Model Preprocessing
    """

    return (
        model.predict(
            source=frame,

            imgsz=IMGSZ,

            conf=(
                confidence
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


# ============================================================
# Box diagnostic
# ============================================================

def count_boxes(
    results,
):
    """
    Diagnostic only

    จำนวนกล่องไม่ใช่ Accuracy Metric
    """

    total = 0


    for result in results:

        if (
            result.boxes
            is not None
        ):

            total += len(
                result.boxes
            )


    return total


# ============================================================
# Benchmark
# ============================================================

def benchmark(
    *,
    backend,
    runs,
    warmup,
    image_path,
):

    # ========================================================
    # Final software / inference contract
    # ========================================================

    confidence = (
        validate_benchmark_contract()
    )


    backend = (
        backend
        .strip()
        .lower()
    )


    # ========================================================
    # Model
    # ========================================================

    model_path = (
        resolve_model(
            backend
        )
    )


    validate_backend(
        backend,
        model_path,
    )


    # ========================================================
    # Input BGR frame
    # ========================================================

    (
        frame,
        input_source,
    ) = (
        load_benchmark_frame(
            image_path
        )
    )


    # ========================================================
    # Process
    # ========================================================

    process = (
        psutil.Process(
            os.getpid()
        )
    )


    logical_cpu_count = (
        psutil.cpu_count(
            logical=True
        )
        or 1
    )


    ram_before_load = (
        bytes_to_mb(
            process
            .memory_info()
            .rss
        )
    )


    # ========================================================
    # Package manifest
    # ========================================================

    package_versions = {

        "numpy":
            package_version(
                "numpy"
            ),

        "opencv_python":
            package_version(
                "opencv-python"
            ),

        "torch":
            package_version(
                "torch"
            ),

        "torchvision":
            package_version(
                "torchvision"
            ),

        "ultralytics":
            package_version(
                "ultralytics"
            ),

        "openvino":
            (
                package_version(
                    "openvino"
                )
                if backend
                == EXPERIMENTAL_BACKEND
                else None
            ),
    }


    # ========================================================
    # Header
    # ========================================================

    print(
        "=" * 78
    )

    print(
        (
            "Smart Fire Detection v2 "
            "- Final R3-E6 "
            "Runtime Performance Benchmark"
        )
    )

    print(
        "=" * 78
    )


    print(
        "Benchmark type : PERFORMANCE ONLY"
    )

    print(
        "Accuracy test  : NO"
    )

    print(
        "Equivalence    : NO"
    )


    print(
        f"Release        : "
        f"{FINAL_MODEL_RELEASE}"
    )

    print(
        f"OS             : "
        f"{platform.system()} "
        f"{platform.release()}"
    )

    print(
        f"Python         : "
        f"{platform.python_version()}"
    )

    print(
        f"CPU logical    : "
        f"{logical_cpu_count}"
    )

    print(
        f"Backend        : "
        f"{backend}"
    )

    print(
        f"Model          : "
        f"{model_path}"
    )

    print(
        f"Device         : "
        f"{INFERENCE_DEVICE}"
    )

    print(
        f"IMGSZ          : "
        f"{IMGSZ}"
    )

    print(
        f"Confidence     : "
        f"{confidence:.2f}"
    )

    print(
        f"NMS IoU        : "
        f"{MODEL_NMS_IOU:.2f}"
    )

    print(
        f"max_det        : "
        f"{MODEL_MAX_DET}"
    )

    print(
        f"rect           : "
        f"{MODEL_RECT}"
    )

    print(
        f"Effective batch: "
        f"{MODEL_BATCH}"
    )

    print(
        f"Frame          : "
        f"{FRAME_WIDTH}"
        f"x"
        f"{FRAME_HEIGHT}"
    )

    print(
        f"Input          : "
        f"{input_source}"
    )

    print(
        f"Warm-up        : "
        f"{warmup}"
    )

    print(
        f"Timed runs     : "
        f"{runs}"
    )


    if (
        backend
        == EXPERIMENTAL_BACKEND
    ):

        print(
            (
                "Backend status : "
                "EXPERIMENTAL / "
                "NOT PRODUCTION APPROVED"
            )
        )

        print(
            (
                "                 "
                "Performance result does NOT "
                "establish PT<->OpenVINO equivalence."
            )
        )

    else:

        print(
            (
                "Backend status : "
                "APPROVED PT MASTER RUNTIME"
            )
        )


    print(
        "=" * 78
    )


    # ========================================================
    # 1. Artifact verification
    # ========================================================

    model_sha256 = None


    if (
        backend
        == PRODUCTION_BACKEND
    ):

        print(
            "\n[1/4] "
            "Verifying Final PT artifact..."
        )


        model_sha256 = (
            verify_pt_artifact(
                model_path
            )
        )


        print(
            f"      SHA256      : "
            f"{model_sha256}"
        )


    else:

        print(
            "\n[1/4] "
            "Artifact verification..."
        )

        print(
            (
                "      PT SHA gate : "
                "N/A for experimental "
                "OpenVINO artifact"
            )
        )


    # ========================================================
    # 2. Model load
    # ========================================================

    print(
        "\n[2/4] Loading model..."
    )


    start = (
        time.perf_counter()
    )


    model = (
        YOLO(
            str(
                model_path
            )
        )
    )


    load_ms = (
        (
            time.perf_counter()
            - start
        )
        * 1000.0
    )


    ram_after_load = (
        bytes_to_mb(
            process
            .memory_info()
            .rss
        )
    )


    peak_ram = (
        ram_after_load
    )


    print(
        f"      Load time    : "
        f"{load_ms:.2f} ms"
    )

    print(
        f"      RAM           : "
        f"{ram_after_load:.2f} MB"
    )


    # --------------------------------------------------------
    # Exact classes
    # --------------------------------------------------------

    names = (
        verify_loaded_classes(
            model
        )
    )


    print(
        f"      Classes       : "
        f"{names}"
    )


    # ========================================================
    # 3. Warm-up
    # ========================================================

    print(
        "\n[3/4] Warm-up..."
    )


    warmup_times = []

    warmup_box_counts = []


    for index in range(
        warmup
    ):

        start = (
            time.perf_counter()
        )


        prediction = (
            run_prediction(
                model,
                frame,
                confidence=(
                    confidence
                ),
            )
        )


        elapsed_ms = (
            (
                time.perf_counter()
                - start
            )
            * 1000.0
        )


        boxes = (
            count_boxes(
                prediction
            )
        )


        warmup_times.append(
            elapsed_ms
        )

        warmup_box_counts.append(
            boxes
        )


        current_ram = (
            bytes_to_mb(
                process
                .memory_info()
                .rss
            )
        )


        peak_ram = max(
            peak_ram,
            current_ram,
        )


        print(
            f"      "
            f"{index + 1:>2}"
            f"/"
            f"{warmup:<2} "
            f"{elapsed_ms:>9.2f} ms "
            f"| boxes="
            f"{boxes}"
        )


    # ========================================================
    # 4. Timed benchmark
    # ========================================================

    print(
        "\n[4/4] "
        "Timed performance runs..."
    )


    latencies = []

    box_counts = []


    cpu_before = (
        process.cpu_times()
    )


    wall_start = (
        time.perf_counter()
    )


    progress_step = max(
        1,
        runs // 10,
    )


    for index in range(
        runs
    ):

        start = (
            time.perf_counter()
        )


        prediction = (
            run_prediction(
                model,
                frame,
                confidence=(
                    confidence
                ),
            )
        )


        elapsed_ms = (
            (
                time.perf_counter()
                - start
            )
            * 1000.0
        )


        latencies.append(
            elapsed_ms
        )


        box_counts.append(
            count_boxes(
                prediction
            )
        )


        current_ram = (
            bytes_to_mb(
                process
                .memory_info()
                .rss
            )
        )


        peak_ram = max(
            peak_ram,
            current_ram,
        )


        if (
            index == 0

            or

            (
                (index + 1)
                % progress_step
                == 0
            )

            or

            index + 1
            == runs
        ):

            print(
                f"      "
                f"{index + 1:>4}"
                f"/"
                f"{runs:<4} "
                f"{elapsed_ms:>9.2f} ms"
            )


    wall_elapsed = (
        time.perf_counter()
        - wall_start
    )


    # ========================================================
    # CPU
    # ========================================================

    cpu_after = (
        process.cpu_times()
    )


    cpu_time = (
        (
            cpu_after.user
            - cpu_before.user
        )
        +
        (
            cpu_after.system
            - cpu_before.system
        )
    )


    if (
        wall_elapsed
        > 0
    ):

        cpu_percent = (
            cpu_time
            /
            wall_elapsed
            /
            logical_cpu_count
            *
            100.0
        )

    else:

        cpu_percent = 0.0


    # ========================================================
    # RAM
    # ========================================================

    ram_after_benchmark = (
        bytes_to_mb(
            process
            .memory_info()
            .rss
        )
    )


    # ========================================================
    # Statistics
    # ========================================================

    mean_ms = (
        statistics.fmean(
            latencies
        )
    )


    median_ms = (
        statistics.median(
            latencies
        )
    )


    p95_ms = (
        percentile(
            latencies,
            95,
        )
    )


    minimum_ms = min(
        latencies
    )


    maximum_ms = max(
        latencies
    )


    if (
        len(
            latencies
        )
        >= 2
    ):

        stdev_ms = (
            statistics.stdev(
                latencies
            )
        )

    else:

        stdev_ms = 0.0


    if (
        mean_ms
        > 0
    ):

        approx_fps = (
            1000.0
            / mean_ms
        )

    else:

        approx_fps = 0.0


    average_boxes = (
        statistics.fmean(
            box_counts
        )
    )


    # ========================================================
    # Result
    # ========================================================

    result = {

        "timestamp":
            (
                datetime.now()
                .astimezone()
                .isoformat()
            ),

        "project":
            "Smart Fire Detection v2",

        "final_model_release":
            FINAL_MODEL_RELEASE,


        # ----------------------------------------------------
        # Scope
        # ----------------------------------------------------

        "benchmark_scope": {

            "type":
                BENCHMARK_TYPE,

            "performance_measured":
                True,

            "accuracy_evaluated":
                False,

            "equivalence_evaluated":
                False,

            "pt_openvino_equivalence_claimed":
                False,

            "end_to_end_ptz_throughput_measured":
                False,

            "warning":
                (
                    "Latency, FPS and box-count "
                    "must not be interpreted as "
                    "model accuracy or "
                    "backend equivalence."
                ),
        },


        # ----------------------------------------------------
        # System
        # ----------------------------------------------------

        "system": {

            "os":
                platform.system(),

            "os_release":
                platform.release(),

            "platform":
                platform.platform(),

            "python":
                platform.python_version(),

            "logical_cpu_count":
                logical_cpu_count,
        },


        # ----------------------------------------------------
        # Packages
        # ----------------------------------------------------

        "packages":
            package_versions,


        # ----------------------------------------------------
        # Model
        # ----------------------------------------------------

        "model": {

            "backend":
                backend,

            "backend_status":
                (
                    "approved_pt_master_runtime"
                    if backend
                    == PRODUCTION_BACKEND
                    else
                    "experimental_not_production_approved"
                ),

            "path":
                str(
                    model_path
                ),

            "sha256":
                model_sha256,

            "expected_pt_sha256":
                (
                    EXPECTED_MODEL_SHA256
                    if backend
                    == PRODUCTION_BACKEND
                    else None
                ),

            "classes":
                names,

            "expected_classes":
                EXPECTED_MODEL_CLASSES,

            "class_contract_ok":
                (
                    names
                    ==
                    EXPECTED_MODEL_CLASSES
                ),
        },


        # ----------------------------------------------------
        # Final inference contract
        # ----------------------------------------------------

        "inference_contract": {

            "source":
                "original_opencv_bgr_frame",

            "manual_preprocessing":
                False,

            "device":
                INFERENCE_DEVICE,

            "imgsz":
                IMGSZ,

            "candidate_confidence":
                confidence,

            "fire_threshold":
                float(
                    CLASS_THRESHOLDS[
                        "fire"
                    ]
                ),

            "smoke_threshold":
                float(
                    CLASS_THRESHOLDS[
                        "smoke"
                    ]
                ),

            "nms_iou":
                MODEL_NMS_IOU,

            "max_det":
                MODEL_MAX_DET,

            "rect":
                MODEL_RECT,

            "effective_batch":
                MODEL_BATCH,

            "frame_width":
                FRAME_WIDTH,

            "frame_height":
                FRAME_HEIGHT,

            "input_source":
                input_source,
        },


        # ----------------------------------------------------
        # Benchmark methodology
        # ----------------------------------------------------

        "benchmark_method": {

            "warmup_runs":
                warmup,

            "production_startup_warmup_default":
                STARTUP_WARMUP_RUNS,

            "timed_runs":
                runs,

            "sequential_single_frame_calls":
                True,
        },


        # ----------------------------------------------------
        # Model load
        # ----------------------------------------------------

        "model_load": {

            "time_ms":
                load_ms,

            "ram_before_mb":
                ram_before_load,

            "ram_after_mb":
                ram_after_load,

            "ram_delta_mb":
                (
                    ram_after_load
                    -
                    ram_before_load
                ),
        },


        # ----------------------------------------------------
        # Warm-up
        # ----------------------------------------------------

        "warmup": {

            "times_ms":
                warmup_times,

            "box_counts":
                warmup_box_counts,

            "first_ms":
                (
                    warmup_times[0]
                    if warmup_times
                    else None
                ),

            "last_ms":
                (
                    warmup_times[-1]
                    if warmup_times
                    else None
                ),
        },


        # ----------------------------------------------------
        # Runtime performance
        # ----------------------------------------------------

        "performance": {

            "mean_ms":
                mean_ms,

            "median_ms":
                median_ms,

            "p95_ms":
                p95_ms,

            "min_ms":
                minimum_ms,

            "max_ms":
                maximum_ms,

            "stdev_ms":
                stdev_ms,

            "approx_single_frame_fps":
                approx_fps,

            "wall_time_sec":
                wall_elapsed,

            "average_boxes_per_run":
                average_boxes,

            "box_count_note":
                (
                    "Diagnostic only; "
                    "not an accuracy metric."
                ),

            "fps_note":
                (
                    "1000 / mean inference latency. "
                    "Not end-to-end "
                    "camera/PTZ sweep FPS."
                ),
        },


        # ----------------------------------------------------
        # Resources
        # ----------------------------------------------------

        "resources": {

            "ram_after_benchmark_mb":
                ram_after_benchmark,

            "observed_peak_ram_mb":
                peak_ram,

            "process_cpu_percent_normalized":
                cpu_percent,

            "note":
                (
                    "CPU percent is normalized "
                    "across logical CPUs. "
                    "Peak RAM is sampled "
                    "after each inference."
                ),
        },
    }


    return result


# ============================================================
# Print Result
# ============================================================

def print_result(
    result,
):

    load = (
        result[
            "model_load"
        ]
    )

    performance = (
        result[
            "performance"
        ]
    )

    resources = (
        result[
            "resources"
        ]
    )


    print(
        "\n"
        + "=" * 78
    )

    print(
        "RUNTIME PERFORMANCE RESULT"
    )

    print(
        "=" * 78
    )


    print(
        "Scope                : PERFORMANCE ONLY"
    )

    print(
        "Accuracy evaluated   : NO"
    )

    print(
        "Equivalence evaluated: NO"
    )


    print(
        f"Backend              : "
        f"{result['model']['backend']}"
    )

    print(
        f"Model load           : "
        f"{load['time_ms']:.2f} ms"
    )

    print(
        f"Inference mean       : "
        f"{performance['mean_ms']:.2f} ms"
    )

    print(
        f"Inference median     : "
        f"{performance['median_ms']:.2f} ms"
    )

    print(
        f"Inference P95        : "
        f"{performance['p95_ms']:.2f} ms"
    )

    print(
        f"Inference min        : "
        f"{performance['min_ms']:.2f} ms"
    )

    print(
        f"Inference max        : "
        f"{performance['max_ms']:.2f} ms"
    )

    print(
        f"Std dev              : "
        f"{performance['stdev_ms']:.2f} ms"
    )

    print(
        f"Approx single FPS    : "
        f"{performance['approx_single_frame_fps']:.2f}"
    )


    print(
        f"RAM before load      : "
        f"{load['ram_before_mb']:.2f} MB"
    )

    print(
        f"RAM after load       : "
        f"{load['ram_after_mb']:.2f} MB"
    )

    print(
        f"Observed peak RAM    : "
        f"{resources['observed_peak_ram_mb']:.2f} MB"
    )

    print(
        f"Process CPU approx   : "
        f"{resources['process_cpu_percent_normalized']:.2f}%"
    )


    print(
        f"Average boxes/run    : "
        f"{performance['average_boxes_per_run']:.2f}"
    )


    print(
        "-" * 78
    )

    print(
        (
            "NOTE: Latency/FPS/box-count "
            "are NOT accuracy metrics."
        )
    )

    print(
        (
            "NOTE: This benchmark does NOT "
            "establish backend equivalence."
        )
    )

    print(
        "=" * 78
    )


# ============================================================
# Save Result
# ============================================================

def save_result(
    result,
    output_path=None,
):

    if output_path:

        path = (
            Path(
                output_path
            )
            .expanduser()
            .resolve()
        )

    else:

        output_dir = (
            Path(
                STATIC_DIR
            )
            / "benchmark_runs"
        )


        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


        timestamp = (
            time.strftime(
                "%Y%m%d_%H%M%S"
            )
        )


        backend = (
            result[
                "model"
            ][
                "backend"
            ]
        )


        path = (
            output_dir
            /
            (
                f"benchmark_"
                f"{backend}_"
                f"{timestamp}.json"
            )
        )


    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    path.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


    return path


# ============================================================
# Main
# ============================================================

def main():

    parser = (
        argparse.ArgumentParser(
            description=(
                "Smart Fire Detection v2 "
                "- Final R3-E6 "
                "Runtime Performance Benchmark. "
                "This tool does not evaluate "
                "accuracy or backend equivalence."
            )
        )
    )


    # ========================================================
    # Backend
    # ========================================================
    #
    # PT:
    #   Production-approved master runtime
    #
    # OpenVINO:
    #   Performance experiment only
    #   ไม่ใช่ Equivalence Gate
    #
    # ========================================================

    parser.add_argument(
        "--backend",
        choices=[
            PRODUCTION_BACKEND,
            EXPERIMENTAL_BACKEND,
        ],
        default=PRODUCTION_BACKEND,
        help=(
            "pt = approved Production runtime; "
            "openvino = experimental "
            "performance measurement only "
            "(default=pt)"
        ),
    )


    # ========================================================
    # Performance methodology
    # ========================================================

    parser.add_argument(
        "--runs",
        type=int,
        default=50,
        help=(
            "จำนวน Timed Performance Runs "
            "(default=50)"
        ),
    )


    parser.add_argument(
        "--warmup",
        type=int,
        default=STARTUP_WARMUP_RUNS,
        help=(
            "จำนวน Warm-up Runs "
            f"(default={STARTUP_WARMUP_RUNS}, "
            "same as Production startup)"
        ),
    )


    # ========================================================
    # Input
    # ========================================================

    parser.add_argument(
        "--image",
        default=None,
        help=(
            "Optional production-resolution "
            "benchmark image. "
            f"ต้องเป็น "
            f"{FRAME_WIDTH}x{FRAME_HEIGHT}. "
            "ถ้าไม่ระบุจะใช้ Synthetic Frame."
        ),
    )


    # ========================================================
    # Output
    # ========================================================

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "กำหนด JSON output เอง "
            "ถ้าไม่ระบุจะเก็บใน "
            "static/benchmark_runs/"
        ),
    )


    args = (
        parser.parse_args()
    )


    # ========================================================
    # Validate CLI
    # ========================================================

    if (
        args.runs
        < 1
    ):

        parser.error(
            "--runs must be >= 1"
        )


    if (
        args.warmup
        < 0
    ):

        parser.error(
            "--warmup must be >= 0"
        )


    # ========================================================
    # Run
    # ========================================================

    try:

        result = (
            benchmark(
                backend=(
                    args.backend
                ),
                runs=(
                    args.runs
                ),
                warmup=(
                    args.warmup
                ),
                image_path=(
                    args.image
                ),
            )
        )


        print_result(
            result
        )


        output_path = (
            save_result(
                result,
                args.output,
            )
        )


        print(
            "\nSaved result:"
        )

        print(
            output_path
        )


        return 0


    except KeyboardInterrupt:

        print(
            "\nBenchmark stopped"
        )

        return 130


    except Exception as exc:

        print(
            "\nBenchmark failed"
        )

        print(
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
        )

        return 1


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
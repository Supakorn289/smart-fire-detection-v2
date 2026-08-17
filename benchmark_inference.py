#!/usr/bin/env python3

"""
Smart Fire Detection v2
AI Inference Benchmark

หน้าที่:
- Benchmark AI โดยไม่ต้องใช้กล้อง
- รองรับ PyTorch และ OpenVINO
- วัด Model Load Time
- วัด Warm-up
- วัด Mean / Median / P95 / Min / Max
- คำนวณ FPS โดยประมาณ
- วัด RAM
- วัด CPU Process โดยประมาณ
- บันทึกผลเป็น JSON

ตัวอย่าง:
    python benchmark_inference.py

    python benchmark_inference.py --backend pt

    python benchmark_inference.py --backend pt --runs 100

    python benchmark_inference.py --image static/camera_test.jpg

    python benchmark_inference.py --backend openvino
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import psutil

from ultralytics import YOLO

from config import (
    CLASS_THRESHOLDS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    IMGSZ,
    INFERENCE_DEVICE,
    MODEL_BACKEND,
    MODEL_PATH_OPENVINO,
    MODEL_PATH_PT,
    STATIC_DIR,
)


# ============================================================
# Helpers
# ============================================================

def bytes_to_mb(value):

    return (
        float(value)
        / 1024.0
        / 1024.0
    )


def percentile(
    values,
    percent,
):

    if not values:

        raise ValueError(
            "values is empty"
        )

    ordered = sorted(
        float(v)
        for v in values
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
        position - low
    )

    return (
        ordered[low]
        * (1.0 - weight)
        +
        ordered[high]
        * weight
    )


# ============================================================
# Synthetic benchmark frame
# ============================================================

def create_synthetic_frame():

    """
    สร้างภาพสำหรับ Benchmark
    เมื่อยังไม่มีกล้อง

    ขนาดภาพตรงกับ Runtime
    FRAME_WIDTH x FRAME_HEIGHT
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
    # Gradient background
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

    frame[:, :, 0] = (
        x_gradient[
            np.newaxis,
            :
        ]
    )

    frame[:, :, 1] = (
        y_gradient[
            :,
            np.newaxis,
        ]
    )

    frame[:, :, 2] = 70

    # --------------------------------------------------------
    # Objects
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
            "Smart Fire Detection "
            "v2 Benchmark"
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
        0.8,
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

    # --------------------------------------------------------
    # ไม่มีภาพ
    # ใช้ Synthetic Frame
    # --------------------------------------------------------

    if image_path is None:

        return (
            create_synthetic_frame(),
            "synthetic",
        )

    # --------------------------------------------------------
    # ใช้ภาพจริง
    # --------------------------------------------------------

    path = Path(
        image_path
    )

    if not path.exists():

        raise FileNotFoundError(
            (
                "ไม่พบภาพ Benchmark: "
                f"{path}"
            )
        )

    frame = cv2.imread(
        str(path),
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
    # ทำ Resolution ให้ตรง Runtime
    # --------------------------------------------------------

    if (
        frame.shape[1]
        != FRAME_WIDTH
        or
        frame.shape[0]
        != FRAME_HEIGHT
    ):

        frame = cv2.resize(
            frame,
            (
                FRAME_WIDTH,
                FRAME_HEIGHT,
            ),
            interpolation=(
                cv2.INTER_AREA
            ),
        )

    return (
        frame,
        str(path),
    )


# ============================================================
# Model
# ============================================================

def resolve_model(
    backend,
):

    backend = (
        backend
        .strip()
        .lower()
    )

    if backend == "pt":

        return Path(
            MODEL_PATH_PT
        )

    if backend == "openvino":

        return Path(
            MODEL_PATH_OPENVINO
        )

    raise ValueError(
        (
            "Backend ไม่รองรับ: "
            f"{backend}"
        )
    )


def validate_backend(
    backend,
    model_path,
):

    if backend not in {
        "pt",
        "openvino",
    }:

        raise SystemExit(
            (
                "❌ --backend "
                "ต้องเป็น "
                "pt หรือ openvino"
            )
        )

    if not model_path.exists():

        raise SystemExit(
            (
                "❌ ไม่พบโมเดล: "
                f"{model_path}"
            )
        )

    # --------------------------------------------------------
    # OpenVINO package
    # --------------------------------------------------------

    if (
        backend == "openvino"
        and
        importlib.util.find_spec(
            "openvino"
        )
        is None
    ):

        raise SystemExit(
            (
                "❌ เลือก OpenVINO "
                "แต่ยังไม่พบ "
                "package openvino"
            )
        )


# ============================================================
# Prediction
# ============================================================

def run_prediction(
    model,
    frame,
    *,
    imgsz,
    device,
    confidence,
):

    """
    ใช้ Parameter หลักให้ตรงกับ Runtime detection.py
    """

    return model.predict(
        source=frame,
        imgsz=imgsz,
        conf=confidence,
        device=device,
        verbose=False,
    )


def count_boxes(
    results,
):

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
    imgsz,
    device,
    image_path,
):

    # --------------------------------------------------------
    # Resolve model
    # --------------------------------------------------------

    model_path = (
        resolve_model(
            backend
        )
    )

    validate_backend(
        backend,
        model_path,
    )

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    (
        frame,
        input_source,
    ) = load_benchmark_frame(
        image_path
    )

    # Runtime ใช้ threshold ต่ำสุด
    confidence = min(
        CLASS_THRESHOLDS.values()
    )

    # --------------------------------------------------------
    # System
    # --------------------------------------------------------

    process = psutil.Process(
        os.getpid()
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
    # Information
    # ========================================================

    print(
        "=" * 78
    )

    print(
        "Smart Fire Detection v2 "
        "- AI Inference Benchmark"
    )

    print(
        "=" * 78
    )

    print(
        f"OS          : "
        f"{platform.system()} "
        f"{platform.release()}"
    )

    print(
        f"Python      : "
        f"{platform.python_version()}"
    )

    print(
        f"CPU logical : "
        f"{logical_cpu_count}"
    )

    print(
        f"Backend     : "
        f"{backend}"
    )

    print(
        f"Model       : "
        f"{model_path}"
    )

    print(
        f"Device      : "
        f"{device}"
    )

    print(
        f"IMGSZ       : "
        f"{imgsz}"
    )

    print(
        f"Confidence  : "
        f"{confidence:.3f}"
    )

    print(
        f"Frame       : "
        f"{FRAME_WIDTH}"
        f"x"
        f"{FRAME_HEIGHT}"
    )

    print(
        f"Input       : "
        f"{input_source}"
    )

    print(
        f"Warm-up     : "
        f"{warmup}"
    )

    print(
        f"Runs        : "
        f"{runs}"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # Model loading
    # ========================================================

    print(
        "\n[1/3] Loading model..."
    )

    start = (
        time.perf_counter()
    )

    model = YOLO(
        str(
            model_path
        )
    )

    load_ms = (
        time.perf_counter()
        - start
    ) * 1000.0

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
        f"      Load time : "
        f"{load_ms:.2f} ms"
    )

    print(
        f"      RAM        : "
        f"{ram_after_load:.2f} MB"
    )

    # ========================================================
    # Warm-up
    # ========================================================

    print(
        "\n[2/3] Warm-up..."
    )

    warmup_times = []

    for index in range(
        warmup
    ):

        start = (
            time.perf_counter()
        )

        results = (
            run_prediction(
                model,
                frame,
                imgsz=imgsz,
                device=device,
                confidence=confidence,
            )
        )

        elapsed_ms = (
            time.perf_counter()
            - start
        ) * 1000.0

        warmup_times.append(
            elapsed_ms
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
            f"{count_boxes(results)}"
        )

    # ========================================================
    # Timed benchmark
    # ========================================================

    print(
        "\n[3/3] Timed runs..."
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

        results = (
            run_prediction(
                model,
                frame,
                imgsz=imgsz,
                device=device,
                confidence=confidence,
            )
        )

        elapsed_ms = (
            time.perf_counter()
            - start
        ) * 1000.0

        latencies.append(
            elapsed_ms
        )

        box_counts.append(
            count_boxes(
                results
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
            (index + 1)
            % progress_step
            == 0
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
    # CPU usage
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

    if wall_elapsed > 0:

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

    if len(
        latencies
    ) >= 2:

        stdev_ms = (
            statistics.stdev(
                latencies
            )
        )

    else:

        stdev_ms = 0.0

    if mean_ms > 0:

        fps = (
            1000.0
            / mean_ms
        )

    else:

        fps = 0.0

    average_boxes = (
        statistics.fmean(
            box_counts
        )
    )

    # ========================================================
    # Result object
    # ========================================================

    result = {

        "timestamp": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),

        "project": (
            "Smart Fire Detection v2"
        ),

        "system": {

            "os": (
                platform.system()
            ),

            "os_release": (
                platform.release()
            ),

            "platform": (
                platform.platform()
            ),

            "python": (
                platform.python_version()
            ),

            "logical_cpu_count": (
                logical_cpu_count
            ),
        },

        "benchmark": {

            "backend": backend,

            "model_path": str(
                model_path
            ),

            "device": device,

            "imgsz": imgsz,

            "confidence": (
                confidence
            ),

            "frame_width": (
                FRAME_WIDTH
            ),

            "frame_height": (
                FRAME_HEIGHT
            ),

            "input_source": (
                input_source
            ),

            "warmup_runs": (
                warmup
            ),

            "timed_runs": (
                runs
            ),
        },

        "model_load": {

            "time_ms": (
                load_ms
            ),

            "ram_before_mb": (
                ram_before_load
            ),

            "ram_after_mb": (
                ram_after_load
            ),

            "ram_delta_mb": (
                ram_after_load
                -
                ram_before_load
            ),
        },

        "warmup": {

            "times_ms": (
                warmup_times
            ),

            "first_ms": (
                warmup_times[0]
                if warmup_times
                else None
            ),

            "last_ms": (
                warmup_times[-1]
                if warmup_times
                else None
            ),
        },

        "inference": {

            "mean_ms": (
                mean_ms
            ),

            "median_ms": (
                median_ms
            ),

            "p95_ms": (
                p95_ms
            ),

            "min_ms": (
                minimum_ms
            ),

            "max_ms": (
                maximum_ms
            ),

            "stdev_ms": (
                stdev_ms
            ),

            "approx_fps": (
                fps
            ),

            "wall_time_sec": (
                wall_elapsed
            ),

            "average_boxes": (
                average_boxes
            ),
        },

        "resources": {

            "ram_after_benchmark_mb": (
                ram_after_benchmark
            ),

            "observed_peak_ram_mb": (
                peak_ram
            ),

            "process_cpu_percent_normalized": (
                cpu_percent
            ),

            "note": (
                "CPU percent is normalized "
                "across logical CPUs. "
                "Peak RAM is sampled after "
                "each inference."
            ),
        },
    }

    return result


# ============================================================
# Print result
# ============================================================

def print_result(
    result,
):

    load = (
        result[
            "model_load"
        ]
    )

    inference = (
        result[
            "inference"
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
        "BENCHMARK RESULT"
    )

    print(
        "=" * 78
    )

    print(
        f"Backend             : "
        f"{result['benchmark']['backend']}"
    )

    print(
        f"Model load          : "
        f"{load['time_ms']:.2f} ms"
    )

    print(
        f"Inference mean      : "
        f"{inference['mean_ms']:.2f} ms"
    )

    print(
        f"Inference median    : "
        f"{inference['median_ms']:.2f} ms"
    )

    print(
        f"Inference P95       : "
        f"{inference['p95_ms']:.2f} ms"
    )

    print(
        f"Inference min       : "
        f"{inference['min_ms']:.2f} ms"
    )

    print(
        f"Inference max       : "
        f"{inference['max_ms']:.2f} ms"
    )

    print(
        f"Std dev             : "
        f"{inference['stdev_ms']:.2f} ms"
    )

    print(
        f"Approx FPS          : "
        f"{inference['approx_fps']:.2f}"
    )

    print(
        f"RAM before load     : "
        f"{load['ram_before_mb']:.2f} MB"
    )

    print(
        f"RAM after load      : "
        f"{load['ram_after_mb']:.2f} MB"
    )

    print(
        f"Observed peak RAM   : "
        f"{resources['observed_peak_ram_mb']:.2f} MB"
    )

    print(
        f"Process CPU approx  : "
        f"{resources['process_cpu_percent_normalized']:.2f}%"
    )

    print(
        f"Average boxes/run   : "
        f"{inference['average_boxes']:.2f}"
    )

    print(
        "=" * 78
    )


# ============================================================
# Save result
# ============================================================

def save_result(
    result,
    output_path=None,
):

    if output_path:

        path = Path(
            output_path
        )

    else:

        output_dir = (
            STATIC_DIR
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
                "benchmark"
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

    parser = argparse.ArgumentParser(
        description=(
            "Smart Fire Detection v2 "
            "- AI inference benchmark"
        )
    )

    parser.add_argument(
        "--backend",
        choices=[
            "pt",
            "openvino",
        ],
        default=MODEL_BACKEND,
        help=(
            "AI backend "
            f"(default={MODEL_BACKEND})"
        ),
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=50,
        help=(
            "จำนวนรอบ Benchmark "
            "(default=50)"
        ),
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help=(
            "จำนวนรอบ Warm-up "
            "(default=5)"
        ),
    )

    parser.add_argument(
        "--imgsz",
        type=int,
        default=IMGSZ,
        help=(
            "Inference image size "
            f"(default={IMGSZ})"
        ),
    )

    parser.add_argument(
        "--device",
        default=INFERENCE_DEVICE,
        help=(
            "Inference device "
            f"(default={INFERENCE_DEVICE})"
        ),
    )

    parser.add_argument(
        "--image",
        default=None,
        help=(
            "ภาพสำหรับ Benchmark "
            "ถ้าไม่ระบุจะสร้าง "
            "Synthetic Frame"
        ),
    )

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

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if args.runs < 1:

        raise SystemExit(
            "❌ --runs ต้อง >= 1"
        )

    if args.warmup < 0:

        raise SystemExit(
            "❌ --warmup ต้อง >= 0"
        )

    if args.imgsz < 32:

        raise SystemExit(
            "❌ --imgsz ต้อง >= 32"
        )

    try:

        result = benchmark(
            backend=(
                args.backend
            ),
            runs=(
                args.runs
            ),
            warmup=(
                args.warmup
            ),
            imgsz=(
                args.imgsz
            ),
            device=(
                args.device
            ),
            image_path=(
                args.image
            ),
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
            "\n❌ Benchmark failed"
        )

        print(
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
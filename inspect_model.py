#!/usr/bin/env python3
# inspect_model.py

"""
Smart Fire Detection v2
Final AI Model R3-E6 Inspector

หน้าที่:
- ตรวจ Final Runtime Configuration
- ตรวจ Final Model Path
- ตรวจ SHA256 ก่อนโหลด Model
- ตรวจ Ultralytics Runtime Version
- โหลด Model แบบ Read-only
- ตรวจ Exact Class Contract
- แสดง Final Inference Contract
- คืน Exit Code 0 เมื่อผ่าน
- คืน Exit Code 1 เมื่อ Critical Contract ไม่ผ่าน

เครื่องมือนี้จะไม่:
- Train
- Fine-tune
- Export
- Quantize
- Fuse + Save
- torch.save()
- YOLO.save()
- แก้ไข .pt
"""

import hashlib
import importlib.metadata
import sys
from pathlib import Path

from ultralytics import YOLO

from config import (
    FINAL_MODEL_RELEASE,
    FINAL_MODEL_SOURCE_NAME,
    FINAL_MODEL_MASTER_PATH,
    FINAL_MODEL_RUNTIME_PATH,

    EXPECTED_MODEL_SHA256,
    EXPECTED_MODEL_CLASSES,
    EXPECTED_ULTRALYTICS_VERSION,
    REFERENCE_PYTORCH_VERSION,

    MODEL_BACKEND,
    MODEL_PATH_PT,
    INFERENCE_DEVICE,

    IMGSZ,
    MODEL_NMS_IOU,
    MODEL_MAX_DET,
    MODEL_RECT,
    MODEL_BATCH,

    CLASS_THRESHOLDS,

    FRAMES_PER_SCAN,
    MIN_CONFIRM_FRAMES,
    FRAME_SAMPLE_GAP_SEC,
    CONSENSUS_IOU_THRESHOLD,

    STARTUP_WARMUP_RUNS,

    validate_runtime_config,
    validate_final_model_contract,
)


# ============================================================
# Result constants
# ============================================================

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


# ============================================================
# Result storage
# ============================================================

results = []


# ============================================================
# Result helper
# ============================================================

def add(
    status,
    name,
    detail="",
):

    results.append(
        (
            status,
            name,
            detail,
        )
    )

    if detail:

        print(
            f"[{status:<4}] "
            f"{name} - "
            f"{detail}"
        )

    else:

        print(
            f"[{status:<4}] "
            f"{name}"
        )


# ============================================================
# SHA256
# ============================================================

def sha256_file(
    path,
):
    """
    คำนวณ SHA256 แบบ Streaming

    เป็น Read-only operation
    ไม่แก้ไขไฟล์ Model
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


# ============================================================
# Package version
# ============================================================

def package_version(
    distribution_name,
):

    try:

        return (
            importlib.metadata.version(
                distribution_name
            )
        )

    except (
        importlib.metadata.PackageNotFoundError,
    ):

        return None

    except Exception:

        return None


# ============================================================
# Normalize model.names
# ============================================================

def normalize_model_names(
    names_object,
):
    """
    Normalize Ultralytics model.names เป็น:

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

            try:

                class_id = int(
                    class_id
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise RuntimeError(
                    "Invalid class ID: "
                    f"{class_id!r}"
                ) from exc

            normalized[
                class_id
            ] = (
                str(
                    class_name
                )
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
                    str(
                        class_name
                    )
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
        "Unsupported model.names type: "
        f"{type(names_object).__name__}"
    )


# ============================================================
# Config Contract
# ============================================================

def inspect_configuration():

    print()
    print(
        "-" * 72
    )
    print(
        "FINAL SOFTWARE CONTRACT"
    )
    print(
        "-" * 72
    )


    # --------------------------------------------------------
    # Generic runtime config
    # --------------------------------------------------------

    try:

        validate_runtime_config()

    except Exception as exc:

        add(
            FAIL,
            "Runtime configuration",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return False


    add(
        PASS,
        "Runtime configuration",
        "Generic validation passed",
    )


    # --------------------------------------------------------
    # Final R3-E6 contract
    # --------------------------------------------------------

    try:

        validate_final_model_contract()

    except Exception as exc:

        add(
            FAIL,
            "Final model configuration",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return False


    add(
        PASS,
        "Final model configuration",
        (
            f"{FINAL_MODEL_RELEASE} "
            "contract passed"
        ),
    )


    # --------------------------------------------------------
    # Display inference contract
    # --------------------------------------------------------

    candidate_confidence = min(
        CLASS_THRESHOLDS.values()
    )


    add(
        PASS,
        "Backend",
        MODEL_BACKEND,
    )

    add(
        PASS,
        "Device",
        INFERENCE_DEVICE,
    )

    add(
        PASS,
        "IMGSZ",
        str(
            IMGSZ
        ),
    )

    add(
        PASS,
        "Candidate confidence",
        f"{candidate_confidence:.2f}",
    )

    add(
        PASS,
        "Fire threshold",
        f"{CLASS_THRESHOLDS['fire']:.2f}",
    )

    add(
        PASS,
        "Smoke threshold",
        f"{CLASS_THRESHOLDS['smoke']:.2f}",
    )

    add(
        PASS,
        "NMS IoU",
        f"{MODEL_NMS_IOU:.2f}",
    )

    add(
        PASS,
        "max_det",
        str(
            MODEL_MAX_DET
        ),
    )

    add(
        PASS,
        "rect",
        str(
            MODEL_RECT
        ),
    )

    add(
        PASS,
        "batch",
        str(
            MODEL_BATCH
        ),
    )

    add(
        PASS,
        "Warm-up runs",
        str(
            STARTUP_WARMUP_RUNS
        ),
    )

    add(
        PASS,
        "Consensus",
        (
            f"{MIN_CONFIRM_FRAMES}/"
            f"{FRAMES_PER_SCAN} frames "
            f"| IoU="
            f"{CONSENSUS_IOU_THRESHOLD:.2f} "
            f"| gap="
            f"{FRAME_SAMPLE_GAP_SEC:.2f}s"
        ),
    )


    return True


# ============================================================
# Runtime environment
# ============================================================

def inspect_runtime_environment():

    print()
    print(
        "-" * 72
    )
    print(
        "AI RUNTIME ENVIRONMENT"
    )
    print(
        "-" * 72
    )


    # --------------------------------------------------------
    # Ultralytics
    # --------------------------------------------------------

    ultralytics_version = (
        package_version(
            "ultralytics"
        )
    )


    if (
        ultralytics_version
        ==
        EXPECTED_ULTRALYTICS_VERSION
    ):

        add(
            PASS,
            "Ultralytics",
            ultralytics_version,
        )

    else:

        add(
            FAIL,
            "Ultralytics",
            (
                "installed="
                f"{ultralytics_version or 'missing'} "
                "| required="
                f"{EXPECTED_ULTRALYTICS_VERSION}"
            ),
        )


    # --------------------------------------------------------
    # PyTorch
    # --------------------------------------------------------

    torch_version = (
        package_version(
            "torch"
        )
    )


    torch_base_version = (

        torch_version.split(
            "+",
            1,
        )[0]

        if torch_version

        else ""
    )


    if (
        torch_base_version
        ==
        REFERENCE_PYTORCH_VERSION
    ):

        add(
            PASS,
            "PyTorch reference",
            (
                torch_version
                or "unknown"
            ),
        )

    else:

        # PyTorch เป็น reference environment
        # ไม่ใช่ Frozen semantic contract แบบ Ultralytics

        add(
            WARN,
            "PyTorch reference",
            (
                "installed="
                f"{torch_version or 'missing'} "
                "| reference="
                f"{REFERENCE_PYTORCH_VERSION}"
            ),
        )


    # --------------------------------------------------------
    # torchvision
    # --------------------------------------------------------
    #
    # Model Team ไม่ได้บันทึก authoritative exact
    # torchvision version
    #
    # ดังนั้นแสดงผลอย่างเดียว
    # ไม่ใช้เป็น Final Model Contract Gate
    #
    # --------------------------------------------------------

    torchvision_version = (
        package_version(
            "torchvision"
        )
    )


    if torchvision_version:

        add(
            PASS,
            "torchvision",
            (
                f"{torchvision_version} "
                "| informational"
            ),
        )

    else:

        add(
            WARN,
            "torchvision",
            "distribution not found",
        )


# ============================================================
# Master artifact information
# ============================================================

def inspect_master_artifact():

    print()
    print(
        "-" * 72
    )
    print(
        "MASTER ARTIFACT"
    )
    print(
        "-" * 72
    )


    print(
        f"Source filename : "
        f"{FINAL_MODEL_SOURCE_NAME}"
    )

    print(
        f"Master path     : "
        f"{FINAL_MODEL_MASTER_PATH}"
    )


    master_path = Path(
        FINAL_MODEL_MASTER_PATH
    )


    # Master copy ใน repository เป็น useful integrity check
    # แต่ Runtime gate หลักคือ models/fire.pt

    if not master_path.is_file():

        add(
            WARN,
            "Master artifact",
            (
                "ไม่พบ repository master copy "
                "| Runtime artifact "
                "จะถูกตรวจแยกต่างหาก"
            ),
        )

        return


    try:

        master_sha = (
            sha256_file(
                master_path
            )
        )

    except Exception as exc:

        add(
            WARN,
            "Master artifact SHA256",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    if (
        master_sha.lower()
        ==
        EXPECTED_MODEL_SHA256.lower()
    ):

        add(
            PASS,
            "Master artifact SHA256",
            master_sha,
        )

    else:

        add(
            FAIL,
            "Master artifact SHA256",
            (
                "HASH MISMATCH "
                "| expected="
                f"{EXPECTED_MODEL_SHA256} "
                "| actual="
                f"{master_sha}"
            ),
        )


# ============================================================
# Runtime artifact
# ============================================================

def inspect_runtime_artifact():

    print()
    print(
        "-" * 72
    )
    print(
        "PRODUCTION RUNTIME ARTIFACT"
    )
    print(
        "-" * 72
    )


    runtime_path = (
        Path(
            MODEL_PATH_PT
        )
        .resolve()
    )


    expected_runtime_path = (
        Path(
            FINAL_MODEL_RUNTIME_PATH
        )
        .resolve()
    )


    print(
        f"Configured path : "
        f"{runtime_path}"
    )

    print(
        f"Expected path   : "
        f"{expected_runtime_path}"
    )


    # --------------------------------------------------------
    # Exact runtime path
    # --------------------------------------------------------

    if (
        runtime_path
        ==
        expected_runtime_path
    ):

        add(
            PASS,
            "Runtime model path",
            str(
                runtime_path
            ),
        )

    else:

        add(
            FAIL,
            "Runtime model path",
            (
                "configured="
                f"{runtime_path} "
                "| expected="
                f"{expected_runtime_path}"
            ),
        )

        return None


    # --------------------------------------------------------
    # File exists
    # --------------------------------------------------------

    if not runtime_path.is_file():

        add(
            FAIL,
            "Runtime model artifact",
            "File not found",
        )

        return None


    add(
        PASS,
        "Runtime model artifact",
        "File exists",
    )


    # --------------------------------------------------------
    # SHA256 BEFORE YOLO LOAD
    # --------------------------------------------------------

    try:

        actual_sha256 = (
            sha256_file(
                runtime_path
            )
        )

    except Exception as exc:

        add(
            FAIL,
            "Runtime SHA256",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return None


    print(
        f"Expected SHA256 : "
        f"{EXPECTED_MODEL_SHA256}"
    )

    print(
        f"Actual SHA256   : "
        f"{actual_sha256}"
    )


    if (
        actual_sha256.lower()
        !=
        EXPECTED_MODEL_SHA256.lower()
    ):

        add(
            FAIL,
            "Runtime SHA256",
            "MODEL ARTIFACT VERIFICATION FAIL",
        )

        return None


    add(
        PASS,
        "Runtime SHA256",
        (
            "Exact Final Artifact match"
        ),
    )


    return (
        runtime_path
    )


# ============================================================
# YOLO Model inspection
# ============================================================

def inspect_loaded_model(
    runtime_path,
):

    print()
    print(
        "-" * 72
    )
    print(
        "MODEL METADATA"
    )
    print(
        "-" * 72
    )


    if (
        runtime_path
        is None
    ):

        add(
            FAIL,
            "Model load",
            (
                "Blocked because Runtime "
                "Artifact verification failed"
            ),
        )

        return


    # ========================================================
    # Load ONLY after SHA verification
    # ========================================================

    try:

        model = (
            YOLO(
                str(
                    runtime_path
                )
            )
        )

    except Exception as exc:

        add(
            FAIL,
            "Model load",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    add(
        PASS,
        "Model load",
        "YOLO load successful",
    )


    # ========================================================
    # Exact Class Contract
    # ========================================================

    try:

        names = (
            normalize_model_names(
                model.names
            )
        )

    except Exception as exc:

        add(
            FAIL,
            "Class metadata",
            (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        )

        return


    print(
        f"Class count : "
        f"{len(names)}"
    )


    for (
        class_id,
        class_name,
    ) in sorted(
        names.items()
    ):

        print(
            f"  [{class_id}] "
            f"{class_name}"
        )


    if (
        names
        ==
        EXPECTED_MODEL_CLASSES
    ):

        add(
            PASS,
            "Exact class contract",
            str(
                names
            ),
        )

    else:

        add(
            FAIL,
            "Exact class contract",
            (
                "expected="
                f"{EXPECTED_MODEL_CLASSES} "
                "| actual="
                f"{names}"
            ),
        )


# ============================================================
# Summary
# ============================================================

def summary():

    pass_count = sum(

        status == PASS

        for (
            status,
            _,
            _,
        )
        in results
    )


    warn_count = sum(

        status == WARN

        for (
            status,
            _,
            _,
        )
        in results
    )


    fail_count = sum(

        status == FAIL

        for (
            status,
            _,
            _,
        )
        in results
    )


    print()
    print(
        "=" * 72
    )
    print(
        "FINAL MODEL INSPECTION SUMMARY"
    )
    print(
        "=" * 72
    )

    print(
        f"PASS : {pass_count}"
    )

    print(
        f"WARN : {warn_count}"
    )

    print(
        f"FAIL : {fail_count}"
    )

    print(
        "-" * 72
    )


    if fail_count:

        print(
            "FINAL MODEL CONTRACT STATUS: FAIL"
        )

        print(
            (
                "ห้ามใช้ Model นี้ใน "
                "Production Runtime "
                "จนกว่ารายการ FAIL จะถูกแก้"
            )
        )

        return 1


    if warn_count:

        print(
            (
                "FINAL MODEL CONTRACT STATUS: "
                "PASS WITH WARNINGS"
            )
        )

    else:

        print(
            "FINAL MODEL CONTRACT STATUS: PASS"
        )


    return 0


# ============================================================
# Main
# ============================================================

def main():

    results.clear()


    print(
        "=" * 72
    )

    print(
        "Smart Fire Detection v2"
    )

    print(
        (
            "Final AI Model "
            f"{FINAL_MODEL_RELEASE} "
            "- Inspector"
        )
    )

    print(
        "=" * 72
    )


    # --------------------------------------------------------
    # Software / Runtime Contract
    # --------------------------------------------------------

    inspect_configuration()


    # --------------------------------------------------------
    # Python AI environment
    # --------------------------------------------------------

    inspect_runtime_environment()


    # --------------------------------------------------------
    # Repository master copy
    # --------------------------------------------------------

    inspect_master_artifact()


    # --------------------------------------------------------
    # Production Runtime Artifact
    # --------------------------------------------------------

    runtime_path = (
        inspect_runtime_artifact()
    )


    # --------------------------------------------------------
    # Load Model only after Runtime SHA PASS
    # --------------------------------------------------------

    inspect_loaded_model(
        runtime_path
    )


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    return summary()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
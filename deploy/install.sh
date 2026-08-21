#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'


# ============================================================
# Smart Fire Detection v2
# Production Installer
# Final AI Model: R3-E6 Release V1
# ============================================================
#
# Target:
#
#   OS      : Debian 13 x86_64
#   Python  : 3.12
#   Backend : PyTorch
#   Device  : CPU
#
# This installer:
#
# - validates the Production platform
# - prepares runtime user/group/directories
# - prepares Python 3.12 venv
# - installs exact Final AI runtime dependencies
# - verifies dependency consistency
# - verifies Final Model SHA256
# - verifies exact Model classes
# - prepares production.env
# - validates Final AI variables in production.env
# - installs systemd unit files
# - validates systemd unit syntax
# - runs Offline Preflight
#
#
# This installer intentionally DOES NOT:
#
# - start main.py
# - start app.py
# - start systemd services
# - enable systemd services
# - move PTZ
# - connect RTSP
# - perform calibration
# - overwrite an existing production.env
# - Train / Fine-tune Model
# - Quantize Model
# - Export Model
# - install OpenVINO for Production Release V1
#
# ============================================================


# ============================================================
# Project paths
# ============================================================

PROJECT_DIR="/opt/smart-fire-detection-v2"

DEPLOY_DIR="${PROJECT_DIR}/deploy"

VENV_DIR="${PROJECT_DIR}/venv"

ENV_DIR="/etc/smart-fire-detection"

ENV_FILE="${ENV_DIR}/production.env"

SYSTEMD_DIR="/etc/systemd/system"


# ============================================================
# systemd
# ============================================================

DETECTION_UNIT="smart-fire-detection.service"

DASHBOARD_UNIT="smart-fire-dashboard.service"


# ============================================================
# Runtime account
# ============================================================

RUNTIME_USER="smartfire"

RUNTIME_GROUP="smartfire"


# ============================================================
# Python
# ============================================================

PYTHON_BIN="${PYTHON_BIN:-python3.12}"


# ============================================================
# Final Model R3-E6 Contract
# ============================================================

FINAL_MODEL_RELEASE="R3-E6"

FINAL_MODEL_SOURCE_NAME="fire_smoke_r3_e6_final.pt"

FINAL_MODEL_MASTER="${PROJECT_DIR}/models/final/${FINAL_MODEL_SOURCE_NAME}"

FINAL_MODEL_RUNTIME="${PROJECT_DIR}/models/fire.pt"

EXPECTED_MODEL_SHA256="49dc0464d99a6c250cf3c3e305d4149c3d4ce3ee354d9d7a5ae1cb8c53a22183"


# ============================================================
# Final Runtime Dependency Contract
# ============================================================

EXPECTED_ULTRALYTICS_VERSION="8.4.95"

EXPECTED_TORCH_VERSION="2.11.0"

EXPECTED_TORCHVISION_VERSION="0.26.0"

EXPECTED_OPENCV_VERSION="4.12.0.88"

EXPECTED_WAITRESS_VERSION="3.0.2"

PYTORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"


# ============================================================
# Logging
# ============================================================

log() {

    printf '\n[INFO] %s\n' "$*"
}


ok() {

    printf '[ OK ] %s\n' "$*"
}


warn() {

    printf '[WARN] %s\n' "$*" >&2
}


fail() {

    printf '[FAIL] %s\n' "$*" >&2

    exit 1
}


on_error() {

    local exit_code=$?
    local line_no=$1

    printf \
        '\n[FAIL] Installer stopped at line %s (exit=%s)\n' \
        "${line_no}" \
        "${exit_code}" \
        >&2

    exit "${exit_code}"
}


trap 'on_error ${LINENO}' ERR


# ============================================================
# Root
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then

    fail "Run this installer with sudo/root."

fi


# ============================================================
# Release V1 OpenVINO safety
# ============================================================
#
# Old installer supported:
#
#   INSTALL_OPENVINO=1
#
# Final Release V1 does NOT.
#
# This explicit check prevents an old deployment command
# from silently enabling an unapproved backend.
#
# ============================================================

if [[ "${INSTALL_OPENVINO:-0}" != "0" ]]; then

    fail \
        "OpenVINO installation is blocked for Final ${FINAL_MODEL_RELEASE} Release V1. PT is the approved Production backend."

fi


# ============================================================
# Project directory
# ============================================================

if [[ ! -d "${PROJECT_DIR}" ]]; then

    fail "Project directory not found: ${PROJECT_DIR}"

fi


if [[ ! -d "${DEPLOY_DIR}" ]]; then

    fail "Deploy directory not found: ${DEPLOY_DIR}"

fi


cd "${PROJECT_DIR}"


# ============================================================
# Required project files
# ============================================================

REQUIRED_FILES=(

    "${PROJECT_DIR}/main.py"

    "${PROJECT_DIR}/app.py"

    "${PROJECT_DIR}/config.py"

    "${PROJECT_DIR}/detection.py"

    "${PROJECT_DIR}/preflight.py"

    "${PROJECT_DIR}/inspect_model.py"

    "${PROJECT_DIR}/benchmark_inference.py"

    "${PROJECT_DIR}/requirements.txt"

    "${DEPLOY_DIR}/production.env.example"

    "${DEPLOY_DIR}/${DETECTION_UNIT}"

    "${DEPLOY_DIR}/${DASHBOARD_UNIT}"

    "${FINAL_MODEL_MASTER}"

    "${FINAL_MODEL_RUNTIME}"
)


for required_file in "${REQUIRED_FILES[@]}"; do

    if [[ ! -f "${required_file}" ]]; then

        fail "Missing required file: ${required_file}"

    fi

done


ok "Required project files found"


# ============================================================
# Debian validation
# ============================================================

log "Validating operating system"


if [[ ! -f /etc/os-release ]]; then

    fail "/etc/os-release not found"

fi


# shellcheck disable=SC1091
source /etc/os-release


if [[ "${ID:-}" != "debian" ]]; then

    fail \
        "Unsupported OS: ${ID:-unknown}. Debian 13 is required."

fi


if [[ "${VERSION_ID:-}" != "13" ]]; then

    fail \
        "Unsupported Debian version: ${VERSION_ID:-unknown}. Debian 13 is required."

fi


ok "Debian ${VERSION_ID}"


# ============================================================
# Architecture
# ============================================================

ARCH="$(uname -m)"


if [[ "${ARCH}" != "x86_64" ]]; then

    fail \
        "Unsupported architecture: ${ARCH}. x86_64 is required."

fi


ok "Architecture: ${ARCH}"


# ============================================================
# Commands
# ============================================================

log "Checking required system commands"


REQUIRED_COMMANDS=(

    getent
    groupadd
    useradd
    runuser
    install
    find
    chmod
    chown
    chgrp
    systemctl
    systemd-analyze
)


for command_name in "${REQUIRED_COMMANDS[@]}"; do

    if ! command -v "${command_name}" >/dev/null 2>&1; then

        fail \
            "Required command not found: ${command_name}"

    fi

done


ok "Required system commands available"


# ============================================================
# Existing service safety
# ============================================================

log "Checking service state"


if systemctl is-active --quiet "${DETECTION_UNIT}"; then

    fail \
        "${DETECTION_UNIT} is running. Stop it before installation/update."

fi


if systemctl is-active --quiet "${DASHBOARD_UNIT}"; then

    fail \
        "${DASHBOARD_UNIT} is running. Stop it before installation/update."

fi


ok "Production services are not running"


# ============================================================
# Python 3.12
# ============================================================

log "Validating Python 3.12"


if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then

    fail "${PYTHON_BIN} not found"

fi


PYTHON_VERSION="$(
    "${PYTHON_BIN}" -c \
        'import sys; print(".".join(map(str, sys.version_info[:3])))'
)"


case "${PYTHON_VERSION}" in

    3.12.*)

        ;;

    *)

        fail \
            "Python 3.12.x required; found ${PYTHON_VERSION}"

        ;;

esac


ok "Python ${PYTHON_VERSION}"


# ============================================================
# Final Model SHA256 helper
# ============================================================

calculate_sha256() {

    local file_path=$1

    "${PYTHON_BIN}" \
        - "${file_path}" <<'PY'

import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])

digest = hashlib.sha256()

with path.open("rb") as handle:

    while True:

        chunk = handle.read(1024 * 1024)

        if not chunk:
            break

        digest.update(chunk)

print(digest.hexdigest())

PY
}


# ============================================================
# Final Model Artifact Verification
# ============================================================
#
# IMPORTANT:
#
# Verify bytes BEFORE creating/changing runtime environment.
#
# ============================================================

log "Verifying Final AI Model artifacts"


MASTER_SHA256="$(
    calculate_sha256 \
        "${FINAL_MODEL_MASTER}"
)"


RUNTIME_SHA256="$(
    calculate_sha256 \
        "${FINAL_MODEL_RUNTIME}"
)"


if [[ "${MASTER_SHA256}" != "${EXPECTED_MODEL_SHA256}" ]]; then

    fail \
        "Final master SHA256 mismatch. Expected=${EXPECTED_MODEL_SHA256} Actual=${MASTER_SHA256}"

fi


ok "Final master SHA256 verified"


if [[ "${RUNTIME_SHA256}" != "${EXPECTED_MODEL_SHA256}" ]]; then

    fail \
        "Runtime model SHA256 mismatch. Expected=${EXPECTED_MODEL_SHA256} Actual=${RUNTIME_SHA256}"

fi


ok "Runtime model SHA256 verified"


if [[ "${MASTER_SHA256}" != "${RUNTIME_SHA256}" ]]; then

    fail \
        "Master and Runtime Model artifacts are not byte-identical"

fi


ok "Master and Runtime artifacts are byte-identical"


# ============================================================
# Runtime group
# ============================================================

log "Preparing runtime group"


if getent group "${RUNTIME_GROUP}" >/dev/null 2>&1; then

    ok "Group already exists: ${RUNTIME_GROUP}"

else

    groupadd \
        --system \
        "${RUNTIME_GROUP}"

    ok "Created group: ${RUNTIME_GROUP}"

fi


# ============================================================
# Runtime user
# ============================================================

log "Preparing runtime user"


if id -u "${RUNTIME_USER}" >/dev/null 2>&1; then

    ok "User already exists: ${RUNTIME_USER}"

else

    useradd \
        --system \
        --gid "${RUNTIME_GROUP}" \
        --home-dir "${PROJECT_DIR}" \
        --no-create-home \
        --shell /usr/sbin/nologin \
        "${RUNTIME_USER}"

    ok "Created user: ${RUNTIME_USER}"

fi


# ============================================================
# Runtime directories
# ============================================================

log "Preparing runtime directories"


install \
    -d \
    -m 0750 \
    -o "${RUNTIME_USER}" \
    -g "${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/static"


install \
    -d \
    -m 0750 \
    -o "${RUNTIME_USER}" \
    -g "${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/calibration"


install \
    -d \
    -m 0750 \
    -o root \
    -g "${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/models"


install \
    -d \
    -m 0750 \
    -o root \
    -g "${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/models/final"


install \
    -d \
    -m 0750 \
    -o root \
    -g root \
    "${ENV_DIR}"


chown -R \
    "${RUNTIME_USER}:${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/static" \
    "${PROJECT_DIR}/calibration"


chown -R \
    "root:${RUNTIME_GROUP}" \
    "${PROJECT_DIR}/models"


find "${PROJECT_DIR}/static" \
    -type d \
    -exec chmod 0750 {} +


find "${PROJECT_DIR}/calibration" \
    -type d \
    -exec chmod 0750 {} +


find "${PROJECT_DIR}/models" \
    -type d \
    -exec chmod 0750 {} +


find "${PROJECT_DIR}/static" \
    -type f \
    -exec chmod 0640 {} +


find "${PROJECT_DIR}/calibration" \
    -type f \
    -exec chmod 0640 {} +


find "${PROJECT_DIR}/models" \
    -type f \
    -exec chmod 0640 {} +


ok "Runtime directories prepared"


# ============================================================
# Project source permissions
# ============================================================

log "Applying project source permissions"


chgrp \
    "${RUNTIME_GROUP}" \
    "${PROJECT_DIR}"


chmod \
    g+rx \
    "${PROJECT_DIR}"


while IFS= read -r -d '' python_file; do

    chgrp \
        "${RUNTIME_GROUP}" \
        "${python_file}"

    chmod \
        g+r \
        "${python_file}"

done < <(

    find "${PROJECT_DIR}" \
        -maxdepth 1 \
        -type f \
        -name '*.py' \
        -print0
)


ok "Project source permissions prepared"


# ============================================================
# Python virtual environment
# ============================================================

log "Preparing Python virtual environment"


if [[ ! -x "${VENV_DIR}/bin/python" ]]; then

    "${PYTHON_BIN}" \
        -m venv \
        "${VENV_DIR}"

    ok "Created venv: ${VENV_DIR}"

else

    ok "Existing venv found: ${VENV_DIR}"

fi


VENV_PYTHON="${VENV_DIR}/bin/python"


# ============================================================
# Validate venv Python
# ============================================================

VENV_PYTHON_VERSION="$(
    "${VENV_PYTHON}" -c \
        'import sys; print(".".join(map(str, sys.version_info[:3])))'
)"


case "${VENV_PYTHON_VERSION}" in

    3.12.*)

        ;;

    *)

        fail \
            "Existing venv is not Python 3.12: ${VENV_PYTHON_VERSION}"

        ;;

esac


ok "venv Python ${VENV_PYTHON_VERSION}"


# ============================================================
# Packaging tools
# ============================================================

log "Updating pip/setuptools/wheel"


"${VENV_PYTHON}" \
    -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel


ok "Python packaging tools updated"


# ============================================================
# Exact CPU PyTorch stack
# ============================================================
#
# Required Production baseline:
#
#   torch       2.11.0 CPU
#   torchvision 0.26.0
#
# A CPU build with a different version is NOT accepted here.
#
# ============================================================

log "Checking Final CPU PyTorch stack"


CPU_TORCH_OK=0


if "${VENV_PYTHON}" - <<PY >/dev/null 2>&1

import torch
import torchvision


def base_version(value):
    return str(value).split("+", 1)[0]


if base_version(torch.__version__) != "${EXPECTED_TORCH_VERSION}":
    raise SystemExit(1)


if base_version(torchvision.__version__) != "${EXPECTED_TORCHVISION_VERSION}":
    raise SystemExit(1)


if torch.version.cuda is not None:
    raise SystemExit(1)


raise SystemExit(0)

PY

then

    CPU_TORCH_OK=1

fi


if [[ "${CPU_TORCH_OK}" -eq 1 ]]; then

    ok \
        "Exact CPU PyTorch stack already installed"

else

    log \
        "Installing torch=${EXPECTED_TORCH_VERSION} / torchvision=${EXPECTED_TORCHVISION_VERSION} CPU"


    "${VENV_PYTHON}" \
        -m pip install \
        --upgrade \
        "torch==${EXPECTED_TORCH_VERSION}" \
        "torchvision==${EXPECTED_TORCHVISION_VERSION}" \
        --index-url "${PYTORCH_CPU_INDEX}"


    ok "Exact CPU PyTorch stack installed"

fi


# ============================================================
# Remove conflicting OpenCV wheel families
# ============================================================
#
# These distributions share the cv2 namespace.
#
# Production must contain only:
#
#   opencv-python==4.12.0.88
#
# ============================================================

log "Removing conflicting OpenCV distributions"


"${VENV_PYTHON}" \
    -m pip uninstall \
    -y \
    opencv-python-headless \
    opencv-contrib-python \
    opencv-contrib-python-headless \
    >/dev/null 2>&1 \
    || true


ok "Conflicting OpenCV cleanup completed"


# ============================================================
# Project dependencies
# ============================================================

log "Installing project runtime dependencies"


"${VENV_PYTHON}" \
    -m pip install \
    -r "${PROJECT_DIR}/requirements.txt"


ok "Project runtime dependencies installed"


# ============================================================
# Enforce one OpenCV distribution
# ============================================================
#
# Reinstall after removing another cv2 distribution because
# uninstalling a competing OpenCV package may remove shared
# cv2 files from the environment.
#
# ============================================================

log "Enforcing exact OpenCV runtime"


"${VENV_PYTHON}" \
    -m pip uninstall \
    -y \
    opencv-python-headless \
    opencv-contrib-python \
    opencv-contrib-python-headless \
    >/dev/null 2>&1 \
    || true


"${VENV_PYTHON}" \
    -m pip install \
    --force-reinstall \
    --no-deps \
    "opencv-python==${EXPECTED_OPENCV_VERSION}"


ok \
    "opencv-python==${EXPECTED_OPENCV_VERSION} enforced"


# ============================================================
# Dependency consistency
# ============================================================

log "Running pip dependency check"


"${VENV_PYTHON}" \
    -m pip check


ok "pip dependency check passed"


# ============================================================
# Exact Runtime Dependency Contract
# ============================================================

log "Validating Final R3-E6 runtime dependency contract"


"${VENV_PYTHON}" - <<PY

import importlib.metadata

import cv2
import numpy
import torch
import torchvision
import ultralytics
import waitress


EXPECTED_ULTRALYTICS = "${EXPECTED_ULTRALYTICS_VERSION}"
EXPECTED_TORCH = "${EXPECTED_TORCH_VERSION}"
EXPECTED_TORCHVISION = "${EXPECTED_TORCHVISION_VERSION}"
EXPECTED_OPENCV = "${EXPECTED_OPENCV_VERSION}"
EXPECTED_WAITRESS = "${EXPECTED_WAITRESS_VERSION}"


def version(name):

    try:
        return importlib.metadata.version(name)

    except importlib.metadata.PackageNotFoundError:
        return None


def base(value):

    return str(value).split("+", 1)[0]


# ------------------------------------------------------------
# OpenCV distributions
# ------------------------------------------------------------

opencv_distributions = {

    name: version(name)

    for name in (
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
    )

    if version(name) is not None
}


if len(opencv_distributions) != 1:

    raise SystemExit(
        "OpenCV distribution conflict: "
        f"{opencv_distributions}"
    )


if opencv_distributions.get("opencv-python") != EXPECTED_OPENCV:

    raise SystemExit(
        "opencv-python mismatch: "
        f"{opencv_distributions}"
    )


# ------------------------------------------------------------
# Ultralytics
# ------------------------------------------------------------

if version("ultralytics") != EXPECTED_ULTRALYTICS:

    raise SystemExit(
        "Ultralytics mismatch: "
        f"{version('ultralytics')} "
        f"!= {EXPECTED_ULTRALYTICS}"
    )


# ------------------------------------------------------------
# PyTorch CPU
# ------------------------------------------------------------

if base(torch.__version__) != EXPECTED_TORCH:

    raise SystemExit(
        "torch mismatch: "
        f"{torch.__version__} "
        f"!= {EXPECTED_TORCH}"
    )


if base(torchvision.__version__) != EXPECTED_TORCHVISION:

    raise SystemExit(
        "torchvision mismatch: "
        f"{torchvision.__version__} "
        f"!= {EXPECTED_TORCHVISION}"
    )


if torch.version.cuda is not None:

    raise SystemExit(
        "Production requires CPU PyTorch; "
        f"CUDA build detected: {torch.version.cuda}"
    )


# ------------------------------------------------------------
# Waitress
# ------------------------------------------------------------

if version("waitress") != EXPECTED_WAITRESS:

    raise SystemExit(
        "Waitress mismatch: "
        f"{version('waitress')} "
        f"!= {EXPECTED_WAITRESS}"
    )


print("numpy      :", numpy.__version__)
print("opencv     :", cv2.__version__)
print("torch      :", torch.__version__)
print("torchvision:", torchvision.__version__)
print("ultralytics:", ultralytics.__version__)
print("waitress   :", version("waitress"))

print("Final dependency contract: PASS")

PY


ok "Final runtime dependency contract verified"


# ============================================================
# config.py Final Contract
# ============================================================

log "Validating config.py Final Model Contract"


"${VENV_PYTHON}" - <<'PY'

import config

config.validate_runtime_config()

config.validate_final_model_contract()

print(
    "Release     :",
    config.FINAL_MODEL_RELEASE,
)

print(
    "Backend     :",
    config.MODEL_BACKEND,
)

print(
    "Device      :",
    config.INFERENCE_DEVICE,
)

print(
    "IMGSZ       :",
    config.IMGSZ,
)

print(
    "NMS IoU     :",
    config.MODEL_NMS_IOU,
)

print(
    "max_det     :",
    config.MODEL_MAX_DET,
)

print(
    "rect        :",
    config.MODEL_RECT,
)

print(
    "batch       :",
    config.MODEL_BATCH,
)

print(
    "Config Final Model Contract: PASS"
)

PY


ok "config.py Final Model Contract verified"


# ============================================================
# Final Model Inspector
# ============================================================
#
# Loads Model only AFTER:
#
# - SHA verified
# - dependencies verified
# - config contract verified
#
# inspect_model.py is read-only.
#
# ============================================================

log "Running Final Model Inspector"


"${VENV_PYTHON}" \
    "${PROJECT_DIR}/inspect_model.py"


ok "Final Model Inspector passed"


# ============================================================
# venv permissions
# ============================================================

log "Applying venv permissions"


chown -R \
    "root:${RUNTIME_GROUP}" \
    "${VENV_DIR}"


chmod -R \
    g+rX,o-rwx \
    "${VENV_DIR}"


ok "venv permissions applied"


# ============================================================
# Runtime-user access
# ============================================================

log "Verifying runtime-user access"


if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -r "${PROJECT_DIR}/main.py"
then

    fail \
        "${RUNTIME_USER} cannot read main.py"

fi


if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -r "${PROJECT_DIR}/app.py"
then

    fail \
        "${RUNTIME_USER} cannot read app.py"

fi


if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -r "${FINAL_MODEL_RUNTIME}"
then

    fail \
        "${RUNTIME_USER} cannot read models/fire.pt"

fi


if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -x "${VENV_DIR}/bin/python"
then

    fail \
        "${RUNTIME_USER} cannot execute venv Python"

fi


if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -x "${VENV_DIR}/bin/waitress-serve"
then

    fail \
        "${RUNTIME_USER} cannot execute waitress-serve"

fi


runuser \
    -u "${RUNTIME_USER}" \
    -- "${VENV_PYTHON}" \
    -c \
    'import cv2, flask, numpy, torch, torchvision, ultralytics, waitress; print("runtime imports: OK")'


ok "Runtime-user access verified"


# ============================================================
# Production environment
# ============================================================

log "Preparing production environment"


if [[ -f "${ENV_FILE}" ]]; then

    ok "Existing production.env preserved"

else

    install \
        -m 0600 \
        -o root \
        -g root \
        "${DEPLOY_DIR}/production.env.example" \
        "${ENV_FILE}"

    ok \
        "Created ${ENV_FILE} from Final R3-E6 template"

fi


chown \
    root:root \
    "${ENV_FILE}"


chmod \
    0600 \
    "${ENV_FILE}"


# ============================================================
# Validate production.env Final AI variables
# ============================================================
#
# Existing production.env is NEVER overwritten.
#
# Therefore an upgrade from an old installation may still
# contain:
#
#   IMGSZ=640
#   FIRE_THRESHOLD=0.50
#   SMOKE_THRESHOLD=0.60
#
# Installer must refuse this before Production use.
#
# Secret values are not printed.
#
# ============================================================

log "Validating production.env Final AI Contract"


ENV_FILE_PATH="${ENV_FILE}" \
"${VENV_PYTHON}" - <<'PY'

import os
from pathlib import Path


path = Path(
    os.environ["ENV_FILE_PATH"]
)


required = {

    "MODEL_BACKEND":
        "pt",

    "MODEL_PATH_PT":
        "models/fire.pt",

    "INFERENCE_DEVICE":
        "cpu",

    "IMGSZ":
        "768",

    "MODEL_NMS_IOU":
        "0.70",

    "MODEL_MAX_DET":
        "300",

    "MODEL_RECT":
        "0",

    "MODEL_BATCH":
        "1",

    "FIRE_THRESHOLD":
        "0.25",

    "SMOKE_THRESHOLD":
        "0.25",

    "FRAMES_PER_SCAN":
        "3",

    "MIN_CONFIRM_FRAMES":
        "2",

    "FRAME_SAMPLE_GAP_SEC":
        "0.15",

    "CONSENSUS_IOU_THRESHOLD":
        "0.30",

    "STARTUP_WARMUP_RUNS":
        "3",
}


values = {}


for raw_line in path.read_text(
    encoding="utf-8"
).splitlines():

    line = raw_line.strip()

    if (
        not line
        or
        line.startswith("#")
        or
        "=" not in line
    ):
        continue


    key, value = (
        line.split(
            "=",
            1,
        )
    )


    key = key.strip()

    value = value.strip()


    if (
        len(value) >= 2
        and
        value[0] == value[-1]
        and
        value[0] in {
            "'",
            '"',
        }
    ):

        value = value[1:-1]


    values[key] = value


errors = []


for key, expected in required.items():

    actual = values.get(key)

    if actual is None:

        errors.append(
            f"{key}: missing"
        )

        continue


    if actual != expected:

        errors.append(
            f"{key}: "
            f"actual={actual!r}, "
            f"expected={expected!r}"
        )


if errors:

    print(
        "production.env Final AI Contract: FAIL"
    )

    for error in errors:

        print(
            " -",
            error,
        )

    raise SystemExit(1)


print(
    "production.env Final AI Contract: PASS"
)

PY


ok "production.env Final AI Contract verified"


# ============================================================
# Install systemd units
# ============================================================

log "Installing systemd unit files"


install \
    -m 0644 \
    -o root \
    -g root \
    "${DEPLOY_DIR}/${DETECTION_UNIT}" \
    "${SYSTEMD_DIR}/${DETECTION_UNIT}"


install \
    -m 0644 \
    -o root \
    -g root \
    "${DEPLOY_DIR}/${DASHBOARD_UNIT}" \
    "${SYSTEMD_DIR}/${DASHBOARD_UNIT}"


systemctl \
    daemon-reload


ok "systemd unit files installed"


# ============================================================
# Validate systemd units
# ============================================================

log "Validating systemd units"


systemd-analyze \
    verify \
    "${SYSTEMD_DIR}/${DETECTION_UNIT}" \
    "${SYSTEMD_DIR}/${DASHBOARD_UNIT}"


ok "systemd unit validation passed"


# ============================================================
# Offline Preflight
# ============================================================
#
# This does not:
#
# - connect RTSP
# - move PTZ
# - load Production site calibration requirements
#
# It DOES validate:
#
# - dependency stack
# - Final config contract
# - model path
# - model SHA256
#
# ============================================================

log "Running Offline Preflight"


"${VENV_PYTHON}" \
    "${PROJECT_DIR}/preflight.py" \
    --offline


ok "Offline Preflight passed"


# ============================================================
# Calibration status
# ============================================================

INTRINSICS_FILE="${PROJECT_DIR}/calibration/camera_intrinsics.json"

SITE_FILE="${PROJECT_DIR}/calibration/site.json"

DISTANCE_FILE="${PROJECT_DIR}/calibration/distance_global.json"


if [[ -f "${INTRINSICS_FILE}" ]]; then

    ok "Intrinsics file found"

else

    warn \
        "camera_intrinsics.json not found"

fi


if [[ -f "${SITE_FILE}" ]]; then

    ok "Site bearing calibration found"

else

    warn \
        "site.json not found - Site calibration is still required"

fi


if [[ -f "${DISTANCE_FILE}" ]]; then

    ok "Distance calibration found"

else

    warn \
        "distance_global.json not found - Site calibration is still required"

fi


# ============================================================
# Final status
# ============================================================

printf '\n'

printf '%s\n' \
    "============================================================"

printf '%s\n' \
    " Smart Fire Detection v2 - Installation Complete"

printf '%s\n' \
    " Final AI Model R3-E6 Release V1"

printf '%s\n' \
    "============================================================"


printf '\nProject:\n'

printf '  %s\n' \
    "${PROJECT_DIR}"


printf '\nPython:\n'

printf '  %s\n' \
    "${VENV_PYTHON_VERSION}"


printf '\nFinal Model:\n'

printf '  Release : %s\n' \
    "${FINAL_MODEL_RELEASE}"

printf '  Runtime : %s\n' \
    "${FINAL_MODEL_RUNTIME}"

printf '  SHA256  : %s\n' \
    "${EXPECTED_MODEL_SHA256}"


printf '\nAI Runtime:\n'

printf '  Backend      : pt\n'

printf '  Device       : cpu\n'

printf '  IMGSZ        : 768\n'

printf '  Confidence   : 0.25\n'

printf '  NMS IoU      : 0.70\n'

printf '  max_det      : 300\n'

printf '  rect         : False\n'

printf '  batch        : 1\n'


printf '\nProduction environment:\n'

printf '  %s\n' \
    "${ENV_FILE}"


printf '\nDetection unit:\n'

printf '  %s\n' \
    "${SYSTEMD_DIR}/${DETECTION_UNIT}"


printf '\nDashboard unit:\n'

printf '  %s\n' \
    "${SYSTEMD_DIR}/${DASHBOARD_UNIT}"


printf '\nIMPORTANT:\n'

printf '%s\n' \
    "  Production services were NOT started."

printf '%s\n' \
    "  Production services were NOT enabled."

printf '%s\n' \
    "  Calibration was NOT performed."

printf '%s\n' \
    "  OpenVINO was NOT installed or approved by this installer."


printf '\nNext:\n'

printf '%s\n' \
    "  1. Configure real Camera/Telegram/Site values in production.env"

printf '%s\n' \
    "  2. Complete Site bearing/distance calibration"

printf '%s\n' \
    "  3. Run Production hardware benchmark"

printf '%s\n' \
    "  4. Validate Camera / PTZ / fresh-stable frames"

printf '%s\n' \
    "  5. Run Full Preflight"

printf '%s\n' \
    "  6. Run PTZ + Final AI full sweep"

printf '%s\n' \
    "  7. Validate alerts/dashboard"

printf '%s\n' \
    "  8. Only then enable/start Production services"


printf '\n'

printf '%s\n' \
    "Installer finished successfully."

printf '%s\n' \
    "============================================================"
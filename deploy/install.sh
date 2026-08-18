#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

# ============================================================
# Smart Fire Detection v2
# Production Installer
# ============================================================
#
# Target:
#   Debian 13
#   Python 3.12
#
# This installer prepares the production environment.
#
# It intentionally DOES NOT:
#
#   - start main.py
#   - start app.py
#   - start systemd services
#   - enable systemd services
#   - perform calibration
#   - overwrite an existing production.env
#
# ============================================================


# ============================================================
# Configuration
# ============================================================

PROJECT_DIR="/opt/smart-fire-detection-v2"
DEPLOY_DIR="${PROJECT_DIR}/deploy"

VENV_DIR="${PROJECT_DIR}/venv"

ENV_DIR="/etc/smart-fire-detection"
ENV_FILE="${ENV_DIR}/production.env"

SYSTEMD_DIR="/etc/systemd/system"

DETECTION_UNIT="smart-fire-detection.service"
DASHBOARD_UNIT="smart-fire-dashboard.service"

RUNTIME_USER="smartfire"
RUNTIME_GROUP="smartfire"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

# OpenVINO is optional on Debian 13.
#
# Default:
#   INSTALL_OPENVINO=0
#
# To request installation later:
#
#   sudo env INSTALL_OPENVINO=1 ./deploy/install.sh
#
INSTALL_OPENVINO="${INSTALL_OPENVINO:-0}"


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

    printf '\n[FAIL] Installer stopped at line %s (exit=%s)\n' \
        "${line_no}" \
        "${exit_code}" \
        >&2

    exit "${exit_code}"
}

trap 'on_error ${LINENO}' ERR


# ============================================================
# Root check
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then
    fail "Run this installer with sudo/root."
fi


# ============================================================
# Project path validation
# ============================================================

if [[ ! -d "${PROJECT_DIR}" ]]; then
    fail "Project directory not found: ${PROJECT_DIR}"
fi

if [[ ! -d "${DEPLOY_DIR}" ]]; then
    fail "Deploy directory not found: ${DEPLOY_DIR}"
fi


# ============================================================
# Required project files
# ============================================================

REQUIRED_FILES=(
    "${PROJECT_DIR}/main.py"
    "${PROJECT_DIR}/app.py"
    "${PROJECT_DIR}/config.py"
    "${PROJECT_DIR}/requirements.txt"
    "${DEPLOY_DIR}/production.env.example"
    "${DEPLOY_DIR}/${DETECTION_UNIT}"
    "${DEPLOY_DIR}/${DASHBOARD_UNIT}"
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
    fail "Unsupported OS: ${ID:-unknown}. Debian 13 is required."
fi

if [[ "${VERSION_ID:-}" != "13" ]]; then
    fail "Unsupported Debian version: ${VERSION_ID:-unknown}. Debian 13 is required."
fi

ok "Debian ${VERSION_ID}"


# ============================================================
# Architecture validation
# ============================================================

ARCH="$(uname -m)"

if [[ "${ARCH}" != "x86_64" ]]; then
    fail "Unsupported architecture: ${ARCH}. x86_64 is required."
fi

ok "Architecture: ${ARCH}"


# ============================================================
# Required system commands
# ============================================================

log "Checking required system commands"

REQUIRED_COMMANDS=(
    getent
    groupadd
    useradd
    runuser
    install
    find
    systemctl
    systemd-analyze
)

for command_name in "${REQUIRED_COMMANDS[@]}"; do

    if ! command -v "${command_name}" >/dev/null 2>&1; then
        fail "Required command not found: ${command_name}"
    fi

done

ok "Required system commands available"


# ============================================================
# Existing service safety
# ============================================================

log "Checking service state"

if systemctl is-active --quiet "${DETECTION_UNIT}"; then
    fail "${DETECTION_UNIT} is running. Stop it before installation/update."
fi

if systemctl is-active --quiet "${DASHBOARD_UNIT}"; then
    fail "${DASHBOARD_UNIT} is running. Stop it before installation/update."
fi

ok "Production services are not running"


# ============================================================
# Python 3.12 validation
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
        fail "Python 3.12.x required; found ${PYTHON_VERSION}"
        ;;

esac

ok "Python ${PYTHON_VERSION}"


# ============================================================
# Runtime group
# ============================================================

log "Preparing runtime group"

if getent group "${RUNTIME_GROUP}" >/dev/null 2>&1; then

    ok "Group already exists: ${RUNTIME_GROUP}"

else

    groupadd --system "${RUNTIME_GROUP}"

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
# Project directory access
# ============================================================

chgrp "${RUNTIME_GROUP}" "${PROJECT_DIR}"

chmod g+rx "${PROJECT_DIR}"

while IFS= read -r -d '' python_file; do

    chgrp "${RUNTIME_GROUP}" "${python_file}"

    chmod g+r "${python_file}"

done < <(
    find "${PROJECT_DIR}" \
        -maxdepth 1 \
        -type f \
        -name '*.py' \
        -print0
)


# ============================================================
# Python virtual environment
# ============================================================

log "Preparing Python virtual environment"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then

    "${PYTHON_BIN}" -m venv "${VENV_DIR}"

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
        fail "Existing venv is not Python 3.12: ${VENV_PYTHON_VERSION}"
        ;;

esac

ok "venv Python ${VENV_PYTHON_VERSION}"


# ============================================================
# Packaging tools
# ============================================================

log "Updating pip/setuptools/wheel"

"${VENV_PYTHON}" -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel

ok "Python packaging tools updated"


# ============================================================
# CPU-only PyTorch
# ============================================================
#
# Production baseline is CPU.
#
# If an existing CUDA PyTorch build is detected,
# replace it with the official CPU wheel.
#
# ============================================================

log "Checking CPU PyTorch"

CPU_TORCH_OK=0

if "${VENV_PYTHON}" - <<'PY' >/dev/null 2>&1
import torch
import torchvision

if torch.version.cuda is not None:
    raise SystemExit(1)

raise SystemExit(0)
PY
then
    CPU_TORCH_OK=1
fi


if [[ "${CPU_TORCH_OK}" -eq 1 ]]; then

    ok "CPU-only PyTorch already installed"

else

    log "Installing official CPU-only PyTorch"

    "${VENV_PYTHON}" -m pip install \
        --upgrade \
        torch \
        torchvision \
        --index-url https://download.pytorch.org/whl/cpu

    ok "CPU-only PyTorch installed"

fi


# ============================================================
# Project runtime dependencies
# ============================================================

log "Installing project dependencies"

"${VENV_PYTHON}" -m pip install \
    -r "${PROJECT_DIR}/requirements.txt"

ok "Project dependencies installed"


# ============================================================
# OpenVINO
# ============================================================
#
# Optional on Debian 13.
#
# INSTALL_OPENVINO=0
#     Skip installation.
#
# INSTALL_OPENVINO=1
#     Attempt installation.
#
# A failed optional OpenVINO install does not invalidate
# the PyTorch CPU production baseline.
#
# ============================================================

case "${INSTALL_OPENVINO}" in

    0)

        log "OpenVINO installation skipped (optional)"

        ;;

    1)

        log "Attempting optional OpenVINO installation"

        if "${VENV_PYTHON}" -m pip install --upgrade openvino; then

            ok "OpenVINO installed"

        else

            warn "OpenVINO installation failed"
            warn "PyTorch CPU baseline remains available"

        fi

        ;;

    *)

        fail "INSTALL_OPENVINO must be 0 or 1"

        ;;

esac


# ============================================================
# Dependency consistency
# ============================================================

log "Running pip dependency check"

"${VENV_PYTHON}" -m pip check

ok "pip dependency check passed"


# ============================================================
# Core import verification
# ============================================================

log "Verifying runtime Python imports"

"${VENV_PYTHON}" - <<'PY'
import importlib.metadata

import cv2
import flask
import numpy
import psutil
import requests
import torch
import torchvision
import ultralytics
import waitress

print("numpy      :", numpy.__version__)
print("opencv     :", cv2.__version__)
print("requests   :", requests.__version__)
print("psutil     :", psutil.__version__)
print("Flask      :", flask.__version__ if hasattr(flask, "__version__") else importlib.metadata.version("Flask"))
print("Waitress   :", importlib.metadata.version("waitress"))
print("torch      :", torch.__version__)
print("torchvision:", torchvision.__version__)
print("ultralytics:", ultralytics.__version__)

if torch.version.cuda is not None:
    raise SystemExit(
        "Production baseline requires CPU-only PyTorch, "
        f"but CUDA build was detected: {torch.version.cuda}"
    )

print("PyTorch CPU build: OK")
PY

ok "Core imports verified"


# ============================================================
# OpenVINO verification
# ============================================================

if "${VENV_PYTHON}" -c \
    'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("openvino") else 1)' \
    >/dev/null 2>&1
then

    "${VENV_PYTHON}" - <<'PY'
from openvino import get_version

print("OpenVINO   :", get_version())
PY

    ok "OpenVINO import verified"

else

    warn "OpenVINO is not installed"
    warn "This is allowed while MODEL_BACKEND=pt"

fi


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
# Runtime user verification
# ============================================================

log "Verifying runtime-user access"

if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -r "${PROJECT_DIR}/main.py"
then
    fail "${RUNTIME_USER} cannot read main.py"
fi

if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -r "${PROJECT_DIR}/app.py"
then
    fail "${RUNTIME_USER} cannot read app.py"
fi

if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -x "${VENV_DIR}/bin/python"
then
    fail "${RUNTIME_USER} cannot execute venv Python"
fi

if ! runuser \
    -u "${RUNTIME_USER}" \
    -- test -x "${VENV_DIR}/bin/waitress-serve"
then
    fail "${RUNTIME_USER} cannot execute waitress-serve"
fi

runuser \
    -u "${RUNTIME_USER}" \
    -- "${VENV_PYTHON}" \
    -c 'import flask, waitress, torch, ultralytics; print("runtime imports: OK")'

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

    ok "Created ${ENV_FILE} from template"

fi

chown root:root "${ENV_FILE}"

chmod 0600 "${ENV_FILE}"


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

systemctl daemon-reload

ok "systemd unit files installed"


# ============================================================
# Validate systemd units
# ============================================================

log "Validating systemd units"

systemd-analyze verify \
    "${SYSTEMD_DIR}/${DETECTION_UNIT}" \
    "${SYSTEMD_DIR}/${DASHBOARD_UNIT}"

ok "systemd unit validation passed"


# ============================================================
# Model status
# ============================================================

MODEL_PT="${PROJECT_DIR}/models/fire.pt"

if [[ -f "${MODEL_PT}" ]]; then

    ok "PyTorch model found: ${MODEL_PT}"

else

    warn "Model not found: ${MODEL_PT}"
    warn "Copy the validated production model before Full Preflight"

fi


# ============================================================
# Calibration status
# ============================================================

INTRINSICS_FILE="${PROJECT_DIR}/calibration/camera_intrinsics.json"
SITE_FILE="${PROJECT_DIR}/calibration/site.json"
DISTANCE_FILE="${PROJECT_DIR}/calibration/distance_global.json"

if [[ -f "${INTRINSICS_FILE}" ]]; then
    ok "Intrinsics file found"
else
    warn "camera_intrinsics.json not found"
fi

if [[ -f "${SITE_FILE}" ]]; then
    ok "Site bearing calibration found"
else
    warn "site.json not found"
fi

if [[ -f "${DISTANCE_FILE}" ]]; then
    ok "Distance calibration found"
else
    warn "distance_global.json not found"
fi


# ============================================================
# Final status
# ============================================================

printf '\n'
printf '%s\n' "============================================================"
printf '%s\n' " Smart Fire Detection v2 - Installation Complete"
printf '%s\n' "============================================================"

printf '\nProject:\n'
printf '  %s\n' "${PROJECT_DIR}"

printf '\nPython:\n'
printf '  %s\n' "${VENV_PYTHON_VERSION}"

printf '\nProduction environment:\n'
printf '  %s\n' "${ENV_FILE}"

printf '\nDetection unit:\n'
printf '  %s\n' "${SYSTEMD_DIR}/${DETECTION_UNIT}"

printf '\nDashboard unit:\n'
printf '  %s\n' "${SYSTEMD_DIR}/${DASHBOARD_UNIT}"

printf '\nIMPORTANT:\n'
printf '%s\n' "  Production services were NOT started."
printf '%s\n' "  Production services were NOT enabled."
printf '%s\n' "  Calibration was NOT performed."

printf '\nNext:\n'
printf '%s\n' "  1. Configure production.env"
printf '%s\n' "  2. Run Offline Preflight"
printf '%s\n' "  3. Benchmark Production hardware"
printf '%s\n' "  4. Validate Camera / PTZ / Calibration"
printf '%s\n' "  5. Run Full Preflight"
printf '%s\n' "  6. Run Full Sweep"
printf '%s\n' "  7. Only then enable/start services"

printf '\n'
printf '%s\n' "Installer finished successfully."
printf '%s\n' "============================================================"
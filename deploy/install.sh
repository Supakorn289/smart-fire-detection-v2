#!/usr/bin/env bash

set -Eeuo pipefail


# ============================================================
# Smart Fire Detection v2
# Production Installer
# ============================================================
#
# หน้าที่:
#
# - ตรวจสอบว่าอยู่บน Linux / Debian
# - ตรวจสอบ Python 3.12
# - สร้าง system user: smartfire
# - สร้าง Python virtual environment
# - ติดตั้ง Python dependencies
# - ติดตั้ง CPU-only PyTorch
# - ติดตั้ง OpenVINO
# - สร้าง Production environment file
# - ติดตั้ง systemd service
#
# สิ่งที่ไฟล์นี้จะไม่ทำ:
#
# - ไม่ Start main.py
# - ไม่ Enable service อัตโนมัติ
# - ไม่แก้ Calibration
# - ไม่เขียนทับ production.env เดิม
# - ไม่เขียนทับ Site configuration
#
# ============================================================


# ============================================================
# Constants
# ============================================================

PROJECT_DIR="/opt/smart-fire-detection-v2"

SERVICE_USER="smartfire"
SERVICE_GROUP="smartfire"

CONFIG_DIR="/etc/smart-fire-detection"

ENV_FILE="${CONFIG_DIR}/production.env"

SERVICE_NAME="smart-fire-detection.service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

VENV_DIR="${PROJECT_DIR}/venv"

VENV_PYTHON="${VENV_DIR}/bin/python"


# ============================================================
# Helper
# ============================================================

info() {

    echo
    echo "============================================================"
    echo "$1"
    echo "============================================================"

}


ok() {

    echo "[OK] $1"

}


warn() {

    echo "[WARN] $1"

}


fail() {

    echo
    echo "[ERROR] $1"
    echo

    exit 1

}


# ============================================================
# Root check
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then

    fail "กรุณารันด้วย sudo: sudo ./deploy/install.sh"

fi


# ============================================================
# Operating system
# ============================================================

info "1. Checking operating system"


if [[ "$(uname -s)" != "Linux" ]]; then

    fail "install.sh ใช้สำหรับ Linux Production Server เท่านั้น"

fi


if [[ ! -f /etc/debian_version ]]; then

    fail "ไม่พบ Debian environment"

fi


ok "Debian detected"


if [[ -f /etc/os-release ]]; then

    # shellcheck disable=SC1091
    source /etc/os-release

    echo "OS      : ${PRETTY_NAME:-Debian}"

fi


# ============================================================
# Project directory
# ============================================================

info "2. Checking project directory"


if [[ ! -d "${PROJECT_DIR}" ]]; then

    fail "
ไม่พบโปรเจกต์ที่:

${PROJECT_DIR}

ต้องนำโปรเจกต์ไปไว้ที่ Path นี้ก่อน
"

fi


required_files=(

    "${PROJECT_DIR}/main.py"

    "${PROJECT_DIR}/config.py"

    "${PROJECT_DIR}/requirements.txt"

    "${PROJECT_DIR}/deploy/production.env.example"

    "${PROJECT_DIR}/deploy/smart-fire-detection.service"

)


for file in "${required_files[@]}"; do

    if [[ ! -f "${file}" ]]; then

        fail "ไม่พบไฟล์ที่จำเป็น: ${file}"

    fi

done


ok "Project structure พร้อม"


# ============================================================
# Protect running production service
# ============================================================

info "3. Checking existing service"


if systemctl is-active \
    --quiet \
    "${SERVICE_NAME}" \
    2>/dev/null
then

    fail "
${SERVICE_NAME} กำลังทำงานอยู่

Installer จะไม่แก้ Environment หรือ Python packages
ขณะที่ Runtime กำลังทำงาน

หยุด Service ก่อน:

sudo systemctl stop ${SERVICE_NAME}
"

fi


ok "Service ไม่ได้กำลังทำงาน"


# ============================================================
# Python
# ============================================================

info "4. Checking Python 3.12"


if ! command -v \
    "${PYTHON_BIN}" \
    >/dev/null 2>&1
then

    fail "
ไม่พบ ${PYTHON_BIN}

โปรเจกต์นี้ใช้ Python 3.12

Debian 13 มี Python รุ่นอื่นเป็นค่าเริ่มต้น
ดังนั้น Installer จะไม่ใช้ 'python3' แทนโดยอัตโนมัติ

ต้องติดตั้ง Python 3.12 ก่อน
แล้วจึงกลับมารัน install.sh ใหม่
"

fi


PYTHON_VERSION="$(
    "${PYTHON_BIN}" \
    -c \
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'
)"


PYTHON_MAJOR_MINOR="$(
    "${PYTHON_BIN}" \
    -c \
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
)"


echo "Python : ${PYTHON_VERSION}"


if [[ "${PYTHON_MAJOR_MINOR}" != "3.12" ]]; then

    fail "
Python version ไม่ถูกต้อง

พบ:
${PYTHON_VERSION}

ต้องการ:
Python 3.12.x
"

fi


ok "Python 3.12 พร้อม"


# ============================================================
# smartfire group
# ============================================================

info "5. Creating service account"


if getent group \
    "${SERVICE_GROUP}" \
    >/dev/null 2>&1
then

    ok "Group ${SERVICE_GROUP} มีอยู่แล้ว"

else

    groupadd \
        --system \
        "${SERVICE_GROUP}"

    ok "สร้าง Group ${SERVICE_GROUP}"

fi


# ============================================================
# smartfire user
# ============================================================

if id \
    "${SERVICE_USER}" \
    >/dev/null 2>&1
then

    ok "User ${SERVICE_USER} มีอยู่แล้ว"

else

    useradd \
        --system \
        --gid "${SERVICE_GROUP}" \
        --home-dir "${PROJECT_DIR}" \
        --no-create-home \
        --shell /usr/sbin/nologin \
        "${SERVICE_USER}"

    ok "สร้าง User ${SERVICE_USER}"

fi


# ============================================================
# Runtime directories
# ============================================================

info "6. Preparing runtime directories"


mkdir -p \
    "${PROJECT_DIR}/static"

mkdir -p \
    "${PROJECT_DIR}/calibration"

mkdir -p \
    "${PROJECT_DIR}/models"


# Runtime ต้องเขียน static/
chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/static"


# Calibration tools ต้องสามารถบันทึก Calibration ได้
chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/calibration"


ok "Runtime directories พร้อม"


# ============================================================
# Python virtual environment
# ============================================================

info "7. Preparing Python virtual environment"


if [[ -x "${VENV_PYTHON}" ]]; then

    EXISTING_VENV_VERSION="$(
        "${VENV_PYTHON}" \
        -c \
        'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    )"

    if [[ "${EXISTING_VENV_VERSION}" != "3.12" ]]; then

        fail "
พบ venv เดิม แต่ใช้ Python ${EXISTING_VENV_VERSION}

Installer จะไม่ลบ venv ให้เอง

Path:
${VENV_DIR}

กรุณาตรวจสอบก่อนลบหรือเปลี่ยนด้วยตนเอง
"

    fi

    ok "พบ Python 3.12 venv เดิม"

else

    echo "Creating venv..."

    if ! "${PYTHON_BIN}" \
        -m venv \
        "${VENV_DIR}"
    then

        fail "
สร้าง venv ไม่สำเร็จ

ตรวจสอบว่า Python 3.12 มี module venv/ensurepip พร้อม
"

    fi

    ok "สร้าง venv สำเร็จ"

fi


# ============================================================
# Upgrade Python packaging tools
# ============================================================

info "8. Updating pip tools"


"${VENV_PYTHON}" \
    -m pip \
    install \
    --upgrade \
    pip \
    setuptools \
    wheel


ok "pip tools พร้อม"


# ============================================================
# CPU-only PyTorch
# ============================================================

info "9. Installing CPU-only PyTorch"


"${VENV_PYTHON}" \
    -m pip \
    install \
    torch \
    torchvision \
    --index-url \
    https://download.pytorch.org/whl/cpu


ok "CPU-only PyTorch พร้อม"


# ============================================================
# Project dependencies
# ============================================================

info "10. Installing project dependencies"


"${VENV_PYTHON}" \
    -m pip \
    install \
    -r \
    "${PROJECT_DIR}/requirements.txt"


ok "Project dependencies พร้อม"


# ============================================================
# OpenVINO
# ============================================================

info "11. Installing OpenVINO"


"${VENV_PYTHON}" \
    -m pip \
    install \
    openvino


ok "OpenVINO พร้อม"


# ============================================================
# Verify imports
# ============================================================

info "12. Verifying Python runtime"


"${VENV_PYTHON}" - <<'PY'

import sys

print(
    "Python:",
    sys.version.split()[0],
)

packages = [
    "cv2",
    "numpy",
    "requests",
    "psutil",
    "flask",
    "torch",
    "ultralytics",
    "openvino",
]

failed = []

for package in packages:

    try:

        module = __import__(
            package
        )

        version = getattr(
            module,
            "__version__",
            "unknown",
        )

        print(
            f"[OK] {package:<12} "
            f"{version}"
        )

    except Exception as exc:

        failed.append(
            (
                package,
                str(exc),
            )
        )


if failed:

    print()

    for package, error in failed:

        print(
            f"[FAIL] {package}: "
            f"{error}"
        )

    raise SystemExit(1)

PY


ok "Python runtime verification ผ่าน"


# ============================================================
# Production environment directory
# ============================================================

info "13. Preparing production environment"


install \
    -d \
    -m 0755 \
    "${CONFIG_DIR}"


if [[ -f "${ENV_FILE}" ]]; then

    warn "
พบ Production environment เดิม:

${ENV_FILE}

Installer จะไม่เขียนทับไฟล์นี้
"

else

    install \
        -m 0600 \
        "${PROJECT_DIR}/deploy/production.env.example" \
        "${ENV_FILE}"

    ok "สร้าง ${ENV_FILE}"

    warn "
ไฟล์ Production environment ยังเป็น TEMPLATE

ต้องแก้ค่าจริงก่อนใช้งาน
"

fi


# ============================================================
# systemd service
# ============================================================

info "14. Installing systemd service"


install \
    -m 0644 \
    "${PROJECT_DIR}/deploy/smart-fire-detection.service" \
    "${SERVICE_FILE}"


systemctl daemon-reload


ok "ติดตั้ง ${SERVICE_NAME}"


# ============================================================
# Model check
# ============================================================

info "15. Checking AI model"


MODEL_PT="${PROJECT_DIR}/models/fire.pt"

MODEL_OV="${PROJECT_DIR}/models/fire_openvino_model"


if [[ -f "${MODEL_PT}" ]]; then

    ok "พบ models/fire.pt"

else

    warn "
ยังไม่พบ:

${MODEL_PT}

ต้องนำ Model มาใส่ก่อน Benchmark/Production
"

fi


if [[ -d "${MODEL_OV}" ]]; then

    ok "พบ OpenVINO model"

else

    warn "
ยังไม่พบ:

${MODEL_OV}

สามารถ Export ภายหลังด้วย export_openvino.py
"

fi


# ============================================================
# Calibration check
# ============================================================

info "16. Checking site calibration"


SITE_FILE="${PROJECT_DIR}/calibration/site.json"

DISTANCE_FILE="${PROJECT_DIR}/calibration/distance_global.json"


if [[ -f "${SITE_FILE}" ]]; then

    ok "พบ site.json"

else

    warn "
ยังไม่มี site.json

ต้องทำ Bearing calibration
หลังติดตั้งกล้องในสถานที่จริง
"

fi


if [[ -f "${DISTANCE_FILE}" ]]; then

    ok "พบ distance_global.json"

else

    warn "
ยังไม่มี distance_global.json

ต้องทำ Distance calibration
หลังติดตั้งกล้องในสถานที่จริง
"

fi


# ============================================================
# Permissions
# ============================================================

info "17. Final permissions"


chmod 0755 \
    "${PROJECT_DIR}"


chmod -R \
    u+rwX \
    "${PROJECT_DIR}/static"

chmod -R \
    g+rwX \
    "${PROJECT_DIR}/static"


chmod -R \
    u+rwX \
    "${PROJECT_DIR}/calibration"

chmod -R \
    g+rwX \
    "${PROJECT_DIR}/calibration"


ok "Permissions พร้อม"


# ============================================================
# IMPORTANT:
#
# เราจะยังไม่ Start หรือ Enable Service
#
# เพราะก่อน Production ต้อง:
#
# - ตั้ง production.env
# - Preflight
# - Benchmark
# - Bearing calibration
# - Distance calibration
# - Verification
#
# ============================================================


info "INSTALLATION COMPLETE"


echo
echo "Project:"
echo "${PROJECT_DIR}"

echo
echo "Python:"
echo "${VENV_PYTHON}"

echo
echo "Environment:"
echo "${ENV_FILE}"

echo
echo "Service:"
echo "${SERVICE_FILE}"

echo
echo "------------------------------------------------------------"

echo
echo "Service ยังไม่ได้ Start"
echo "และยังไม่ได้ Enable ตอน Boot"

echo
echo "นี่เป็นพฤติกรรมที่ตั้งใจไว้"

echo
echo "ขั้นต่อไปต้องทำ:"
echo
echo "1. ตรวจ Production environment"
echo "2. รัน Preflight"
echo "3. Benchmark PyTorch"
echo "4. Benchmark OpenVINO"
echo "5. ทำ Site calibration"
echo "6. Verify"
echo "7. Full Sweep Test"
echo "8. จึงค่อย Enable Production Service"

echo
echo "------------------------------------------------------------"

echo
echo "ห้ามรัน main.py เป็นขั้นทดสอบแรก"
echo

exit 0
#!/usr/bin/env bash
# deploy/install.sh

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
# - ตรวจสอบโครงสร้าง Project
# - ป้องกันการติดตั้งทับขณะ Service กำลังทำงาน
# - สร้าง system user/group: smartfire
# - เตรียม Runtime directories
# - สร้าง Python virtual environment
# - ติดตั้ง CPU-only PyTorch
# - ติดตั้ง Project dependencies
# - ติดตั้ง OpenVINO
# - ตรวจสอบ Python imports
# - สร้าง Production environment file
# - ติดตั้ง Detection systemd service
# - ติดตั้ง Dashboard systemd service
# - ตรวจสอบ AI Model
# - ตรวจสอบ Calibration files
# - กำหนด Runtime permissions
#
#
# สิ่งที่ไฟล์นี้จะ "ไม่" ทำ:
#
# - ไม่ Start main.py
# - ไม่ Start app.py
# - ไม่ Enable systemd services อัตโนมัติ
# - ไม่ทำ Camera Calibration
# - ไม่ทำ Bearing Calibration
# - ไม่ทำ Distance Calibration
# - ไม่เขียนทับ production.env เดิม
# - ไม่เขียนทับ Site configuration
# - ไม่สร้างหรือแก้ Camera credentials
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


# ============================================================
# Detection service
# ============================================================

SERVICE_NAME="smart-fire-detection.service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

SOURCE_SERVICE_FILE="${PROJECT_DIR}/deploy/${SERVICE_NAME}"


# ============================================================
# Dashboard service
# ============================================================

DASHBOARD_SERVICE_NAME="smart-fire-dashboard.service"

DASHBOARD_SERVICE_FILE="/etc/systemd/system/${DASHBOARD_SERVICE_NAME}"

SOURCE_DASHBOARD_SERVICE_FILE="${PROJECT_DIR}/deploy/${DASHBOARD_SERVICE_NAME}"


# ============================================================
# Python
# ============================================================

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

VENV_DIR="${PROJECT_DIR}/venv"

VENV_PYTHON="${VENV_DIR}/bin/python"


# ============================================================
# Models
# ============================================================

MODEL_PT="${PROJECT_DIR}/models/fire.pt"

MODEL_OV="${PROJECT_DIR}/models/fire_openvino_model"


# ============================================================
# Calibration
# ============================================================

INTRINSICS_FILE="${PROJECT_DIR}/calibration/camera_intrinsics.json"

SITE_FILE="${PROJECT_DIR}/calibration/site.json"

DISTANCE_FILE="${PROJECT_DIR}/calibration/distance_global.json"


# ============================================================
# Helper functions
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
# Error handler
# ============================================================

on_error() {

    local exit_code=$?
    local line_no=$1

    echo
    echo "============================================================"
    echo "[ERROR] Installation failed"
    echo "============================================================"
    echo "Line      : ${line_no}"
    echo "Exit code : ${exit_code}"
    echo
    echo "แก้ปัญหาแล้วสามารถรัน Installer ใหม่ได้"
    echo "Installer ถูกออกแบบให้รองรับการรันซ้ำ"
    echo "============================================================"

    exit "${exit_code}"
}


trap 'on_error ${LINENO}' ERR


# ============================================================
# Root check
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then

    fail "
กรุณารันด้วย sudo:

sudo ./deploy/install.sh
"

fi


# ============================================================
# 1. Operating system
# ============================================================

info "1. Checking operating system"


if [[ "$(uname -s)" != "Linux" ]]; then

    fail "
install.sh ใช้สำหรับ Linux Production Server เท่านั้น
"

fi


if [[ ! -f /etc/debian_version ]]; then

    fail "
ไม่พบ Debian environment

Installer นี้จัดทำสำหรับ Debian Production Server
"

fi


ok "Debian detected"


if [[ -f /etc/os-release ]]; then

    # shellcheck disable=SC1091
    source /etc/os-release

    echo "OS      : ${PRETTY_NAME:-Debian}"

fi


echo "Kernel  : $(uname -r)"
echo "Arch    : $(uname -m)"


# ============================================================
# systemd check
# ============================================================

if ! command -v systemctl >/dev/null 2>&1; then

    fail "
ไม่พบ systemctl

Production Installer ต้องใช้ systemd
"

fi


ok "systemd available"


# ============================================================
# 2. Project directory
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

    "${PROJECT_DIR}/app.py"

    "${PROJECT_DIR}/config.py"

    "${PROJECT_DIR}/camera.py"

    "${PROJECT_DIR}/ptz.py"

    "${PROJECT_DIR}/detection.py"

    "${PROJECT_DIR}/requirements.txt"

    "${PROJECT_DIR}/preflight.py"

    "${PROJECT_DIR}/benchmark_inference.py"

    "${PROJECT_DIR}/deploy/install.sh"

    "${PROJECT_DIR}/deploy/production.env.example"

    "${SOURCE_SERVICE_FILE}"

    "${SOURCE_DASHBOARD_SERVICE_FILE}"

)


for file in "${required_files[@]}"; do

    if [[ ! -f "${file}" ]]; then

        fail "
ไม่พบไฟล์ที่จำเป็น:

${file}
"

    fi

done


ok "Project structure พร้อม"


# ============================================================
# Production environment template safety
# ============================================================
#
# CAMERA_LAT / CAMERA_LON ถูกอ่านเป็น float
#
# ดังนั้น Template ต้องใช้:
#
# CAMERA_LAT=nan
# CAMERA_LON=nan
#
# หรือค่าตัวเลขจริง
#
# ห้ามเป็น CHANGE_ME
#
# ============================================================

PRODUCTION_TEMPLATE="${PROJECT_DIR}/deploy/production.env.example"


if grep -Eq \
    '^[[:space:]]*CAMERA_(LAT|LON)[[:space:]]*=[[:space:]]*CHANGE_ME[[:space:]]*$' \
    "${PRODUCTION_TEMPLATE}"
then

    fail "
deploy/production.env.example ยังมี:

CAMERA_LAT=CHANGE_ME
หรือ
CAMERA_LON=CHANGE_ME

config.py ต้องแปลงสองค่านี้เป็น float

กรุณาแก้ Template เป็น:

CAMERA_LAT=nan
CAMERA_LON=nan

ก่อนรัน Installer
"

fi


ok "Production environment template format พร้อม"


# ============================================================
# 3. Protect running production services
# ============================================================

info "3. Checking existing production services"


if systemctl is-active \
    --quiet \
    "${SERVICE_NAME}" \
    2>/dev/null
then

    fail "
${SERVICE_NAME} กำลังทำงานอยู่

Installer จะไม่แก้ Python packages,
Environment หรือ Service files
ขณะที่ Detection Runtime กำลังทำงาน

หยุด Service ก่อน:

sudo systemctl stop ${SERVICE_NAME}
"

fi


if systemctl is-active \
    --quiet \
    "${DASHBOARD_SERVICE_NAME}" \
    2>/dev/null
then

    fail "
${DASHBOARD_SERVICE_NAME} กำลังทำงานอยู่

Installer จะไม่แก้ Python packages,
Environment หรือ Service files
ขณะที่ Dashboard กำลังทำงาน

หยุด Service ก่อน:

sudo systemctl stop ${DASHBOARD_SERVICE_NAME}
"

fi


ok "Production services ไม่ได้กำลังทำงาน"


# ============================================================
# 4. Python
# ============================================================

info "4. Checking Python 3.12"


if ! command -v \
    "${PYTHON_BIN}" \
    >/dev/null 2>&1
then

    fail "
ไม่พบ ${PYTHON_BIN}

โปรเจกต์นี้ใช้ Python 3.12

Installer จะไม่ใช้ python3 เวอร์ชันอื่น
แทนโดยอัตโนมัติ

ต้องติดตั้ง Python 3.12 ก่อน
แล้วกลับมารัน Installer ใหม่
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
# Python venv capability
# ============================================================

if ! "${PYTHON_BIN}" \
    -c 'import venv, ensurepip' \
    >/dev/null 2>&1
then

    fail "
Python 3.12 ไม่มี venv หรือ ensurepip พร้อมใช้งาน

ต้องเตรียม Python 3.12 environment
ให้สามารถสร้าง virtual environment ได้ก่อน
"

fi


ok "Python venv capability พร้อม"


# ============================================================
# 5. smartfire group
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
# 6. Runtime directories
# ============================================================

info "6. Preparing runtime directories"


mkdir -p \
    "${PROJECT_DIR}/static" \
    "${PROJECT_DIR}/static/alert_spool" \
    "${PROJECT_DIR}/calibration" \
    "${PROJECT_DIR}/models"


# ============================================================
# Runtime writes static/
# ============================================================

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/static"


# ============================================================
# Calibration tools write calibration/
# ============================================================

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/calibration"


ok "Runtime directories พร้อม"


# ============================================================
# 7. Python virtual environment
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

ตรวจสอบว่า Python 3.12
มี module venv/ensurepip พร้อม
"

    fi


    ok "สร้าง venv สำเร็จ"

fi


# ============================================================
# Venv Python check
# ============================================================

if [[ ! -x "${VENV_PYTHON}" ]]; then

    fail "
ไม่พบ Python ภายใน venv:

${VENV_PYTHON}
"

fi


echo "Venv Python:"
"${VENV_PYTHON}" --version


# ============================================================
# 8. Upgrade Python packaging tools
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
# 9. CPU-only PyTorch
# ============================================================
#
# Production Server ใช้ CPU inference
#
# ติดตั้ง CPU wheel โดยตรงเพื่อไม่ให้ดึง
# CUDA build ที่ไม่จำเป็น
#
# ============================================================

info "9. Installing CPU-only PyTorch"


"${VENV_PYTHON}" \
    -m pip \
    install \
    --upgrade \
    torch \
    torchvision \
    --index-url \
    https://download.pytorch.org/whl/cpu


ok "CPU-only PyTorch พร้อม"


# ============================================================
# 10. Project dependencies
# ============================================================

info "10. Installing project dependencies"


"${VENV_PYTHON}" \
    -m pip \
    install \
    -r \
    "${PROJECT_DIR}/requirements.txt"


ok "Project dependencies พร้อม"


# ============================================================
# 11. OpenVINO
# ============================================================

info "11. Installing OpenVINO"


"${VENV_PYTHON}" \
    -m pip \
    install \
    --upgrade \
    openvino


ok "OpenVINO พร้อม"


# ============================================================
# Dependency consistency
# ============================================================

info "12. Checking Python dependency consistency"


if ! "${VENV_PYTHON}" \
    -m pip \
    check
then

    fail "
pip dependency check ไม่ผ่าน

ตรวจสอบ Package versions ก่อน Production
"

fi


ok "Python dependency consistency ผ่าน"


# ============================================================
# 13. Verify imports
# ============================================================

info "13. Verifying Python runtime"


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
    "waitress",
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
# PyTorch CPU verification
# ============================================================

info "14. Verifying PyTorch device"


"${VENV_PYTHON}" - <<'PY'

import torch

print(
    "Torch version :",
    torch.__version__,
)

print(
    "CUDA available:",
    torch.cuda.is_available(),
)

print(
    "Torch threads :",
    torch.get_num_threads(),
)

PY


ok "PyTorch verification ผ่าน"


# ============================================================
# 15. Production environment directory
# ============================================================

info "15. Preparing production environment"


install \
    -d \
    -m 0755 \
    -o root \
    -g root \
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
        -o root \
        -g root \
        "${PRODUCTION_TEMPLATE}" \
        "${ENV_FILE}"

    ok "สร้าง ${ENV_FILE}"

    warn "
ไฟล์ Production environment ยังเป็น TEMPLATE

ต้องแก้ค่าจริงก่อนใช้งาน Production
"

fi


# ============================================================
# Environment permissions
# ============================================================

chown \
    root:root \
    "${ENV_FILE}"


chmod \
    0600 \
    "${ENV_FILE}"


ok "Production environment permission = 0600"


# ============================================================
# Detect invalid LAT/LON placeholders
# ============================================================

if grep -Eq \
    '^[[:space:]]*CAMERA_(LAT|LON)[[:space:]]*=[[:space:]]*CHANGE_ME[[:space:]]*$' \
    "${ENV_FILE}"
then

    fail "
Production environment มี CAMERA_LAT/CAMERA_LON
เป็น CHANGE_ME

ไฟล์:

${ENV_FILE}

ให้ใช้ nan ระหว่างที่ยังไม่ได้ตั้ง Site:

CAMERA_LAT=nan
CAMERA_LON=nan

หรือเปลี่ยนเป็นพิกัดจริงก่อน Full Production Validation
"

fi


# ============================================================
# Camera credential placeholders
# ============================================================

if grep -Eq \
    '^[[:space:]]*CAMERA_(IP|USER|PWD)[[:space:]]*=[[:space:]]*CHANGE_ME[[:space:]]*$' \
    "${ENV_FILE}"
then

    warn "
production.env ยังมี Camera Placeholder

นี่ไม่ทำให้ Installer ล้ม
แต่ Full Preflight จะไม่ผ่านจนกว่าจะตั้งค่าจริง
"

fi


# ============================================================
# 16. Install systemd services
# ============================================================

info "16. Installing systemd services"


# ============================================================
# Detection service
# ============================================================

install \
    -m 0644 \
    -o root \
    -g root \
    "${SOURCE_SERVICE_FILE}" \
    "${SERVICE_FILE}"


ok "ติดตั้ง ${SERVICE_NAME}"


# ============================================================
# Dashboard service
# ============================================================

install \
    -m 0644 \
    -o root \
    -g root \
    "${SOURCE_DASHBOARD_SERVICE_FILE}" \
    "${DASHBOARD_SERVICE_FILE}"


ok "ติดตั้ง ${DASHBOARD_SERVICE_NAME}"


# ============================================================
# Reload systemd
# ============================================================

systemctl daemon-reload


ok "systemd daemon reload completed"


# ============================================================
# Optional systemd unit verification
# ============================================================

if command -v \
    systemd-analyze \
    >/dev/null 2>&1
then

    echo
    echo "Checking systemd unit syntax..."


    if systemd-analyze verify \
        "${SERVICE_FILE}" \
        "${DASHBOARD_SERVICE_FILE}"
    then

        ok "systemd unit verification ผ่าน"

    else

        warn "
systemd-analyze verify พบคำเตือนหรือข้อผิดพลาด

ตรวจ Service files ก่อน Enable Production
"

    fi

fi


# ============================================================
# Ensure Installer did not enable/start services
# ============================================================

if systemctl is-active \
    --quiet \
    "${SERVICE_NAME}" \
    2>/dev/null
then

    fail "
${SERVICE_NAME} กลายเป็น Active โดยไม่คาดคิด

Installer นี้ไม่ควร Start Service
"

fi


if systemctl is-active \
    --quiet \
    "${DASHBOARD_SERVICE_NAME}" \
    2>/dev/null
then

    fail "
${DASHBOARD_SERVICE_NAME} กลายเป็น Active โดยไม่คาดคิด

Installer นี้ไม่ควร Start Service
"

fi


ok "Services ยังไม่ถูก Start ตามนโยบาย"


# ============================================================
# 17. AI model check
# ============================================================

info "17. Checking AI models"


if [[ -f "${MODEL_PT}" ]]; then

    ok "พบ models/fire.pt"

    echo "Model size:"
    du -h "${MODEL_PT}" 2>/dev/null || true

else

    warn "
ยังไม่พบ:

${MODEL_PT}

ต้องนำ Model มาใส่ก่อน
AI Benchmark / Camera AI Test / Production
"

fi


if [[ -d "${MODEL_OV}" ]]; then

    ok "พบ OpenVINO model"

    echo "OpenVINO model directory:"
    du -sh "${MODEL_OV}" 2>/dev/null || true

else

    warn "
ยังไม่พบ:

${MODEL_OV}

สามารถ Export ภายหลังด้วย:

${VENV_PYTHON} ${PROJECT_DIR}/export_openvino.py
"

fi


# ============================================================
# 18. Calibration check
# ============================================================

info "18. Checking calibration files"


# ============================================================
# Camera intrinsics
# ============================================================

if [[ -f "${INTRINSICS_FILE}" ]]; then

    ok "พบ camera_intrinsics.json"

else

    warn "
ยังไม่มี:

${INTRINSICS_FILE}

หาก Camera / Lens / Zoom / Resolution
ยังไม่เคยผ่าน Intrinsics Calibration
ต้องทำก่อน Production
"

fi


# ============================================================
# Bearing calibration
# ============================================================

if [[ -f "${SITE_FILE}" ]]; then

    ok "พบ site.json"

else

    warn "
ยังไม่มี:

${SITE_FILE}

ต้องทำ Bearing Calibration
หลังติดตั้งกล้องในสถานที่จริง
"

fi


# ============================================================
# Distance calibration
# ============================================================

if [[ -f "${DISTANCE_FILE}" ]]; then

    ok "พบ distance_global.json"

else

    warn "
ยังไม่มี:

${DISTANCE_FILE}

ต้องทำ Distance Calibration
หลังติดตั้งกล้องในสถานที่จริง
"

fi


# ============================================================
# 19. Final permissions
# ============================================================

info "19. Applying final permissions"


# ============================================================
# Project root
# ============================================================

chmod \
    0755 \
    "${PROJECT_DIR}"


# ============================================================
# Runtime writable directories
# ============================================================

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/static"


chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${PROJECT_DIR}/calibration"


chmod -R \
    u+rwX \
    "${PROJECT_DIR}/static"


chmod -R \
    g+rwX \
    "${PROJECT_DIR}/static"


chmod -R \
    o-rwx \
    "${PROJECT_DIR}/static"


chmod -R \
    u+rwX \
    "${PROJECT_DIR}/calibration"


chmod -R \
    g+rwX \
    "${PROJECT_DIR}/calibration"


chmod -R \
    o-rwx \
    "${PROJECT_DIR}/calibration"


ok "Runtime directory permissions พร้อม"


# ============================================================
# Model permissions
# ============================================================
#
# Model ไม่จำเป็นต้อง writable โดย Runtime
# แต่ service user ต้องอ่านได้
#
# ============================================================

if [[ -f "${MODEL_PT}" ]]; then

    chmod \
        0644 \
        "${MODEL_PT}"

fi


if [[ -d "${MODEL_OV}" ]]; then

    find \
        "${MODEL_OV}" \
        -type d \
        -exec chmod 0755 {} \;

    find \
        "${MODEL_OV}" \
        -type f \
        -exec chmod 0644 {} \;

fi


ok "Model permissions พร้อม"


# ============================================================
# 20. Service configuration summary
# ============================================================

info "20. Production configuration summary"


echo "Project:"
echo "  ${PROJECT_DIR}"
echo

echo "Python:"
echo "  ${VENV_PYTHON}"
echo

echo "Environment:"
echo "  ${ENV_FILE}"
echo

echo "Detection service:"
echo "  ${SERVICE_FILE}"
echo

echo "Dashboard service:"
echo "  ${DASHBOARD_SERVICE_FILE}"
echo

echo "Detection runtime:"
echo "  ${PROJECT_DIR}/main.py"
echo

echo "Dashboard runtime:"
echo "  ${PROJECT_DIR}/app.py"
echo


# ============================================================
# IMPORTANT
# ============================================================
#
# เราจะยังไม่ Start หรือ Enable Services
#
# เพราะก่อน Production ต้อง:
#
# - ตั้ง production.env
# - Offline Preflight
# - Production Benchmark
# - Camera Test
# - PTZ Test
# - PTZ / Frame Sync
# - Camera Intrinsics validation
# - Bearing Calibration
# - Distance Calibration
# - Bearing Verification
# - Distance Verification
# - Full Preflight
# - Full Sweep
# - Telegram Test
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
echo "Services:"
echo "${SERVICE_FILE}"
echo "${DASHBOARD_SERVICE_FILE}"

echo
echo "------------------------------------------------------------"

echo
echo "Detection Service ยังไม่ได้ Start"
echo "Dashboard Service ยังไม่ได้ Start"
echo
echo "และทั้งสอง Service"
echo "ยังไม่ได้ Enable ตอน Boot"

echo
echo "นี่เป็นพฤติกรรมที่ตั้งใจไว้"

echo
echo "------------------------------------------------------------"

echo
echo "ขั้นต่อไป:"
echo
echo " 1. แก้ Production environment"
echo " 2. รัน Offline Preflight"
echo " 3. ตรวจ Unit Tests"
echo " 4. Benchmark PyTorch"
echo " 5. Benchmark OpenVINO"
echo " 6. เลือก Production Backend"
echo " 7. ทดสอบ RTSP Camera"
echo " 8. ทดสอบ PTZ Presets"
echo " 9. ทดสอบ PTZ / Fresh / Stable Frame"
echo "10. ตรวจ Intrinsics / HFOV"
echo "11. ทำ Bearing Calibration"
echo "12. ทำ Distance Calibration"
echo "13. Verify Bearing"
echo "14. Verify Distance"
echo "15. รัน Full Preflight"
echo "16. รัน Full Sweep Test"
echo "17. ทดสอบ Telegram"
echo "18. Enable Detection Service"
echo "19. Enable Dashboard Service"
echo "20. Reboot Test"

echo
echo "------------------------------------------------------------"

echo
echo "ห้ามรัน main.py เป็นขั้นทดสอบแรก"

echo
echo "หลังทุก Validation ผ่านแล้วจึงใช้:"
echo
echo "sudo systemctl enable smart-fire-detection.service"
echo "sudo systemctl start smart-fire-detection.service"
echo
echo "sudo systemctl enable smart-fire-dashboard.service"
echo "sudo systemctl start smart-fire-dashboard.service"

echo
echo "ตรวจสถานะ:"
echo
echo "systemctl status smart-fire-detection.service"
echo "systemctl status smart-fire-dashboard.service"

echo
echo "ดู Log:"
echo
echo "journalctl -u smart-fire-detection.service -f"
echo "journalctl -u smart-fire-dashboard.service -f"

echo
echo "============================================================"
echo "Smart Fire Detection v2 Production Installer completed"
echo "============================================================"
echo


exit 0
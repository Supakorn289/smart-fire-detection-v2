import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Camera / RTSP
CAMERA_IP = os.getenv('CAMERA_IP', '192.168.0.100')
CAMERA_PORT = int(os.getenv('CAMERA_PORT', '81'))
CAMERA_USER = os.getenv('CAMERA_USER', 'admin')
CAMERA_PWD = os.getenv('CAMERA_PWD', '888888')
RTSP_PORT = int(os.getenv('RTSP_PORT', '10554'))
RTSP_PATH = os.getenv('RTSP_PATH', '/tcp/av0_0')
CAMERA_ID = os.getenv('CAMERA_ID', f'rtsp://{CAMERA_USER}:{CAMERA_PWD}@{CAMERA_IP}:{RTSP_PORT}{RTSP_PATH}')
FRAME_WIDTH = int(os.getenv('FRAME_WIDTH', '1280'))
FRAME_HEIGHT = int(os.getenv('FRAME_HEIGHT', '720'))
HFOV_DEG = float(os.getenv('HFOV_DEG', '56.14'))

# PTZ physical pan coordinate: -177.5 .. +177.5
PRESET_PAN_DEG = {
    1: 0.0, 2: 45.0, 3: 90.0, 4: 135.0, 5: 177.5,
    6: -45.0, 7: -90.0, 8: -135.0, 9: -177.5,
}
# Compass azimuth: 0=N, 90=E, 180=S, 270=W
PRESET_BEARING_DEG = {
    1: 0.0, 2: 45.0, 3: 90.0, 4: 135.0, 5: 177.5,
    6: 315.0, 7: 270.0, 8: 225.0, 9: 182.5,
}
SWEEP_SEQUENCE = [1, 2, 3, 4, 5, 4, 3, 2, 1, 6, 7, 8, 9, 8, 7, 6, 1]
DEG_PER_SEC = float(os.getenv('DEG_PER_SEC', '15.0'))
PTZ_BUFFER_SEC = float(os.getenv('PTZ_BUFFER_SEC', '1.5'))
INITIAL_PRESET_WAIT_SEC = float(os.getenv('INITIAL_PRESET_WAIT_SEC', '5.0'))
STABLE_DIFF_THRESHOLD = float(os.getenv('STABLE_DIFF_THRESHOLD', '3.0'))
STABLE_REQUIRED_PAIRS = int(os.getenv('STABLE_REQUIRED_PAIRS', '3'))
STABLE_TIMEOUT_SEC = float(os.getenv('STABLE_TIMEOUT_SEC', '5.0'))
POST_MOVE_FRESH_FRAMES = int(os.getenv('POST_MOVE_FRESH_FRAMES', '3'))

# AI
MODEL_BACKEND = os.getenv('MODEL_BACKEND', 'pt').strip().lower()
MODEL_PATH_PT = os.getenv('MODEL_PATH_PT', str(BASE_DIR / 'models' / 'fire.pt'))
MODEL_PATH_OPENVINO = os.getenv('MODEL_PATH_OPENVINO', str(BASE_DIR / 'models' / 'fire_openvino_model'))
INFERENCE_DEVICE = os.getenv('INFERENCE_DEVICE', 'cpu')
IMGSZ = int(os.getenv('IMGSZ', '640'))
FRAMES_PER_SCAN = int(os.getenv('FRAMES_PER_SCAN', '3'))
MIN_CONFIRM_FRAMES = int(os.getenv('MIN_CONFIRM_FRAMES', '2'))
FRAME_SAMPLE_GAP_SEC = float(os.getenv('FRAME_SAMPLE_GAP_SEC', '0.15'))
CLASS_THRESHOLDS = {
    'fire': float(os.getenv('FIRE_THRESHOLD', '0.50')),
    'smoke': float(os.getenv('SMOKE_THRESHOLD', '0.60')),
}
CLASS_ALIASES = {
    'fire': {'fire', 'flame', 'flames'},
    'smoke': {'smoke', 'smokes', 'fire-smoke', 'firesmoke'},
}

# Calibration / GPS
CALIBRATION_DIR = Path(os.getenv('CALIBRATION_DIR', str(BASE_DIR / 'calibration')))
GLOBAL_DISTANCE_CALIBRATION = CALIBRATION_DIR / 'distance_global.json'
SITE_CALIBRATION_FILE = CALIBRATION_DIR / 'site.json'
MIN_VALID_DISTANCE_M = float(os.getenv('MIN_VALID_DISTANCE_M', '1.0'))
MAX_VALID_DISTANCE_M = float(os.getenv('MAX_VALID_DISTANCE_M', '200.0'))
CAMERA_LAT = float(os.getenv('CAMERA_LAT', '18.79273619036605'))
CAMERA_LON = float(os.getenv('CAMERA_LON', '98.98380734578086'))

# Alert / output
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
ALERT_COOLDOWN_SEC = float(os.getenv('ALERT_COOLDOWN_SEC', '30'))
STATIC_DIR = Path(os.getenv('STATIC_DIR', str(BASE_DIR / 'static')))
DASHBOARD_WRITE_INTERVAL_SEC = float(os.getenv('DASHBOARD_WRITE_INTERVAL_SEC', '1.0'))
HEADLESS_MODE = os.getenv('HEADLESS_MODE', '1') != '0'

for p in (CALIBRATION_DIR, STATIC_DIR, BASE_DIR / 'models'):
    p.mkdir(parents=True, exist_ok=True)

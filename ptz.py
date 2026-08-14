import requests
from config import CAMERA_IP, CAMERA_PORT, CAMERA_USER, CAMERA_PWD, PRESET_PAN_DEG, PRESET_BEARING_DEG, DEG_PER_SEC, PTZ_BUFFER_SEC

class PTZController:
    def __init__(self):
        self.current_preset = None
        self.current_pan_deg = None

    @staticmethod
    def _call_command(command: int) -> bool:
        url = (f'http://{CAMERA_IP}:{CAMERA_PORT}/decoder_control.cgi?command={command}'
               f'&onestep=&loginuse={CAMERA_USER}&loginpas={CAMERA_PWD}')
        try:
            r = requests.get(url, timeout=3.0)
            return r.status_code == 200
        except requests.RequestException as e:
            print(f'⚠️ PTZ request failed: {e}')
            return False

    def goto_preset(self, preset: int):
        if preset not in PRESET_PAN_DEG:
            raise ValueError(f'Unknown preset {preset}')
        target_pan = PRESET_PAN_DEG[preset]
        previous_pan = self.current_pan_deg
        travel = 0.0 if previous_pan is None else abs(target_pan - previous_pan) / max(DEG_PER_SEC, 1e-6)
        wait_sec = travel + PTZ_BUFFER_SEC
        cmd = 31 + ((preset - 1) * 2)
        ok = self._call_command(cmd)
        if ok:
            self.current_preset = preset
            self.current_pan_deg = target_pan
        return ok, wait_sec

    def save_preset(self, preset: int) -> bool:
        if not (1 <= preset <= 16):
            raise ValueError('preset must be 1..16')
        return self._call_command(30 + ((preset - 1) * 2))

    @staticmethod
    def bearing_for_preset(preset: int) -> float:
        return PRESET_BEARING_DEG[preset]

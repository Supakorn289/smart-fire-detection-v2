import json
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from config import (
    CALIBRATION_DIR,
    GLOBAL_DISTANCE_CALIBRATION,
    SITE_CALIBRATION_FILE,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    HFOV_DEG,
)


@dataclass
class DistanceModel:
    H: float
    K: float
    pixel_rmse: float
    frame_width: int
    frame_height: int
    points: int
    preset: int | None = None

    # v3: ช่วงระยะจริงที่ใช้สร้าง calibration
    min_distance_m: float | None = None
    max_distance_m: float | None = None

    def estimate(self, y_px: float) -> float | None:
        denom = y_px - self.H
        if abs(denom) < 1e-9:
            return None

        z = self.K / denom
        if not np.isfinite(z) or z <= 0:
            return None

        return float(z)

    def has_calibrated_range(self) -> bool:
        return (
            self.min_distance_m is not None
            and self.max_distance_m is not None
            and self.min_distance_m > 0
            and self.max_distance_m >= self.min_distance_m
        )

    def is_within_calibrated_range(self, distance_m: float) -> bool:
        if not self.has_calibrated_range():
            return False

        return self.min_distance_m <= distance_m <= self.max_distance_m


def fit_distance_model(
    samples: list[tuple[float, float]],
    preset: int | None = None,
) -> DistanceModel:
    """Fit y = H + K*(1/z) by least squares. Need >= 3 reference points."""
    if len(samples) < 3:
        raise ValueError("ต้องมีจุด calibration อย่างน้อย 3 จุด")

    z = np.asarray([s[0] for s in samples], dtype=float)
    y = np.asarray([s[1] for s in samples], dtype=float)

    if np.any(z <= 0):
        raise ValueError("ระยะจริงต้องมากกว่า 0 เมตร")

    x = 1.0 / z
    A = np.column_stack([np.ones_like(x), x])

    coeff, *_ = np.linalg.lstsq(A, y, rcond=None)
    H, K = float(coeff[0]), float(coeff[1])

    pred = H + K * x
    rmse = float(np.sqrt(np.mean((pred - y) ** 2)))

    if abs(K) < 1e-9:
        raise ValueError("Calibration ผิดปกติ: K ใกล้ศูนย์")

    return DistanceModel(
        H=H,
        K=K,
        pixel_rmse=rmse,
        frame_width=FRAME_WIDTH,
        frame_height=FRAME_HEIGHT,
        points=len(samples),
        preset=preset,
        min_distance_m=float(np.min(z)),
        max_distance_m=float(np.max(z)),
    )


def _path_for_preset(preset: int | None) -> Path:
    return (
        GLOBAL_DISTANCE_CALIBRATION
        if preset is None
        else CALIBRATION_DIR / f"distance_preset_{preset:02d}.json"
    )


def save_distance_model(model: DistanceModel) -> Path:
    path = _path_for_preset(model.preset)

    data = {
        "version": 3,
        "H": model.H,
        "K": model.K,
        "pixel_rmse": model.pixel_rmse,
        "frame_width": model.frame_width,
        "frame_height": model.frame_height,
        "hfov_deg": HFOV_DEG,
        "points": model.points,
        "preset": model.preset,
        "min_distance_m": model.min_distance_m,
        "max_distance_m": model.max_distance_m,
    }

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_distance_model(preset: int | None = None) -> DistanceModel | None:
    specific = _path_for_preset(preset)

    path = (
        specific
        if preset is not None and specific.exists()
        else GLOBAL_DISTANCE_CALIBRATION
    )

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if (
            int(data["frame_width"]) != FRAME_WIDTH
            or int(data["frame_height"]) != FRAME_HEIGHT
        ):
            print(f"⚠️ Calibration resolution mismatch: {path}")
            return None

        min_distance = data.get("min_distance_m")
        max_distance = data.get("max_distance_m")

        model = DistanceModel(
            H=float(data["H"]),
            K=float(data["K"]),
            pixel_rmse=float(data.get("pixel_rmse", 0.0)),
            frame_width=int(data["frame_width"]),
            frame_height=int(data["frame_height"]),
            points=int(data.get("points", 0)),
            preset=data.get("preset"),
            min_distance_m=(
                None if min_distance is None else float(min_distance)
            ),
            max_distance_m=(
                None if max_distance is None else float(max_distance)
            ),
        )

        if not model.has_calibrated_range():
            print(
                f"⚠️ Calibration file ไม่มี range metadata: {path}\n"
                "   ระบบจะไม่สร้าง GPS จากระยะจนกว่าจะกำหนดช่วง calibration"
            )

        return model

    except Exception as e:
        print(f"⚠️ โหลด calibration ไม่สำเร็จ {path}: {e}")
        return None


def save_site_calibration(
    north_offset_deg: float,
    measured_preset1_bearing_deg: float,
) -> Path:
    data = {
        "version": 1,
        "north_offset_deg": float(north_offset_deg),
        "measured_preset1_bearing_deg": float(
            measured_preset1_bearing_deg
        ),
        "frame_width": FRAME_WIDTH,
        "frame_height": FRAME_HEIGHT,
        "hfov_deg": HFOV_DEG,
    }

    SITE_CALIBRATION_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    return SITE_CALIBRATION_FILE


def load_north_offset_deg() -> float:
    if not SITE_CALIBRATION_FILE.exists():
        return 0.0

    try:
        data = json.loads(
            SITE_CALIBRATION_FILE.read_text(encoding="utf-8")
        )
        return float(data.get("north_offset_deg", 0.0))
    except Exception:
        return 0.0

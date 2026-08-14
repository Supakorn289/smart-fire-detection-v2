#!/usr/bin/env python3
import argparse
import json

from config import CALIBRATION_DIR, GLOBAL_DISTANCE_CALIBRATION


def main():
    ap = argparse.ArgumentParser(
        description="Add/Update min/max distance metadata in an existing calibration JSON"
    )
    ap.add_argument(
        "--min",
        dest="min_distance",
        type=float,
        required=True,
        help="ระยะ calibration ต่ำสุด (m)",
    )
    ap.add_argument(
        "--max",
        dest="max_distance",
        type=float,
        required=True,
        help="ระยะ calibration สูงสุด (m)",
    )
    ap.add_argument(
        "--preset",
        type=int,
        choices=range(1, 10),
        default=None,
        help="ถ้าไม่ระบุจะใช้ global calibration",
    )
    args = ap.parse_args()

    if args.min_distance <= 0:
        raise SystemExit("❌ --min ต้องมากกว่า 0")

    if args.max_distance <= args.min_distance:
        raise SystemExit("❌ --max ต้องมากกว่า --min")

    path = (
        GLOBAL_DISTANCE_CALIBRATION
        if args.preset is None
        else CALIBRATION_DIR / f"distance_preset_{args.preset:02d}.json"
    )

    if not path.exists():
        raise SystemExit(f"❌ ไม่พบ calibration file: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    print("=" * 72)
    print("Distance Calibration Range Migration")
    print(f"File : {path}")
    print(f"H    : {data.get('H')}")
    print(f"K    : {data.get('K')}")
    print(f"RMSE : {data.get('pixel_rmse')}")
    print("=" * 72)

    data["version"] = max(int(data.get("version", 1)), 3)
    data["min_distance_m"] = float(args.min_distance)
    data["max_distance_m"] = float(args.max_distance)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"✅ Saved calibrated range: "
        f"{args.min_distance:.3f} - {args.max_distance:.3f} m"
    )
    print(f"✅ Updated: {path}")


if __name__ == "__main__":
    main()

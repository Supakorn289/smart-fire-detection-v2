#!/usr/bin/env python3
from calibration import save_site_calibration
from geometry import normalize_bearing
print('หันกล้องไป Preset 1 แล้ววัด bearing จริงของจุดกลางภาพ')
measured = float(input('Bearing จริง (0-360°): '))
offset = normalize_bearing(measured)
if offset > 180:
    offset -= 360
path = save_site_calibration(offset, measured)
print(f'✅ Saved {path} | north_offset_deg={offset:+.3f}°')

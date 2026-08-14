import math

EARTH_RADIUS_M = 6378137.0

def normalize_bearing(angle_deg: float) -> float:
    return angle_deg % 360.0

def focal_length_px(frame_width: int, hfov_deg: float) -> float:
    if frame_width <= 0:
        raise ValueError('frame_width must be > 0')
    if not (0.0 < hfov_deg < 180.0):
        raise ValueError('hfov_deg must be between 0 and 180')
    return frame_width / (2.0 * math.tan(math.radians(hfov_deg) / 2.0))

def pixel_to_bearing(preset_bearing_deg: float, x_px: float, frame_width: int,
                     hfov_deg: float, north_offset_deg: float = 0.0,
                     principal_x_px: float | None = None) -> float:
    '''Pinhole horizontal projection: pixel x -> angular offset -> bearing.'''
    cx = frame_width / 2.0 if principal_x_px is None else principal_x_px
    fx = focal_length_px(frame_width, hfov_deg)
    offset_deg = math.degrees(math.atan2(x_px - cx, fx))
    return normalize_bearing(preset_bearing_deg + north_offset_deg + offset_deg)

def gps_from_bearing_distance(camera_lat: float, camera_lon: float,
                              distance_m: float, bearing_deg: float) -> tuple[float, float]:
    if distance_m < 0:
        raise ValueError('distance_m must be >= 0')
    lat1 = math.radians(camera_lat)
    lon1 = math.radians(camera_lon)
    bearing = math.radians(bearing_deg)
    ad = distance_m / EARTH_RADIUS_M
    s = (math.sin(lat1) * math.cos(ad) + math.cos(lat1) * math.sin(ad) * math.cos(bearing))
    lat2 = math.asin(max(-1.0, min(1.0, s)))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(ad) * math.cos(lat1),
        math.cos(ad) - math.sin(lat1) * math.sin(lat2),
    )
    lon2 = (lon2 + 3.0 * math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(lat2), math.degrees(lon2)

def bearing_to_compass(bearing_deg: float) -> str:
    labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    return labels[int((normalize_bearing(bearing_deg) + 22.5) // 45.0) % 8]

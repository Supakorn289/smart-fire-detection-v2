import cv2
from geometry import bearing_to_compass

def draw_detection(frame, d):
    x1, y1, x2, y2 = d.bbox
    cv2.rectangle(frame, (x1,y1), (x2,y2), (0,0,255), 2)
    dist = '?' if d.distance_m is None else f'{d.distance_m:.1f}m'
    text = f'{d.canonical_class} {d.confidence:.2f} | {dist} | {d.bearing_deg:.1f}deg {bearing_to_compass(d.bearing_deg)}'
    cv2.putText(frame, text, (x1, max(25,y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,255), 2)

def draw_status(frame, preset, bearing, status):
    cv2.putText(frame, f'Preset {preset} | center {bearing:.1f} deg | {status}',
                (10, frame.shape[0]-20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)

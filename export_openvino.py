#!/usr/bin/env python3
import argparse
from ultralytics import YOLO
from config import MODEL_PATH_PT
ap = argparse.ArgumentParser()
ap.add_argument('--int8', action='store_true')
ap.add_argument('--data', default=None, help='dataset yaml for INT8 calibration when required')
args = ap.parse_args()
model = YOLO(MODEL_PATH_PT)
kwargs = {'format': 'openvino', 'dynamic': False}
if args.int8:
    kwargs['int8'] = True
    if args.data:
        kwargs['data'] = args.data
else:
    kwargs['half'] = False
print('Export args:', kwargs)
print('Exported:', model.export(**kwargs))

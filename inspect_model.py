#!/usr/bin/env python3
from config import MODEL_BACKEND, MODEL_PATH_PT, MODEL_PATH_OPENVINO
from ultralytics import YOLO
path = MODEL_PATH_OPENVINO if MODEL_BACKEND == 'openvino' else MODEL_PATH_PT
model = YOLO(path)
print(f'Model: {path}')
print(f'Classes ({len(model.names)}):')
for i, name in model.names.items():
    print(f'  [{i}] {name}')

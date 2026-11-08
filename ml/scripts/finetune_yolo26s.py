import sys
from ultralytics import YOLO

base_model, data_yaml, project = sys.argv[1], sys.argv[2], sys.argv[3]

model = YOLO(base_model)
model.train(
    data=data_yaml,
    project=project,
    name="finetune",
    epochs=40,
    patience=12,
    imgsz=640,
    batch=0.7,
    optimizer="SGD",
    lr0=0.001,
    lrf=0.01,
    cos_lr=True,
    warmup_epochs=3.0,
    mosaic=0.0,
    close_mosaic=0,
    scale=0.3,
    degrees=2.0,
    translate=0.1,
    fliplr=0.5,
    seed=42,
    deterministic=True,
    save_period=5,
    device=0,
)
model = YOLO(f"{project}/finetune/weights/best.pt")
model.export(format="onnx", imgsz=640, simplify=True)

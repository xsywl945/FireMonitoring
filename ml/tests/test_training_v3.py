import csv
import functools
import http.server
import json
import os
import hashlib
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from validate_model import operating_metrics  # noqa: E402


class TrainingV3Test(unittest.TestCase):
    def run_script(self, script, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_prepare_split_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = []
            rng = np.random.default_rng(42)
            for source, names in [
                ("dfire", ["smoke", "fire"]),
                ("ifiresmoke", ["fire", "smoke"]),
            ]:
                raw = root / source
                raw.mkdir()
                (raw / "data.yaml").write_text(yaml.safe_dump(dict(names=names)))
                for split in ("train", "val", "test"):
                    (raw / split / "images").mkdir(parents=True)
                    (raw / split / "labels").mkdir()
                    for index in range(16):
                        stem = f"image_{split}_{index}.rf.abc123"
                        Image.fromarray(
                            rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
                        ).save(raw / split / "images" / f"{stem}.png")
                        (raw / split / "labels" / f"{stem}.txt").write_text(
                            "0 0.5 0.5 0.2 0.2\n1 0.99 0.5 0.04 0.2\n"
                        )
                specs.append(
                    dict(
                        name=source,
                        root=str(raw),
                        names=names,
                        yaml="data.yaml",
                        splits={s: s for s in ("train", "val", "test")},
                        background=False,
                        url="https://example.org",
                        license="test",
                    )
                )
            config = root / "sources.json"
            config.write_text(json.dumps(specs))
            merged = root / "merged"
            self.run_script(
                "prepare_fire_smoke_v1.py",
                "--sources",
                config,
                "--output",
                merged,
                "--link",
            )
            with (merged / "manifest.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            dfire = next(r for r in rows if r["source"] == "dfire")
            self.assertTrue(Path(dfire["target_label"]).read_text().startswith("1 "))
            self.assertEqual(
                len(json.loads((merged / "source_label_repairs.json").read_text())), 96
            )
            baseline = root / "baseline.csv"
            with baseline.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["target_image", "target_split"]
                )
                writer.writeheader()
                for row in (
                    rows[0],
                    next(r for r in rows if r["source"] == "ifiresmoke"),
                ):
                    name = (
                        Path(row["target_image"])
                        .stem.rsplit("__", 1)[0]
                        .replace(".", "_")
                        + "__"
                        + row["sha256"][:10]
                        + ".png"
                    )
                    writer.writerow(dict(target_image=name, target_split="train"))
            output = root / "split"
            self.run_script(
                "build_leakage_safe_primary_split.py",
                "--manifest",
                merged / "manifest.csv",
                "--baseline-manifest",
                baseline,
                "--output",
                output,
                "--link",
            )
            self.run_script(
                "audit_yolo_dataset.py",
                "--data",
                output / "data.yaml",
                "--output",
                root / "audit.json",
                "--phash-threshold",
                4,
            )
            audit = json.loads((root / "audit.json").read_text())
            self.assertEqual(audit["near_cross_split_duplicate_pair_count"], 0)
            with (output / "manifest.csv").open() as handle:
                result = list(csv.DictReader(handle))
            self.assertEqual({r["split"] for r in result}, {"train", "val", "test"})
            self.assertEqual(sum(r["baseline_exposed"] == "true" for r in result), 2)
            self.assertTrue(
                all(
                    r["baseline_exposed"] == "false"
                    for r in result
                    if r["split"] == "test"
                )
            )

    @unittest.skipUnless(
        os.environ.get("YOLO26S_WEIGHTS"),
        "set YOLO26S_WEIGHTS for the CPU training self-test",
    )
    def test_train_resume_validate_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            rng = np.random.default_rng(42)
            for split, count in (("train", 4), ("val", 2), ("test", 2)):
                for index in range(count):
                    image = root / "images" / split / f"{index}.png"
                    label = root / "labels" / split / f"{index}.txt"
                    image.parent.mkdir(parents=True, exist_ok=True)
                    label.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(
                        rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)
                    ).save(image)
                    label.write_text(
                        "0 0.3 0.3 0.2 0.2\n1 0.7 0.7 0.3 0.3\n"
                        if index % 2 == 0
                        else ""
                    )
                    rows.append(
                        dict(
                            split=split,
                            source="ifiresmoke",
                            target_image=image.relative_to(root).as_posix(),
                        )
                    )
            with (root / "manifest.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            config = dict(
                path=root.as_posix(),
                train="images/train",
                val="images/val",
                test="images/test",
                names={0: "fire", 1: "smoke"},
            )
            (root / "data.yaml").write_text(yaml.safe_dump(config))
            common = [
                "--data",
                root / "data.yaml",
                "--model",
                os.environ["YOLO26S_WEIGHTS"],
                "--project",
                root / "runs",
                "--name",
                "cli",
                "--epochs",
                2,
                "--imgsz",
                64,
                "--batch",
                2,
                "--workers",
                0,
                "--device",
                "cpu",
                "--time",
                1,
            ]
            self.run_script("train_baseline.py", *common)
            run = root / "runs/cli"
            self.assertTrue((run / "weights/epoch0.pt").is_file())
            self.run_script(
                "train_baseline.py", *common, "--resume", run / "weights/epoch0.pt"
            )
            with (run / "results.csv").open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 2)
            experiment = json.loads((run / "experiment.json").read_text())
            with Path(os.environ["YOLO26S_WEIGHTS"]).open("rb") as handle:
                expected = hashlib.file_digest(handle, "sha256").hexdigest()
            self.assertEqual(experiment["pretrained_model_sha256"], expected)
            self.assertIn("resume_checkpoint_sha256", experiment)
            import torch
            from datetime import datetime, timezone
            from ultralytics import YOLO

            checkpoint = YOLO(str(run / "weights/epoch0.pt")).ckpt
            checkpoint["epoch"] = 80
            checkpoint["train_args"]["epochs"] = 83
            checkpoint["train_results"]["epoch"] = [81]
            late = run / "weights/late.pt"
            torch.save(checkpoint, late)
            request = root / "runs/cli.request.json"
            initial = json.loads(request.read_text())
            initial["started_at_utc"] = datetime.now(timezone.utc).isoformat()
            request.write_text(json.dumps(initial))
            self.run_script(
                "train_baseline.py",
                *common,
                "--resume",
                late,
                "--epochs",
                83,
                "--time",
                0.01,
            )
            with (run / "results.csv").open() as handle:
                epochs = [int(r["epoch"]) for r in csv.DictReader(handle)]
            self.assertEqual(epochs, [81, 82, 83])
            duplicate = root / "another/data.yaml"
            duplicate.parent.mkdir()
            duplicate.write_text(yaml.safe_dump(config))
            self.run_script(
                "validate_model.py",
                "--model",
                run / "weights/best.pt",
                "--data",
                root / "data.yaml",
                "--data",
                duplicate,
                "--project",
                root / "evaluation",
                "--imgsz",
                64,
                "--batch",
                2,
                "--device",
                "cpu",
            )
            result = json.loads(
                (root / "evaluation/validation_summary.json").read_text()
            )
            self.assertEqual(len(result["datasets"]), 2)
            self.assertTrue((root / "evaluation/validation_report.md").is_file())
            command = "import sys,onnx; from ultralytics import YOLO; p=YOLO(sys.argv[1]).export(format='onnx',imgsz=64,opset=17,simplify=False,device='cpu');onnx.checker.check_model(onnx.load(p))"
            exported = subprocess.run(
                [sys.executable, "-c", command, str(run / "weights/best.pt")],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
            self.assertTrue((run / "weights/best.onnx").is_file())

    def test_metrics_match_classes_small_boxes_and_negatives(self):
        records = [
            dict(
                image="positive",
                width=640,
                height=640,
                gt=[[0, 0, 0, 20, 20], [1, 100, 100, 200, 200]],
                pred=[[0, 0.8, 0, 0, 20, 20], [0, 0.7, 100, 100, 200, 200]],
            ),
            dict(
                image="background",
                width=640,
                height=640,
                gt=[],
                pred=[[1, 0.9, 0, 0, 20, 20]],
            ),
        ]
        metric = operating_metrics(records, [0.25, 0.25], 640)
        self.assertEqual(metric["per_class"]["fire"]["small_recall_iou50"], 1)
        self.assertEqual(metric["per_class"]["smoke"]["recall"], 0)
        self.assertEqual(metric["negative_image_fpr"], 1)
        self.assertEqual(metric["negative_fp_detections"], 1)

    def test_coco_filter_download_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (20, 20), "red").save(root / "one.jpg")
            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0),
                functools.partial(http.server.SimpleHTTPRequestHandler, directory=root),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/one.jpg"
            data = dict(
                images=[
                    dict(
                        id=i,
                        file_name=f"{i}.jpg",
                        license=1,
                        coco_url=url,
                        flickr_url="https://example.org",
                    )
                    for i in [4, 2, 1, 3]
                ],
                licenses=[
                    dict(id=1, url="https://creativecommons.org/licenses/by/4.0/")
                ],
                annotations=[
                    dict(image_id=1, caption="a red screen"),
                    dict(image_id=2, caption="a red screen with fire"),
                    dict(image_id=3, caption="a red screen"),
                    dict(image_id=4, caption="a red screen"),
                ],
            )
            exclusions = root / "exclusions.csv"
            exclusions.write_text("filename,reason\n3.jpg,manual visual exclusion\n")
            path = root / "captions.json"
            path.write_text(json.dumps(data))
            try:
                self.run_script(
                    "prepare_coco_negatives.py",
                    "--annotations",
                    path,
                    "--output",
                    root / "out",
                    "--per-category",
                    1,
                    "--exclusions",
                    exclusions,
                )
            finally:
                server.shutdown()
                server.server_close()
            self.assertTrue((root / "out/train/images/1.jpg").is_file())
            for index in (2, 3, 4):
                self.assertFalse((root / f"out/train/images/{index}.jpg").exists())
            archive = root / "images.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.write(root / "one.jpg", "train2017/1.jpg")
            next(item for item in data["images"] if item["id"] == 1)["coco_url"] = (
                "http://images.cocodataset.org/train2017/1.jpg"
            )
            path.write_text(json.dumps(data))
            self.run_script(
                "prepare_coco_negatives.py",
                "--annotations",
                path,
                "--images-zip",
                archive,
                "--output",
                root / "zip-out",
                "--per-category",
                1,
                "--exclusions",
                exclusions,
            )
            self.assertTrue((root / "zip-out/train/images/1.jpg").is_file())
            with (root / "out/metadata.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertIn("creativecommons.org", rows[0]["license"])


if __name__ == "__main__":
    unittest.main()

import csv
import functools
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
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
                        stem = f"image_{split}_{index}"
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
                writer.writerow(
                    dict(target_image=rows[0]["target_image"], target_split="train")
                )
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
            self.assertTrue(
                all(
                    r["baseline_exposed"] == "false"
                    for r in result
                    if r["split"] == "test"
                )
            )

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
                    for i in [1, 2]
                ],
                licenses=[
                    dict(id=1, url="https://creativecommons.org/licenses/by/4.0/")
                ],
                annotations=[
                    dict(image_id=1, caption="a red screen"),
                    dict(image_id=2, caption="a red screen with fire"),
                ],
            )
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
                )
            finally:
                server.shutdown()
                server.server_close()
            self.assertTrue((root / "out/train/images/1.jpg").is_file())
            self.assertFalse((root / "out/train/images/2.jpg").exists())
            with (root / "out/metadata.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertIn("creativecommons.org", rows[0]["license"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env bash
set -Eeuo pipefail
export PATH="/root/miniconda3/bin:${PATH}"
trap 'echo "失败: line ${LINENO}: ${BASH_COMMAND}" >&2' ERR

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${DATA_ZIP:?设置本地已校验数据 ZIP 路径}"
: "${PRETRAINED:?设置 yolo26s.pt 路径}"
: "${BASELINE:?设置旧 YOLO11s best.pt 路径}"
AMP_CHECKPOINT="$(dirname -- "$PRETRAINED")/yolo26n.pt"
[[ -f "$AMP_CHECKPOINT" ]]
: "${TMUX:?请从 tmux 会话执行}"
WORK_ROOT="${FIRE_WORK_ROOT:-/root/autodl-tmp/yolo26s-v3}"
ARCHIVE_ROOT="${FIRE_ARCHIVE_ROOT:-/root/autodl-fs/fire-monitoring/2026-11-03-yolo26s-v3}"
[[ ! -e "$WORK_ROOT" ]]
[[ -d /root/autodl-fs ]]
mkdir -p "$WORK_ROOT" "$ARCHIVE_ROOT"
exec > >(tee "$WORK_ROOT/run_all.log") 2>&1
cd "$REPO_ROOT"
export YOLO_AUTOINSTALL=false
export MPLBACKEND=Agg
cp "$AMP_CHECKPOINT" "$REPO_ROOT/yolo26n.pt"
step() {
  local label="$1" seconds="$2"
  shift 2
  echo "开始: $label $(date --iso-8601=seconds)"
  timeout --foreground --signal=TERM --kill-after=60 "$seconds" "$@"
  echo "完成: $label $(date --iso-8601=seconds)"
}
step 安装依赖 3600 python -m pip install -r ml/requirements-autodl.txt
step 环境检查 300 python ml/scripts/check_environment.py --require-cuda --workdir /root/autodl-tmp
python -m pip freeze > "$WORK_ROOT/environment-freeze.txt"
nvidia-smi > "$WORK_ROOT/nvidia-smi.txt"
python - "$PRETRAINED" "$BASELINE" <<'PY'
import sys,torch,ultralytics
from ultralytics import YOLO
assert sys.version_info[:2] == (3,12), sys.version
assert torch.__version__.split('+')[0] == '2.8.0', torch.__version__
assert torch.version.cuda == '12.8', torch.version.cuda
assert ultralytics.__version__ == '8.4.100'
assert '4090' in torch.cuda.get_device_name(0)
assert YOLO(sys.argv[1]).model.yaml['scale'] == 's'
assert YOLO(sys.argv[2]).names == {0:'fire',1:'smoke'}
PY
sha256sum "$PRETRAINED" "$BASELINE" "$AMP_CHECKPOINT" > "$WORK_ROOT/input-weights.sha256"
step 解压与校验 3600 python - "$DATA_ZIP" "$WORK_ROOT/dataset" <<'PY'
import hashlib,pathlib,sys,zipfile,yaml
archive=pathlib.Path(sys.argv[1]).resolve(); target=pathlib.Path(sys.argv[2]).resolve()
expected=pathlib.Path(str(archive)+'.sha256').read_text().split()[0]
with archive.open('rb') as handle: assert hashlib.file_digest(handle,'sha256').hexdigest()==expected
with zipfile.ZipFile(archive) as z:
    assert all(not pathlib.PurePosixPath(n).is_absolute() and '..' not in pathlib.PurePosixPath(n).parts for n in z.namelist())
    z.extractall(target)
for line in (target/'CHECKSUMS.sha256').read_text().splitlines():
    digest,name=line.split('  ',1)
    with (target/name).open('rb') as handle: assert hashlib.file_digest(handle,'sha256').hexdigest()==digest, name
for path in target.glob('*.yaml'):
    config=yaml.safe_load(path.read_text());config['path']=str(target)
    path.write_text(yaml.safe_dump(config,sort_keys=False))
PY
DATA="$WORK_ROOT/dataset/data.yaml"
step 数据审计 1800 python ml/scripts/audit_yolo_dataset.py --data "$DATA" --output "$WORK_ROOT/audit.json" --phash-threshold 4
python - "$WORK_ROOT/audit.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert not r['errors'] and r['near_cross_split_duplicate_pair_count']==0,r
PY
TRAIN=(python ml/scripts/train_baseline.py --data "$DATA" --model "$PRETRAINED" --project "$WORK_ROOT/runs" --imgsz 640 --device 0 --batch 0.7 --workers 8 --cache none --seed 42)
step 两轮冒烟 1800 "${TRAIN[@]}" --name smoke --epochs 2 --patience 25 --time 0.4 --fraction 0.01
step 正式训练 52200 "${TRAIN[@]}" --name formal --epochs 120 --patience 25 --time 14
EVAL_DATA=(--data "$DATA")
for path in "$WORK_ROOT"/dataset/*_test.yaml; do EVAL_DATA+=(--data "$path"); done
step 旧模型评测 3000 python ml/scripts/validate_model.py --model "$BASELINE" "${EVAL_DATA[@]}" --project "$WORK_ROOT/evaluation/baseline"
step 新模型评测 3000 python ml/scripts/validate_model.py --model "$WORK_ROOT/runs/formal/weights/best.pt" "${EVAL_DATA[@]}" --project "$WORK_ROOT/evaluation/yolo26s" --compare "$WORK_ROOT/evaluation/baseline/validation_summary.json"
step 导出ONNX 1200 python - "$WORK_ROOT/runs/formal/weights/best.pt" <<'PY'
import sys,onnx
from ultralytics import YOLO
path=YOLO(sys.argv[1]).export(format='onnx',imgsz=640,batch=1,opset=17,dynamic=False,simplify=False,device='cpu')
onnx.checker.check_model(onnx.load(path))
PY
mkdir "$WORK_ROOT/result"
cp "$WORK_ROOT/runs/formal/weights/"{best.pt,last.pt,best.onnx} "$WORK_ROOT/result/"
cp "$WORK_ROOT/"{environment-freeze.txt,nvidia-smi.txt,input-weights.sha256,audit.json} "$WORK_ROOT/result/"
cp -r "$WORK_ROOT/evaluation" "$WORK_ROOT/result/"
cp "$WORK_ROOT/runs/formal/"{args.yaml,experiment.json,results.csv,results.png} "$WORK_ROOT/result/"
cp "$WORK_ROOT/dataset/"{manifest.csv,split_summary.json,sources.json,source_label_repairs.json,CHECKSUMS.sha256} "$WORK_ROOT/result/"
python - "$WORK_ROOT/result" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);files=[]
for p in sorted(root.rglob('*')):
    if p.is_file():
        with p.open('rb') as handle: digest=hashlib.file_digest(handle,'sha256').hexdigest()
        files.append(dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest))
(root/'ARCHIVE-MANIFEST.json').write_text(json.dumps(dict(status='trained',files=files),indent=2))
(root/'RESULT-CHECKSUMS.sha256').write_text(''.join(f"{r['sha256']}  {r['path']}\n" for r in files))
PY
cp "$WORK_ROOT/run_all.log" "$WORK_ROOT/result/"
step 归档 600 tar -C "$WORK_ROOT/result" -czf "$ARCHIVE_ROOT/results.tar.gz" .
sha256sum "$ARCHIVE_ROOT/results.tar.gz" > "$ARCHIVE_ROOT/results.tar.gz.sha256"
cp "$WORK_ROOT/result/ARCHIVE-MANIFEST.json" "$ARCHIVE_ROOT/"
echo "结果: $ARCHIVE_ROOT/results.tar.gz"
echo "本地同步命令见 docs/training/yolo26s-v3.md。"

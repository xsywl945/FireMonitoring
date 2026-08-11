#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
WORK_ROOT="${FIRE_WORK_ROOT:-/root/autodl-tmp/fire-monitoring}"

if [[ ! -d /root/autodl-tmp ]]; then
  echo "ERROR: /root/autodl-tmp does not exist; confirm this is an AutoDL instance." >&2
  exit 2
fi

mkdir -p \
  "${WORK_ROOT}/datasets/raw" \
  "${WORK_ROOT}/datasets/processed" \
  "${WORK_ROOT}/runs" \
  "${WORK_ROOT}/audits" \
  "${WORK_ROOT}/artifacts"

echo "Repository: ${REPO_ROOT}"
echo "Work root:  ${WORK_ROOT}"

python -m pip install --disable-pip-version-check \
  -r "${REPO_ROOT}/ml/requirements-autodl.txt"

python "${REPO_ROOT}/ml/scripts/check_environment.py" \
  --require-cuda \
  --workdir /root/autodl-tmp \
  | tee "${WORK_ROOT}/artifacts/environment-check.txt"

python -m pip freeze > "${WORK_ROOT}/artifacts/environment-freeze.txt"
nvidia-smi > "${WORK_ROOT}/artifacts/nvidia-smi.txt"
df -h / /root/autodl-tmp > "${WORK_ROOT}/artifacts/disk-usage.txt"

if [[ -d /root/autodl-fs ]]; then
  mkdir -p /root/autodl-fs/fire-monitoring-backup
  echo "Persistent file storage detected: /root/autodl-fs/fire-monitoring-backup"
else
  echo "WARNING: /root/autodl-fs is not available. Download checkpoints before releasing the instance."
fi

echo "AutoDL bootstrap PASSED. Next: download the two datasets."

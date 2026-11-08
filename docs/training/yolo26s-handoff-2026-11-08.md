# YOLO26s 训练交接（2026-11-08）

Grok 交付的部署候选为 `models/yolo26s-ft-2026-11-04/best.pt` 或 `best.onnx`。

## 文件

- `models/yolo26s-ft-2026-11-04/`：微调模型。`best.pt`、`best.onnx`、训练参数 `args.yaml`、`results.csv`、评测报告 `evaluation/`
- `models/yolo26s-v3-2026-11-03/`：正式训练模型（微调的起点）。同样带参数、曲线、数据划分、环境版本，以及旧 YOLO11s 的同测评测 `evaluation/yolo11s-baseline/`
- `ml/scripts/finetune_yolo26s.py`：微调脚本。原脚本留在 AutoDL 上没带回来，这份按 `args.yaml` 重写；显式训练参数已核对，未重新训练验证复现

## 训练过程

1. 正式训练：YOLO26s@640，数据 D-Fire + IFireSmoke（去重后训练集 13,164 张），使用 `ml/scripts/train_baseline.py`，配置上限 120 轮。交付 `results.csv` 实际记录 91 轮，验证 mAP50-95 峰值出现在第 66 轮
2. 微调：从正式训练的 `best.pt` 继续，SGD lr0=0.001，关闭 mosaic，上限 40 轮、patience 12。曲线记录 20 轮，验证 mAP50-95 峰值出现在第 8 轮
3. 注意：Ultralytics `optimizer=auto` 会忽略 lr0，微调必须显式写 `optimizer="SGD"`

环境：Ultralytics 8.4.100，torch 2.8.0+cu128，Python 3.12，RTX 4090D。

Grok 原交接写正式训练“120 轮，最佳 epoch 69”，与交付曲线不符。这里采用 CSV 记录的轮数与验证指标峰值，未直接读取权重内的训练 epoch。正式训练包记录 `git_dirty=true`，提交号只标识打包时的 Git 基点，不能单凭该提交证明云端代码完全相同。

## 结果（同一测试集）

| 模型 | D-Fire mAP50 | D-Fire mAP50-95 | COCO 背景图误报率 @0.25 |
|---|---:|---:|---:|
| YOLO11s 旧基线 | 0.745 | 0.432 | 11.68%（39/334） |
| YOLO26s 正式 | 0.733 | 0.428 | 2.99%（10/334） |
| YOLO26s 微调 | 0.731 | 0.419 | 1.80%（6/334） |

验证集选出的置信度阈值：fire 0.30，smoke 0.35。IFireSmoke 测试集只有 6 张，结果不作参考。

## 校验

- 微调 best.pt sha256 `429f7107d8810d912ab919f85285525eb8d8b167c050eb7b8450ea8f0772d027`
- 微调 best.onnx sha256 `5426dd16b54f8fa0e338b1d2d681b15492effaa3cf16808b91b0038cd3586dcd`
- 正式 best.pt sha256 `146ec675ae5b3b21533097e54e440f0a5c718a9099811876b316fc5d21b3dcfb`

以上指标摘自交付文件，本次未重新评测。原始参数、曲线和精简评测见 [实验目录](../experiments/2026-11-04-yolo26s/metrics.json)。微调降低了该背景集的误报，但 D-Fire mAP 下降。

2026-11-08 本地重新计算上述 3 个文件的 SHA-256，均一致。其余交付文件的路径、大小和本次计算的 hash 见 [归档清单](../../data/training-archive/2026-11-03-yolo26s-v3/ARCHIVE-MANIFEST.json)。

## AutoDL

Grok 交接记录称实例已关机，未释放；本次未登录云端核验。`/root/autodl-fs/fire-monitoring/` 下有两次训练的完整归档 `results.tar.gz`。

## 保存与部署状态

- `models/` 保留本地并整目录忽略，不加入普通 Git 或 Git LFS。Git 记录参数、评测摘要和归档清单；完整云端归档未在本次重新下载验证
- 推理服务 `apps/inference` 还没切到新模型

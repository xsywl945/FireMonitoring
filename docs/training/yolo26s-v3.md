# YOLO26s v3 训练

2026-11-08：正式训练与微调已完成，结果见 [训练交接](yolo26s-handoff-2026-11-08.md)。下文保留实际使用的训练流程。

模型固定 YOLO26s，输入 640，类别 `0=fire, 1=smoke`。本轮只使用公开图片。

## 数据来源

| 来源 | 原类别与格式 | 许可与出处 |
|---|---|---|
| D-Fire | `0=smoke, 1=fire`，归一化 YOLO 框 | [作者仓库](https://github.com/gaia-solutions-on-demand/DFireDataset)、[CC0 声明](https://github.com/gaia-solutions-on-demand/DFireDataset/blob/master/LICENSE)。`PublicDataset` 图片仍受原提供者条款约束，来源包括 HPWREN、FESB、FireNet；FESB 要求署名。此次使用本地已有 Kaggle ZIP。 |
| IFireSmoke | `0=Fire, 1=Smoke`，归一化 YOLO 框 | [作者数据卡](https://huggingface.co/datasets/shahriar-5/IFireSmoke/blob/main/README.md)，CC BY 4.0，署名 Shafak Shahriar Sozol。 |
| COCO 2017 train | captions 筛选灯光、夕阳、红色物体、屏幕、蒸汽和雾气，生成空标签 | [官方下载](https://cocodataset.org/#download)。图片逐张保留原 URL、Flickr URL 与许可 URL；COCO 标注许可不能替代图片许可。筛选代码见 `prepare_coco_negatives.py`，seed 42，每类上限 600。 |
| FASDD_CV | 论文说明提供 VOC、COCO、YOLO、TDML；此次未核实实际类别顺序 | [作者仓库](https://github.com/openrsgis/FASDD)、[DOI 下载入口](https://doi.org/10.57760/sciencedb.j00104.00103)。2026-11-03 访问详情 API 返回 `70001 / PERMISSION NO ACCESS`。无法取得可校验下载文件、类别表与数据许可，本轮跳过。 |

COCO 排除 captions 提到火、烟、燃烧、蜡烛、壁炉、烟花、机车、火车、烟囱、发动机、炉灶、烤箱、烧烤和烹饪的图片。2026-11-03 查看了全部 2,354 张候选的缩略图，放大复核 13 张，排除 5 张含烟羽、疑似蜡烛、煤油灯或无法确认来源的人造烟雾的图片，文件与原因见 `ml/configs/coco_negative_exclusions.csv`。筛选规则和逐图 captions 保存在 `negatives_metadata.csv`。空标签是本任务的火焰/烟雾背景标签，COCO 物体框不转换成火焰框。

## 本地生成

Python 环境先安装 `ml/requirements-autodl.txt`；本地 CPU 自测使用 PyTorch 2.8.0 CPU。AutoDL 使用镜像已有的 PyTorch，安装脚本不会主动重装 torch。

```powershell
python ml/scripts/prepare_coco_negatives.py --annotations D:/FireMonitoring-training-v3/raw/coco/annotations/captions_train2017.json --images-zip D:/FireMonitoring-training-v3/train2017.zip --output D:/FireMonitoring-training-v3/raw/negatives-reviewed --per-category 600 --exclusions ml/configs/coco_negative_exclusions.csv
python ml/scripts/prepare_fire_smoke_v1.py --sources ml/configs/fire_smoke_v3.sources.json --output D:/FireMonitoring-training-v3/merged --link
python ml/scripts/build_leakage_safe_primary_split.py --manifest D:/FireMonitoring-training-v3/merged/manifest.csv --baseline-manifest data/training-archive/2026-08-12-yolo11s-primary-v2/dataset/metadata/primary_fire_smoke_v2/manifest.csv --output D:/FireMonitoring-training-v3/dataset --link
python ml/scripts/audit_yolo_dataset.py --data D:/FireMonitoring-training-v3/dataset/data.yaml --output D:/FireMonitoring-training-v3/audit.json --phash-threshold 4
powershell -File scripts/New-AutoDLTrainingBundle.ps1
```

`fire_smoke_v3.sources.json` 的 `root` 是本机路径。更换数据存放位置时直接修改此文件。`--link` 要求源与目标位于同一文件系统，失败会退出。

IFireSmoke 的 `FireDataV*_视频号_帧号` 按视频分组，Roboflow `.rf.` 变体保留相同图片身份。D-Fire 的 AoF 和 PublicDataset 各作为保守集合组，其余图片按原图片身份与 pHash 连接。pHash Hamming 距离不超过 4 的连接分量只保留一张，优先保留目标数更多的标注。跨来源近似图和同场景组取并集后再划分。旧模型 train、val 样本所在组固定放入 train，禁止进入新 test。train 空标签比例目标 12.5%，优先使用 COCO 困难背景。

WEB 与纯数字图片缺少原始视频/场景身份，只能通过图片身份和 pHash 近似分组。这不能证明所有未知场景都已完全隔离。旧模型已公布的测试结果也不构成对全新场景的证明。`split_summary.json`、manifest 的 `group_method` 和 `baseline_exposed` 保留这些范围。

数据包根目录包含 `data.yaml`、各来源测试 YAML、相对图片清单、`manifest.csv`、来源配置、标签修复、去重记录和 `CHECKSUMS.sha256`。ZIP 与 ZIP 自身的 SHA-256 文件不提交 Git。

本机最终数据已审计：train 13,164、val 868、test 879；训练 COCO 背景 1,645 张，占 12.496%。test 为 D-Fire 539、IFireSmoke 6、negatives 334 张。跨划分精确重复与 pHash 距离不超过 4 的近重复均为 0，审计错误和警告均为 0。IFireSmoke 只剩 6 张未暴露测试图，不能用它单独证明该来源的精度提升。

数据 ZIP 大小 1,179,442,073 字节，SHA-256 为 `968daaa46b027fa73f2262d4c848d064671e2760931ee733c155574386dbf045`。位置为 `D:/FireMonitoring-training-v3/fire-smoke-v3.zip`。

## AutoDL 执行

上传数据 ZIP 及 `.sha256`、代码 ZIP、官方 `yolo26s.pt`、AMP 检查使用的官方 `yolo26n.pt`、旧归档的 `models/deployment/best.pt`。旧权重上传后命名为 `yolo11s-best.pt`。不在云端下载或清洗数据。

```bash
cd /root/autodl-tmp
unzip FireMonitoring-AutoDL-*.zip
# 数据和权重放在 /root/autodl-tmp/upload/。
tmux new-session -d -s yolo26s-v3 \
  'DATA_ZIP=/root/autodl-tmp/upload/fire-smoke-v3.zip PRETRAINED=/root/autodl-tmp/upload/yolo26s.pt BASELINE=/root/autodl-tmp/upload/yolo11s-best.pt timeout --signal=TERM --kill-after=60 20h bash /root/autodl-tmp/FireMonitoring/ml/autodl/run_all.sh'
tmux attach -t yolo26s-v3
```

`run_all.sh` 顺序执行：安装依赖、检查 Python 3.12 / PyTorch 2.8.0 / CUDA 12.8 / RTX 4090、核验输入与 ZIP hash、解压、核验包内全部 SHA-256、重写数据根目录、审计、2 epoch 冒烟、正式训练、旧模型评测、新模型评测、ONNX 导出校验、打包到 autodl-fs。任何一步失败会退出并打印命令与行号。要求 `/root/autodl-fs` 已挂载，工作目录必须不存在。

正式训练：最多 120 epoch，patience 25，640，自动 batch 0.7，AMP，seed 42，cos_lr，save_period 5，cache=False，`time=14`。库内 timed training 会改变 epoch 数，训练器在建立 cosine 调度器时固定轮数上限。外层 `timeout 20h` 限制整个流程，不包含开机前的上传等待；上传/环境阶段仍须遵守 2 小时预算。

恢复只使用带 optimizer 的未完成检查点。正常完成后的 best.pt、last.pt 已被 Ultralytics 去掉 optimizer，不能继续 resume。以下命令用于失败后恢复正式训练，不会自动重复已完成的评测步骤：

```bash
python ml/scripts/train_baseline.py \
  --data /root/autodl-tmp/yolo26s-v3/dataset/data.yaml \
  --project /root/autodl-tmp/yolo26s-v3/runs --name formal \
  --resume /root/autodl-tmp/yolo26s-v3/runs/formal/weights/last.pt \
  --epochs 120 --patience 25 --time 14 --batch 0.7 --cache none --seed 42
```

恢复时核对同一 manifest，保留首次初始化权重 hash，记录恢复检查点 hash，以检查点内历史覆盖 results.csv，并从 14 小时预算扣除首次启动后已过去的时间。

## 评测与交付

两个模型使用同一数据 manifest、640 和测试来源清单。mAP 使用 confidence 0.001、IoU 0.7；逐类统计、小目标召回和负样本误报同时报告固定 confidence 0.25 与各自验证集选出的阈值。阈值按验证集每类 IoU 0.5 F1 最大值选取，候选 0.05 到 0.95，间隔 0.05；并列时取较高阈值。test 不参与阈值选择。

小目标定义为图片缩放至 640 后框面积小于 32² 像素，报告 IoU 0.5 召回与目标计数。它不等同于 COCO AP_small。负样本误报率为出现至少一个检测框的空标签图片数除以空标签图片数，同时保留误报框数。错误 JSON 包含全部错误图片的真值和预测，最多导出 40 张标图，绿色是真值，红色是预测。

`evaluation/*/validation_report.md` 与 `validation_summary.json` 给出按来源、fire/smoke、固定阈值、建议阈值和相对旧模型的 mAP 差值。差值可以为负，脚本不预设提升。RTX 5060 Laptop 的四路性能尚未测试。

结果保存到 `/root/autodl-fs/fire-monitoring/2026-11-03-yolo26s-v3/results.tar.gz`，包含 best.pt、last.pt、best.onnx、两模型评测、阈值建议、环境冻结、训练曲线、数据 manifest 和归档 SHA-256 清单。下载到本地：

```powershell
scp -P 26369 root@connect.cqa1.seetacloud.com:/root/autodl-fs/fire-monitoring/2026-11-03-yolo26s-v3/results.tar.gz data/training-archive/2026-11-03-yolo26s-v3/
scp -P 26369 root@connect.cqa1.seetacloud.com:/root/autodl-fs/fire-monitoring/2026-11-03-yolo26s-v3/results.tar.gz.sha256 data/training-archive/2026-11-03-yolo26s-v3/
```

先用 `Get-FileHash -Algorithm SHA256` 对照下载的 `.sha256`，再解压。只将 `ARCHIVE-MANIFEST.json` 更新进 Git。权重、数据和图片保持忽略。

AutoDL 训练已完成。本次只核对本地交付文件和既有实验记录，未登录云端重跑训练或核验完整归档。

## 自测

```powershell
$env:YOLO26S_WEIGHTS='D:/FireMonitoring-training-v3/yolo26s.pt'
$env:PYTHONIOENCODING='utf-8'
$env:YOLO_AUTOINSTALL='false'
.venv/Scripts/python.exe -m unittest discover -s ml/tests -v
python -m compileall -q ml/scripts
```

自测包括类别反转与坏框裁剪、分组/旧模型隔离和审计、COCO 排除规则与来源、误报及小目标计数、真实 YOLO26s CPU 训练 2 epoch、从 epoch0 恢复、初始权重 hash、同名 YAML 汇总和 ONNX checker。缺少 `YOLO26S_WEIGHTS` 时训练自测显示 skipped，不能视为训练流程已验证。

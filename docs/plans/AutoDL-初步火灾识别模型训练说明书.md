# AutoDL 初步火灾识别模型训练说明书

版本：v1.0
编制日期：2026-07-18
适用目标：3～5 天内训练出可在本项目和 Windows RTX 5060 Laptop GPU 上演示的火焰/烟雾检测基线

> 安全边界：这是科研与演示模型，不能替代通过认证的火灾探测器、报警器和消防流程，也不能成为唯一的
> 生命安全告警链路。真实场所测试必须保留人工确认和既有消防设施。

## 1. 先给结论

首轮建议采用：

| 项目 | 选择 |
|---|---|
| 任务 | 目标检测，不是整图分类 |
| 类别 | `0=fire`、`1=smoke` |
| 主模型 | `YOLO11s` 预训练权重微调 |
| 主训练数据 | D-Fire 官方划分的训练/验证部分 + IFireSmoke 官方划分的训练/验证部分 |
| 测试数据 | 合并测试集、D-Fire 测试集、IFireSmoke 测试集分别评估 |
| 云端 GPU | 首选单卡 RTX 4090 24GB；5090 每小时价格不超过 4090 的约 1.35 倍时可选 |
| AutoDL 镜像 | PyTorch 2.8.0、Python 3.12、CUDA 12.8 |
| 训练框架 | `ultralytics==8.4.100`，固定版本，不在同一轮实验中升级 |
| 输入尺寸 | `640×640` |
| 训练长度 | 先 10 epoch 小跑，再 100 epoch 正式训练，`patience=20` |
| 交付格式 | `best.pt` 为主，另导出固定 `640×640` 的 FP32 ONNX |

这是一条“先成功、可复现、再扩大”的路线。它与长期计划
《第一阶段-火灾检测模型训练计划.md》并不冲突：长期方案仍以 FASDD_CV 扩大泛化能力，
本说明书则专门解决“这几天先做出第一个可信模型”。

首轮完成的定义不是只看到训练结束，而是同时得到：

1. 类别映射确认无误、结构检查通过的数据集；
2. `best.pt`、`last.pt`、训练参数、曲线和混淆矩阵；
3. 三套测试结果：合并测试、D-Fire 测试、IFireSmoke 室内测试；
4. 至少一组教室/实验室真实负样本视频测试结果；
5. `best.onnx` 和一份已知失败案例清单。

## 2. 为什么这样选择

### 2.1 首轮使用 D-Fire + IFireSmoke

[D-Fire 官方仓库](https://github.com/gaia-solutions-on-demand/DFireDataset)列出超过
21,000 张图像，其中仅火焰 1,164 张、仅烟雾 5,867 张、火焰和烟雾同时出现
4,658 张、无火无烟 9,838 张；共有 14,692 个火焰框和 11,865 个烟雾框。
它最大的价值并非只有正样本，而是近一万张负样本，可帮助模型认识云、雾、强光等非火灾画面。
官方仓库提供 YOLO 标注和预划分数据，数据集合以
[CC0 1.0](https://github.com/gaia-solutions-on-demand/DFireDataset/blob/master/LICENSE)
发布。

[IFireSmoke 配套论文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0322052)
公开了 5,000 张室内图像和 5,931 个目标，官方训练/验证/测试比例为 80:10:10。
论文说明其约 60% 来自本地拍摄、约 40% 来自网络和合成来源，场景比纯野外数据更接近本项目的
教室和实验室。原始压缩包约 92.3MB，可从
[Hugging Face](https://huggingface.co/datasets/shahriar-5/IFireSmoke/tree/main)
下载，数据卡标注为 MIT License。

两个数据集有一个危险的差异：

| 数据源 | 源类别 0 | 源类别 1 | 本项目目标顺序 |
|---|---|---|---|
| D-Fire | smoke | fire | 需要交换为 `fire, smoke` |
| IFireSmoke | fire | smoke | 保持不变 |

本项目提供的 `prepare_fire_smoke_v1.py` 会验证数据包中的 YAML，并把 D-Fire 标签
`0↔1` 后统一为小写 `fire/smoke`。不要直接把两个目录拼在一起训练。

### 2.2 为什么首轮不直接下载完整 FASDD

[FASDD 论文](https://doi.org/10.1080/10095020.2024.2347922)描述了超过 12 万张、
覆盖地面、无人机和遥感来源的异构图像，且提供 YOLO、COCO、VOC、TDML 等格式；
[官方项目页](https://github.com/openrsgis/FASDD)和
[数据 DOI](https://doi.org/10.57760/sciencedb.j00104.00103)均已公开。
它适合长期方案，但下载、解压、分域、去重和检查所需时间明显更多，遥感/UAV 子集还会引入与室内摄像头
不一致的视角。首轮先把训练链路跑通；第二轮再加入 FASDD_CV，而不是 FASDD_RS。

### 2.3 为什么仍先训练检测器，不让多模态模型直接识别

[SmokeBench（WACV 2026）](https://openaccess.thecvf.com/content/WACV2026/html/Qi_SmokeBench_Evaluating_Multimodal_Large_Language_Models_for_Wildfire_Smoke_Detection_WACV_2026_paper.html)
发现多模态大模型在烟雾面积较大时可以做存在性判断，但对早期、小体积烟雾的准确定位普遍困难。
因此本项目应让 YOLO 负责实时定位，让云端多模态模型在告警候选产生后负责火源性质和场景风险解释，
二者职责不能倒置。

[DetectiumFire](https://arxiv.org/abs/2511.02495)有约 22.5k 高分辨率图像和
2.5k 真实视频，并同时提供框和语义描述，非常适合后续风险研判；但首轮并入前仍要确认每张含烟图像是否有
完整烟雾框，否则未标注烟雾会被当成背景。它暂不进入 v0.1 主训练集。

[CaMuViD（CVPR 2025）](https://openaccess.thecvf.com/content/CVPR2025/papers/Daryani_CaMuViD_Calibration-Free_Multi-View_Detection_CVPR_2025_paper.pdf)
证明无标定多视角特征融合有研究价值，但它的任务和数据主要是多视角行人检测。当前两路摄像头先共享同一
YOLO 权重，各自输出检测，再在系统层做时序与决策融合；不要在第一个模型中同时引入多视角网络。

## 3. GPU 和软件选择

### 3.1 4090 还是 5090

[NVIDIA 官方规格](https://www.nvidia.com/en-eu/geforce/graphics-cards/40-series/rtx-4090/)
显示 RTX 4090 有 24GB GDDR6X；
[NVIDIA Blackwell 白皮书](https://images.nvidia.com/aem-dam/Solutions/geforce/blackwell/nvidia-rtx-blackwell-gpu-architecture.pdf)
列出 RTX 5090 有 32GB GDDR7。对于约 2.6 万张、`YOLO11s`、640 分辨率的单卡训练，两者显存都足够。

推荐决策：

- 默认租 4090：软件成熟、24GB 足够，首轮性价比通常更好。
- 如果同地区同 CPU/磁盘条件下，5090 的实时价格不超过 4090 约 1.35 倍，并且你希望缩短等待，可租 5090。
- 如果选择 5090，必须使用 CUDA 12.8 构建的 PyTorch。PyTorch 官方在
  [2.7 发布说明](https://pytorch.org/blog/pytorch-2-7/)中说明 Blackwell 支持随 CUDA 12.8 wheel 引入。
- AutoDL 当前镜像表已列出 PyTorch 2.8.0 + Python 3.12 + CUDA 12.8，4090 和 5090 都可用同一镜像。

不要为了 v0.1 租多卡。单卡训练更便宜、故障点更少，且 Ultralytics 的自动 batch 能充分使用显存。

### 3.2 AutoDL 实例建议

创建实例时选择：

- GPU：RTX 4090 ×1 或 RTX 5090 ×1；
- 镜像：PyTorch 2.8.0 / Python 3.12 / CUDA 12.8；
- CPU：至少 8 个逻辑核心；
- 内存：至少 32GB，推荐 64GB；
- 本地数据盘：至少 30GB，推荐 50GB；
- 地区：优先价格、GPU 空闲和网络稳定，不必为“离本地近”支付明显溢价。

[AutoDL GPU 文档](https://www.autodl.com/docs/gpu/)说明 GPU 为实例独占，并建议每卡至少
4～8 个 CPU 逻辑核心以支持数据加载。训练数据放 `/root/autodl-tmp`，不要直接从网络文件存储训练。
[AutoDL 文件存储文档](https://www.autodl.com/docs/fs/)也建议重要代码/数据放共享存储，训练时复制到本地盘
以获得更好的 I/O；文件存储 20GB 以内免费，但 I/O 一般。

### 3.3 工具版本和许可

本说明书固定使用 `ultralytics==8.4.100`。这是 2026-07-18 的
[PyPI 发布版本](https://pypi.org/project/ultralytics/)。不要在一次实验中先后执行无版本号升级，
否则同一命令的默认超参数可能变化。

[YOLO11 官方文档](https://docs.ultralytics.com/models/yolo11/)列出 `yolo11s.pt` 支持训练、验证、推理和导出；
它在 640 输入下约 9.4M 参数，适合作为第一个可部署基线。YOLO26s 是后续 A/B 候选，而不是首轮唯一模型，
因为它的端到端双头输出和部署后处理与传统 YOLO11 不完全相同。

许可必须提前知道：Ultralytics 当前说明其代码、模型和训练产物默认采用 AGPL-3.0；学术、个人和完整开源
项目可使用，如未来做闭源或商业部署，应重新审查并可能购买 Enterprise License。请以
[Ultralytics 当前许可说明](https://www.ultralytics.com/license)为准。这不是法律意见。

## 4. 3～5 天执行日程

| 时间 | 工作 | 当日通过条件 |
|---|---|---|
| 第 1 天上午 | 创建 AutoDL 实例、上传工具包、检查 CUDA | 环境检查输出 `PASSED` |
| 第 1 天下午 | 下载 D-Fire 和 IFireSmoke、统一类别、审计 | 无坏图、坏标签、跨集合精确重复；预览框正确 |
| 第 2 天 | 10 epoch 小跑；确认后正式训练 100 epoch | loss 正常下降，显存稳定，训练图中类别正确 |
| 第 3 天 | 三套测试、错误案例分析 | 生成三套混淆矩阵和 `validation_summary.json` |
| 第 4 天 | 采集本地负样本视频、测误报、必要时小幅微调 | 得到每摄像头小时误报数和失败案例目录 |
| 第 5 天 | 导出 ONNX、下载归档、在 Windows 接入 | `best.pt`/ONNX 可推理，归档已复制出 AutoDL 实例 |

如果下载或标注审计占用更多时间，宁可把正式训练顺延，也不要跳过类别预览和测试集隔离。

## 5. 开始前准备

你需要：

1. AutoDL 账户和足够余额；
2. Kaggle 账户；
3. Kaggle 个人 API 凭据 `kaggle.json`；
4. 本项目中的 `ml/` 目录；
5. 约 30～50GB AutoDL 本地数据盘；
6. 本地保留一份最终权重备份的位置。

`kaggle.json` 是密钥，不得发送给他人、贴进聊天、写进 Markdown、放进 Git 或模型压缩包。

本地 Clash Verge 的 TUN 模式只代理你的 Windows 网络，不会自动代理 AutoDL 远程实例。若 AutoDL 直连
Kaggle/Hugging Face 失败，可以在本地通过 TUN 下载后，经 AutoDL 网页/JupyterLab 上传；不要把本地
`127.0.0.1:7890` 写成 AutoDL 代理地址，因为远程实例里的 `127.0.0.1` 指向远程实例自己。

## 6. 手把手操作

下面命令都在 AutoDL 的 JupyterLab Terminal 或 SSH 中执行。每段执行成功后再进入下一段。

### 6.1 创建目录

```bash
mkdir -p /root/autodl-tmp/fire-monitoring/{datasets/raw,datasets/processed,runs,audits,artifacts}
cd /root/autodl-tmp/fire-monitoring

if [ -d /root/autodl-fs ]; then
  mkdir -p /root/autodl-fs/fire-monitoring-backup
else
  echo "WARNING: 尚未挂载 AutoDL 文件存储"
fi
```

不要在 `/root/autodl-fs` 不存在时直接创建这个根目录，否则普通系统盘目录会被误认为持久化文件存储。
若实例没有该目录，先在 AutoDL 控制台初始化同地区“文件存储”，然后重启实例；也可暂时把备份下载到
Windows，但不能只留在即将释放的实例中。

### 6.2 上传本项目训练工具包

最简单的方法是在 AutoDL JupyterLab 左侧文件栏上传项目压缩包，解压后保证路径为：

```text
/root/autodl-tmp/fire-monitoring/FireMonitoring/ml/
```

本项目可在 Windows 本地生成最小上传包：

```powershell
cd C:\Users\xsywl\Desktop\FireMonitoring
powershell -File scripts/New-AutoDLTrainingBundle.ps1
```

上传 `tmp/autodl-upload/` 中最新的 ZIP 后，在 AutoDL 执行：

```bash
cd /root/autodl-tmp/fire-monitoring
unzip -q /上传路径/FireMonitoring-AutoDL-*.zip -d .
cd FireMonitoring
bash ml/autodl/bootstrap.sh
```

脚本会完成第 6.1 节目录创建、第 6.3 节依赖安装与 GPU 检查，并把检查结果写入
`/root/autodl-tmp/fire-monitoring/artifacts/`。如果已运行脚本，可以跳过下面重复的安装命令。

若项目已有远程 Git 仓库，也可以：

```bash
cd /root/autodl-tmp/fire-monitoring
git clone <你的仓库地址> FireMonitoring
```

确认：

```bash
cd /root/autodl-tmp/fire-monitoring/FireMonitoring
ls ml/scripts
```

应至少看到 `check_environment.py`、`prepare_fire_smoke_v1.py`、
`audit_yolo_dataset.py`、`train_baseline.py`。

### 6.3 安装依赖并检查 GPU

```bash
cd /root/autodl-tmp/fire-monitoring/FireMonitoring
python -m pip install --upgrade pip
python -m pip install -r ml/requirements-autodl.txt
python ml/scripts/check_environment.py --require-cuda --workdir /root/autodl-tmp
```

通过条件：

- `cuda_available` 为 `true`；
- GPU 名称与所租型号一致；
- 4090 显存约 24GiB，5090 约 32GiB；
- 最后一行是 `Environment check PASSED.`；
- 空闲磁盘建议至少 20GiB，最好超过 30GiB。

再保存环境版本：

```bash
python -m pip freeze > /root/autodl-tmp/fire-monitoring/artifacts/environment-freeze.txt
nvidia-smi > /root/autodl-tmp/fire-monitoring/artifacts/nvidia-smi.txt
```

若 5090 报 `sm_120 is not compatible`，说明选错了旧 PyTorch/CUDA wheel。停止计费训练，换成
PyTorch 2.8.0 + CUDA 12.8 镜像。不要先尝试手工重装系统 CUDA；
[AutoDL CUDA 文档](https://www.autodl.com/docs/cuda/)也说明通常只需选择匹配的框架，无需另装 CUDA/cuDNN。

### 6.4 下载 IFireSmoke

```bash
RAW=/root/autodl-tmp/fire-monitoring/datasets/raw
mkdir -p "$RAW/ifiresmoke"
curl -L --fail --retry 3 \
  -o "$RAW/ifiresmoke/Indoor-FS.zip" \
  "https://huggingface.co/datasets/shahriar-5/IFireSmoke/resolve/main/Indoor%20FS.zip?download=true"
unzip -q "$RAW/ifiresmoke/Indoor-FS.zip" -d "$RAW/ifiresmoke"
find "$RAW/ifiresmoke" -maxdepth 3 -name data.yaml -print
```

应看到 `Indoor FS/data.yaml`。原始包的结构应为 4,000 训练、500 验证、500 测试，类别顺序为
`Fire, Smoke`。

### 6.5 下载 D-Fire

在 Kaggle 账户设置中创建 API token，把 `kaggle.json` 通过 JupyterLab 上传到
`/root/autodl-tmp/kaggle.json`，然后：

```bash
python -m pip install kaggle
mkdir -p /root/.kaggle
install -m 600 /root/autodl-tmp/kaggle.json /root/.kaggle/kaggle.json

RAW=/root/autodl-tmp/fire-monitoring/datasets/raw
mkdir -p "$RAW/dfire"
kaggle datasets download \
  -d sayedgamal99/smoke-fire-detection-yolo \
  -p "$RAW/dfire" \
  --unzip
find "$RAW/dfire" -maxdepth 3 -type d \( -iname train -o -iname val -o -iname test \) -print
```

这是 D-Fire 官方仓库列出的 Kaggle 可用版本；约 3.12GB，源类别为 `0=Smoke, 1=Fire`。
如果 Kaggle API 失败，可从 D-Fire 官方仓库的“Training, validation and test sets”链接下载到本地，
再上传原压缩包。不要改用来源、类别顺序和划分都不明的网盘包。

### 6.6 统一类别并生成 v1 数据

```bash
cd /root/autodl-tmp/fire-monitoring/FireMonitoring

python ml/scripts/prepare_fire_smoke_v1.py \
  --dfire-root /root/autodl-tmp/fire-monitoring/datasets/raw/dfire \
  --ifiresmoke-root /root/autodl-tmp/fire-monitoring/datasets/raw/ifiresmoke \
  --output /root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v1 \
  --link
```

脚本做四件事：

1. 自动寻找两套数据中的 `train/val/test` 或 `train/valid/test`；
2. 核对数据 YAML 的源类别顺序；
3. 将 D-Fire 的类别交换，最终统一为 `0=fire, 1=smoke`；
4. 核对推荐数据版本的总图像数和无目标图像数，单独记录缺失/空源标签，防止下载不完整被误当成负样本；
5. 对当前D-Fire包已知的18个零面积框做删除、379个越界框做边界裁剪，并把原值和修复值写入审计文件；
6. 按 `test > val > train` 优先级去除跨集合完全相同的图像，不覆盖原数据。

`--link` 会优先创建硬链接，节省本地盘；如果文件系统不支持，会自动退回复制。输出目录必须是新的空目录，
脚本不会删除或覆盖以前实验。完成后应生成：

```text
fire_smoke_v1/
├─ images/{train,val,test}/
├─ labels/{train,val,test}/
├─ eval/dfire/images/test/
├─ eval/ifiresmoke/images/test/
├─ fire_smoke_v1.yaml
├─ dfire_test.yaml
├─ ifiresmoke_test.yaml
├─ manifest.csv
├─ prepare_summary.json
├─ source_label_repairs.json
└─ exact_duplicates_removed.json
```

`manifest.csv` 是以后论文复现实验的重要清单，不要丢。
打开 `prepare_summary.json`，还应确认：D-Fire 为 21,527 张、9,838 张无目标图像；IFireSmoke 为
5,000 张、0 张无目标图像。`missing_source_label_files` 与 `empty_source_label_files` 会分别记录“没有源标签文件”
和“源标签为空”的数量；脚本按无目标图像总数做完整性校验，数量异常会直接停止。
`source_label_repairs.json` 必须恰好记录当前推荐D-Fire版本的397处受控修复：18个
`drop_degenerate_box` 和379个 `clip_box_to_image`。越界中位数约0.33%、95分位约3.06%、最大约9.41%；
修复数超过450或单框越界超过10%时脚本会停止，不能把未知版本的问题静默吞掉。

### 6.7 自动审计数据

```bash
python ml/scripts/audit_yolo_dataset.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v1/fire_smoke_v1.yaml \
  --output /root/autodl-tmp/fire-monitoring/audits/fire_smoke_v1.json \
  --phash-threshold 4
```

通过条件：

- 输出最后显示 `PASSED`；
- `errors` 为空；
- 类别必须精确为 `0: fire, 1: smoke`；
- 没有坏图、缺失标签、非 5 列标签、未知类别和越界框；
- `exact_cross_split_duplicate_groups` 为空。

感知哈希警告表示训练/验证/测试间可能有近重复图像。打开 JSON 查看路径；若同一原视频相邻帧分别出现在
训练和测试，应从训练侧移除并重新生成新版本数据。不要通过修改测试集来“提高成绩”。当前D-Fire和
IFireSmoke官方划分均存在连续帧近重复，因此主训练必须继续生成隔离划分：

```bash
python ml/scripts/build_leakage_safe_primary_split.py \
  --manifest /root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v1/manifest.csv \
  --output /root/autodl-tmp/fire-monitoring/datasets/processed/primary_fire_smoke_v1 \
  --phash-threshold 4 \
  --link

python ml/scripts/audit_yolo_dataset.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/primary_fire_smoke_v1/primary_fire_smoke_v1.yaml \
  --output /root/autodl-tmp/fire-monitoring/audits/primary_fire_smoke_v1.json \
  --phash-threshold 4
```

主划分保留IFireSmoke测试集不变；从IFireSmoke验证集移除与测试集近似的图，再从D-Fire/IFireSmoke
训练图中移除与保留验证/测试图近似的样本。D-Fire官方验证/测试仅作带泄漏提示的参考，不用于早停或主结论。

### 6.8 人工看标注——这一步不可省略

```bash
python ml/scripts/preview_yolo_dataset.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/primary_fire_smoke_v1/primary_fire_smoke_v1.yaml \
  --split train \
  --count 32 \
  --output /root/autodl-tmp/fire-monitoring/audits/train-preview.jpg
```

从 JupyterLab 下载并打开 `train-preview.jpg`。图中规定：

- 红框：`0:fire`，必须套住火焰；
- 蓝框：`1:smoke`，必须套住烟雾；
- 无火无烟图片应该没有框。

如果颜色相反，立即停止，不要“先训起来看看”。如果框大量过松、错位或漏掉明显烟雾，记录对应文件名和
来源，先决定修标还是剔除。

### 6.9 先做 10 epoch 小跑

```bash
cd /root/autodl-tmp/fire-monitoring/FireMonitoring

python ml/scripts/train_baseline.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/primary_fire_smoke_v1/primary_fire_smoke_v1.yaml \
  --model yolo11s.pt \
  --project /root/autodl-tmp/fire-monitoring/runs \
  --name yolo11s_smoke_test \
  --epochs 10 \
  --patience 10 \
  --fraction 0.10
```

脚本固定了 AMP、种子 42、确定性模式、磁盘缓存、余弦学习率、轻度几何增强、`mosaic=0.5`、
最后 10 epoch 关闭 Mosaic，并让 `batch=0.70` 自动使用约 70% 显存。
[Ultralytics 训练文档](https://docs.ultralytics.com/modes/train/)明确支持浮点 batch 作为显存比例、
`cache=disk`、AMP、`fraction` 和断点恢复。

小跑通过条件：

- 没有 CUDA OOM、NaN、坏图或类别错误；
- `train_batch*.jpg` 中红框仍是火焰、蓝框仍是烟雾；
- box/cls/dfl loss 总体下降；
- 验证指标不是一直为 0；
- GPU 利用率大部分时间较高，显存稳定。

此时用每个 epoch 的实际耗时估算正式训练时间，比套用他人的小时数可靠。

### 6.10 正式训练

长时间任务应使用守护会话，避免 SSH 断开导致训练终止。
[AutoDL 守护进程文档](https://www.autodl.com/docs/daemon/)推荐 JupyterLab Terminal、screen 或 tmux。

```bash
apt-get update && apt-get install -y tmux
tmux new -s fire-yolo
```

在 tmux 中执行：

```bash
cd /root/autodl-tmp/fire-monitoring/FireMonitoring

python ml/scripts/train_baseline.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/primary_fire_smoke_v1/primary_fire_smoke_v1.yaml \
  --model yolo11s.pt \
  --project /root/autodl-tmp/fire-monitoring/runs \
  --name yolo11s_dfire_ifire_v1 \
  --epochs 100 \
  --patience 20 \
  --imgsz 640 \
  --batch 0.70 \
  --workers 8 \
  --device 0
```

按 `Ctrl+B`，再按 `D` 可退出 tmux 而不终止训练。恢复查看：

```bash
tmux attach -t fire-yolo
```

另开一个终端监控：

```bash
watch -n 2 nvidia-smi
tail -f /root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1/results.csv
```

若 GPU 利用率经常低于 50% 且 CPU 未满，可把 `workers` 从 8 调到 12；若内存不足或 DataLoader 崩溃，
降到 4。不要在正式运行中途修改数据或 YAML。

### 6.11 中断后恢复

Ultralytics 会在每个 epoch 保存 `last.pt`，且本脚本每 5 个 epoch 额外保存一次。恢复时用官方命令：

```bash
yolo detect train resume \
  model=/root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1/weights/last.pt
```

官方说明恢复会加载模型、优化器、学习率调度器和 epoch 状态。不要拿 `best.pt` 当作同一次训练的
`resume` 文件；`best.pt` 更适合新一轮微调或部署。

### 6.12 三套测试

```bash
BEST=/root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1/weights/best.pt
DATA=/root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v1

python ml/scripts/validate_model.py \
  --model "$BEST" \
  --data "$DATA/fire_smoke_v1.yaml" \
  --data "$DATA/dfire_test.yaml" \
  --data "$DATA/ifiresmoke_test.yaml" \
  --project /root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1_eval \
  --imgsz 640 \
  --batch 32 \
  --device 0
```

重点查看：

- 每类 precision、recall 和 AP，而不只看总 mAP；
- smoke recall：早期烟雾漏检比框略松更危险；
- IFireSmoke 室内测试是否明显弱于 D-Fire；
- 混淆矩阵、PR 曲线和测试预测图；
- `validation_summary.json` 中三套数据的差距。

`validation_summary.json` 的 `per_class.fire` 和 `per_class.smoke` 会直接给出每类 precision、recall、
mAP@0.5 和 mAP@0.5:0.95，可逐项对照下面的验收线。

v0.1 建议验收线，不是论文最终指标：

| 指标 | 建议最低线 |
|---|---:|
| 合并测试 mAP@0.5 | ≥ 0.80 |
| 合并测试 mAP@0.5:0.95 | ≥ 0.50 |
| fire recall | ≥ 0.80 |
| smoke recall | ≥ 0.80 |
| IFireSmoke 室内两类 recall | 各 ≥ 0.75 |

如果公开测试指标很高但本地摄像头误报严重，模型仍不合格。公开测试 mAP 与真实系统误报率是两个不同指标。

### 6.13 测教室/实验室真实负样本

在最终演示使用的电脑前置摄像头和第二路 USB/IP 摄像头上，各录至少 30～60 分钟无火视频，覆盖：

- 日光、夕阳、灯光反射、红色/橙色物体；
- 投影屏、视频中的火焰、手机屏幕；
- 烧水蒸汽、空调气流、窗外雾和云；
- 低照度噪声、人物走动、镜头遮挡和自动曝光变化。

严禁为了采集数据擅自在教室或实验室点火、放烟。正样本可用公开测试视频，或在指导教师、场地管理和消防
安全条件全部满足时由专业人员组织受控试验。

用单帧模型预测本地负样本：

```bash
yolo detect predict \
  model="$BEST" \
  source=/root/autodl-tmp/fire-monitoring/local-negative-videos \
  imgsz=640 \
  conf=0.10 \
  save=True \
  save_txt=True \
  save_conf=True \
  project=/root/autodl-tmp/fire-monitoring/runs \
  name=local_negative_predict
```

此处故意用较低 `conf=0.10` 暴露疑似误报；系统最终告警阈值不能直接照搬。记录：

```text
每摄像头小时误报数 = 误报事件数 / 视频总小时数
```

先以“每路每小时明显误报不超过 1 次”作为 v0.1 调试目标，后续再用 3-of-5、持续时间和双摄决策降低
系统告警误报。不要为了让数字变好而把单帧阈值抬到漏掉小烟雾。

### 6.14 可选的第二轮微调

如果主要问题是投影屏、红灯、蒸汽等固定误报，挑出 500～2,000 张本地困难负样本，人工确认无火无烟，
为每张图创建同名空 `.txt` 标签，只加入训练集。保持原测试集冻结，用第一轮 `best.pt` 微调 20～30 epoch：

```bash
python ml/scripts/train_baseline.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v2/fire_smoke_v2.yaml \
  --model "$BEST" \
  --project /root/autodl-tmp/fire-monitoring/runs \
  --name yolo11s_domain_finetune_v2 \
  --epochs 30 \
  --patience 10
```

如果误报下降但公开测试 recall 明显下降，说明负样本比例或微调强度过大，应回退并减少本地负样本权重。

### 6.15 导出给 Windows

先保留原始 `best.pt`。再导出固定输入的 FP32 ONNX：

```bash
yolo export \
  model="$BEST" \
  format=onnx \
  imgsz=640 \
  dynamic=False \
  simplify=True \
  opset=17
```

[Ultralytics 导出文档](https://docs.ultralytics.com/modes/export/)说明 ONNX 支持固定/动态尺寸、图简化和
opset 设置。当前项目只有 640 输入，固定尺寸更容易在 Windows 上复现和优化。

不要在 AutoDL 4090/5090 上生成 TensorRT `.engine` 后直接拿到 RTX 5060 Laptop GPU 使用。
TensorRT engine 与构建时的 GPU 架构、TensorRT/CUDA 版本和配置紧密相关；如后续需要 TensorRT，应在最终
Windows 电脑上根据 `best.pt` 或 ONNX 重新构建。

### 6.16 打包和备份

```bash
RUN=/root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1
EVAL=/root/autodl-tmp/fire-monitoring/runs/yolo11s_dfire_ifire_v1_eval
ART=/root/autodl-tmp/fire-monitoring/artifacts/fire_model_v0.1

mkdir -p "$ART"
cp "$RUN/weights/best.pt" "$ART/"
cp "$RUN/weights/last.pt" "$ART/"
cp "$RUN/weights/best.onnx" "$ART/"
cp "$RUN/results.csv" "$ART/"
cp "$RUN/args.yaml" "$ART/"
cp "$RUN/experiment.json" "$ART/"
cp -r "$EVAL" "$ART/evaluation"
cp /root/autodl-tmp/fire-monitoring/audits/fire_smoke_v1.json "$ART/"
cp /root/autodl-tmp/fire-monitoring/artifacts/environment-freeze.txt "$ART/"
cp /root/autodl-tmp/fire-monitoring/artifacts/nvidia-smi.txt "$ART/"
cp /root/autodl-tmp/fire-monitoring/datasets/processed/fire_smoke_v1/manifest.csv "$ART/"

tar -cf /root/autodl-fs/fire-monitoring-backup/fire_model_v0.1.tar \
  -C /root/autodl-tmp/fire-monitoring/artifacts fire_model_v0.1
sha256sum /root/autodl-fs/fire-monitoring-backup/fire_model_v0.1.tar \
  > /root/autodl-fs/fire-monitoring-backup/fire_model_v0.1.tar.sha256
```

图片、视频和模型本身通常已压缩，AutoDL 也建议用只打包不再压缩的 `.tar`。确认文件存储和 Windows 本地
至少各有一份可打开的归档后，才能释放实例。

## 7. 结果怎么判断

### 7.1 看哪些文件

训练目录中优先看：

- `weights/best.pt`：验证指标最优的权重；
- `weights/last.pt`：断点恢复；
- `results.csv`、`results.png`：各 epoch 的损失和指标；
- `confusion_matrix_normalized.png`：类别混淆；
- `PR_curve.png`、`F1_curve.png`：阈值选择依据；
- `val_batch*_pred.jpg`：模型到底把什么看成火/烟；
- `experiment.json`、`args.yaml`：复现实验。

### 7.2 常见现象

| 现象 | 更可能的原因 | 下一步 |
|---|---|---|
| fire 和 smoke 指标都接近 0 | 路径或标签格式错误 | 检查 YAML、预览和训练 batch |
| 火焰被标成烟雾 | 类别映射反了 | 停止训练，重新准备数据 |
| train 很高、val 很低 | 过拟合或训练/验证分布不同 | 检查泄漏、增强、来源比例 |
| 公开测试高、本地蒸汽误报 | 目标域负样本不足 | 收集困难负样本后小幅微调 |
| 小烟雾漏检 | 目标太小、标签不一致、640 分辨率不足 | 先补小烟雾数据，再比较 960 输入 |
| 4090/5090 利用率低 | 磁盘/CPU 数据加载瓶颈 | 数据放本地盘、调整 workers |
| 第一 epoch OOM | 自动 batch 仍太激进或并发进程占显存 | 降 `--batch 0.60`，检查 `nvidia-smi` |
| loss 变 NaN | 坏标签、数值问题或增强过强 | 停止，审计标签，关闭可疑增强 |

## 8. 第一轮后不要立即做的事

- 不要只凭一张测试图宣布模型完成；
- 不要把验证集当测试集反复调参；
- 不要删除失败图片，只保留好看的演示图；
- 不要为了追求 mAP 把测试图或相邻视频帧放回训练集；
- 不要立刻魔改 YOLO 网络结构；先确认数据和目标域误报瓶颈；
- 不要让云端多模态 API 每帧调用，它应只分析筛选后的候选事件；
- 不要将单帧置信度直接等同于火灾概率或告警等级。

## 9. 下一阶段决策树

完成 v0.1 后按结果决定：

1. **室内 recall 低**：优先扩大 IFireSmoke 类似室内数据和自有目标域样本；
2. **公开集泛化低**：加入 FASDD_CV，保持 D-Fire/IFireSmoke 测试冻结；
3. **小烟雾漏检**：补早期烟雾样本，比较 640 与 960，不先换大模型；
4. **静态干扰误报高**：加入困难负样本；
5. **单帧闪现误报高**：进入单摄 3-of-5/持续时间时序融合；
6. **某一路易被遮挡**：进入双摄决策融合；
7. **定位稳定但风险性质不清**：再接云端多模态 API 做语义研判；
8. **YOLO11s 已稳定**：用完全相同数据和评测流程训练 YOLO26s 做 A/B，而不是换数据后比较。

## 10. 需要记录的实验表

每次训练至少记录：

```text
experiment_id:
date:
git_commit:
dataset_version:
dataset_manifest_sha256:
model_init:
ultralytics_version:
torch_version:
cuda_version:
gpu:
imgsz:
batch:
epochs_completed:
best_epoch:
seed:
combined_map50:
combined_map50_95:
dfire_map50_95:
ifiresmoke_map50_95:
fire_recall:
smoke_recall:
local_negative_video_hours:
false_alarms_per_camera_hour:
known_failures:
artifact_sha256:
```

只有训练参数、数据版本和测试集都固定，模型对比才有意义。

## 11. 参考资料

- D-Fire 数据与下载：https://github.com/gaia-solutions-on-demand/DFireDataset
- D-Fire 论文 DOI：https://doi.org/10.1007/s00521-022-07467-z
- IFireSmoke 论文：https://doi.org/10.1371/journal.pone.0322052
- IFireSmoke 数据：https://huggingface.co/datasets/shahriar-5/IFireSmoke/tree/main
- FASDD 项目：https://github.com/openrsgis/FASDD
- FASDD 论文：https://doi.org/10.1080/10095020.2024.2347922
- FASDD 数据 DOI：https://doi.org/10.57760/sciencedb.j00104.00103
- DetectiumFire：https://arxiv.org/abs/2511.02495
- SmokeBench：https://openaccess.thecvf.com/content/WACV2026/html/Qi_SmokeBench_Evaluating_Multimodal_Large_Language_Models_for_Wildfire_Smoke_Detection_WACV_2026_paper.html
- CaMuViD：https://openaccess.thecvf.com/content/CVPR2025/papers/Daryani_CaMuViD_Calibration-Free_Multi-View_Detection_CVPR_2025_paper.pdf
- YOLO11 文档：https://docs.ultralytics.com/models/yolo11/
- Ultralytics 训练参数：https://docs.ultralytics.com/modes/train/
- Ultralytics 导出参数：https://docs.ultralytics.com/modes/export/
- Ultralytics 许可：https://www.ultralytics.com/license
- AutoDL GPU 选型：https://www.autodl.com/docs/gpu/
- AutoDL 镜像版本：https://www.autodl.com/docs/base_config/
- AutoDL 文件存储：https://www.autodl.com/docs/fs/
- AutoDL 守护进程：https://www.autodl.com/docs/daemon/
- PyTorch Blackwell/CUDA 12.8 支持：https://pytorch.org/blog/pytorch-2-7/

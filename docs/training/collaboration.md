# 模型训练协作

当前目标是提高火焰、烟雾识别的稳定性，尤其关注漏检、水蒸气、强光、屏幕画面等误报。类别固定为 `0: fire`、`1: smoke`。

## 开始

```bash
git clone https://github.com/xsywl945/FireMonitoring.git
cd FireMonitoring
git switch -c train/your-experiment
```

训练脚本在 `ml/scripts/`，完整的数据下载、整理与划分步骤见 [AutoDL 训练说明](../plans/AutoDL-初步火灾识别模型训练说明书.md)。
数据、权重和云端账号由协作成员单独准备；项目中已忽略这些文件。仅修改训练代码不需要运行摄像头、数据库或大模型服务。

AutoDL 环境初始化：

```bash
bash ml/autodl/bootstrap.sh
```

数据审计通过后，使用实际的数据 YAML 路径训练。例如：

```bash
python ml/scripts/train_baseline.py \
  --data /root/autodl-tmp/fire-monitoring/datasets/processed/primary/data.yaml \
  --model yolo11s.pt \
  --project /root/autodl-tmp/fire-monitoring/runs \
  --name your-experiment \
  --epochs 100 --imgsz 640 --seed 42
```

这里的 YAML 路径是示例，需替换为准备脚本实际生成的文件。评估使用 `validate_model.py`，不要用训练集指标代替独立测试结果：

```bash
python ml/scripts/validate_model.py \
  --model /root/autodl-tmp/fire-monitoring/runs/your-experiment/weights/best.pt \
  --data /path/to/test-data.yaml \
  --project /root/autodl-tmp/fire-monitoring/artifacts/your-experiment
```

## 提交结果

将代码改动和一份简短实验记录提交到自己的分支，再向 `main` 发起 Pull Request。实验记录放在 `docs/experiments/日期-实验名.md`，写清楚：

- 代码提交版本、数据来源与版本、训练/验证/测试划分。
- 模型、随机种子、训练参数、GPU 和依赖版本。
- 火焰与烟雾各自的 Precision、Recall、mAP50、mAP50-95，以及独立测试结果。
- 误报和漏检类型，尤其是与上一版在同一测试集上的差异。
- 权重的 SHA-256、文件大小和共享地址；共享文件应确认数据许可及隐私要求。

同一视频或相近帧不要分到训练集和测试集两边。每次训练用不同实验名，保留原结果。
评估报告可以提交；`best.pt`、数据集、摄像头视频和大批预测图片通过约定的文件共享位置交付。

## 运行界面

Windows 运行环境和启动方式见 [项目 README](../../README.md) 与 [Windows 运行说明](../runbooks/windows-demo.md)。
前端支持模拟模式，可以先查看界面；实际摄像头识别需要另行准备模型权重，单纯克隆代码不会自动获得当前模型。

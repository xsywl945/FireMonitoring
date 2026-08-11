# FireMonitoring 训练工具包

本目录用于在 AutoDL 等 Linux GPU 环境中准备火焰/烟雾数据、训练 Ultralytics
YOLO 基线并导出评估结果。首轮模型统一使用两个小写类别：

- `0: fire`
- `1: smoke`

详细操作见：

- [`docs/plans/AutoDL-初步火灾识别模型训练说明书.md`](../docs/plans/AutoDL-初步火灾识别模型训练说明书.md)

主要脚本：

- `check_environment.py`：检查 PyTorch、CUDA、GPU 和磁盘环境。
- `prepare_fire_smoke_v1.py`：合并 D-Fire 与 IFireSmoke，并修正相反的类别编号。
- `audit_yolo_dataset.py`：检查坏图、坏标签、类别统计和数据泄漏。
- `preview_yolo_dataset.py`：生成带框的抽样预览图，人工确认类别没有映射反。
- `build_leakage_safe_primary_split.py`：隔离与验证/测试近似的训练图，生成主训练划分。
- `train_baseline.py`：用固定、可复现的参数训练 YOLO11s 基线。
- `validate_model.py`：分别在合并、D-Fire、IFireSmoke 测试集上评估。

AutoDL 初始化：

- 在 Windows 执行 `powershell -File scripts/New-AutoDLTrainingBundle.ps1` 生成上传包；
- 上传并解压后，在实例执行 `bash ml/autodl/bootstrap.sh`，它会安装固定依赖、
  验证 CUDA，并保存环境和磁盘信息；
- 初始化脚本不包含、读取或保存 SSH/Kaggle 密码。

数据集、权重和训练输出均不提交 Git；仓库根目录的 `.gitignore` 已忽略
`datasets/`、`*.pt`、`*.onnx` 等大文件。

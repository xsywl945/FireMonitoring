# 模型训练协作

更新日期：2026-11-08。YOLO26s 正式训练和微调已完成，Grok 已交付模型与结果，Codex 接管仓库维护。类别固定为 `0: fire`、`1: smoke`。

训练命令、数据划分和评测口径见 [YOLO26s v3 训练](yolo26s-v3.md)，权重、校验值和交付范围见 [训练交接](yolo26s-handoff-2026-11-08.md)。[2026-11-03 协作计划](../plans/单模型高精度训练执行计划-2026-11-03.md)是历史记录，其中 YOLO26m@960 与旧分工已被实际执行的 YOLO26s@640 替代。

## 代码与结果

从最新 `main` 新建短期分支。先用 GitHub Issue 记录具体任务，再提交关联该 Issue 的 PR。代码、评测摘要和参数纳入 Git；模型、数据、私有视频、凭据和完整训练目录保留在 Git 之外。

- `ml/scripts/` 存放数据处理、训练、评测和几何实验代码。
- `docs/experiments/` 存放参数、结果与复现实验所需的精简证据。
- `docs/plans/` 存放研究方案及标明日期的历史计划。
- `docs/project/STATUS.md` 记录当前已完成的工作与未验证的范围。
- `models/` 保存本地交付文件，整目录忽略；归档清单记录相对路径、字节数和 SHA-256。

提交训练结果时写明代码版本、数据清单 hash、实际参数、环境、测试集口径及权重 hash。完整的评测 JSON 和错误样本保存在本地交付目录，可用归档清单核对。每次训练使用独立输出目录，保留原始结果。

`finetune_yolo26s.py` 是根据交付参数重建的脚本，原始云端脚本未交付。参数核对不等于已经重新训练复现。运行方式：

```bash
python ml/scripts/finetune_yolo26s.py /path/to/formal/best.pt /path/to/data.yaml /path/to/new-project
```

评测使用 `validate_model.py`。阈值只用验证集选择，测试集只用于报告；同一视频或近似帧不能跨训练与测试划分。

## 运行

部署操作见 [项目 README](../../README.md)。克隆仓库不会下载模型。在线服务使用的权重路径是 `models/yolo26s-ft-2026-11-04/best.pt`，阈值在 `config.json`。修改训练工具不需要启动摄像头、数据库或水泵。

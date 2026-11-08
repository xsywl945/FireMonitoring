# 项目状态

更新日期：2026-11-08。项目维护由 Codex 接管，工作记录见 [Issue #2](https://github.com/xsywl945/FireMonitoring/issues/2)，训练交付见 [PR #1](https://github.com/xsywl945/FireMonitoring/pull/1)。

YOLO26s@640 正式训练及低学习率微调已完成。Grok 交付文件已接收，微调 PT、微调 ONNX 和正式 PT 的 SHA-256 与交接记录一致。交接和文件位置见 [训练交接](../training/yolo26s-handoff-2026-11-08.md)，完整本地文件清单见 [归档清单](../../data/training-archive/2026-11-03-yolo26s-v3/ARCHIVE-MANIFEST.json)。

| 同一测试集 | YOLO11s 基线 | YOLO26s 正式 | YOLO26s 微调 |
|---|---:|---:|---:|
| D-Fire mAP50 | 0.745 | 0.733 | 0.731 |
| D-Fire mAP50-95 | 0.432 | 0.428 | 0.419 |
| COCO 背景误报图片数，confidence 0.25 | 39/334 | 10/334 | 6/334 |

这些指标来自交付的评测文件，本次未重新运行模型评测。微调减少了这组背景图片的误报，D-Fire mAP 同时下降，不能声称全面提高精度。IFireSmoke 测试集只有 6 张，不能证明该来源的泛化能力。

推理服务尚未切换到新权重。最后记录的实机模式为 2026-10-18 的本地 YOLO 火焰时序识别、一只 USB 摄像头及 ESP32 控制，大模型调用关闭；本次未重新启动设备或确认接线、设备编号。操作见 [本地识别与 BOOT](../runbooks/local-yolo-boot.md)。

四摄代码已实现当前控制点标定和稳健三维求解，输入需要米制控制点及同一源点的二维观测。它仍是几何研究基线，未接入原始四路视频、自动地图匹配或 YOLO 源点预测。方案、推导与合成实验条件见 [四摄研究方案](../plans/后续四摄算法方案-YOLO26s.md)。真实四摄精度和速度未测，没有支持世界先进水平的对照结果。

文档入口：

- [训练流程](../training/yolo26s-v3.md)和[协作规则](../training/collaboration.md)。
- [YOLO26s 评测证据](../experiments/2026-11-04-yolo26s/metrics.json)和[四摄合成实验数据](../experiments/2026-11-08-variable-layout.json)。
- [YOLO11s 历史训练记录](YOLO11s-初步模型训练结果.md)和[自动喷水验证记录](automatic-suppression-validation.md)。

历史里程碑保留在 Git 历史及对应实验文档中。当前状态以本文件为准，旧计划不作为已实现功能或当前操作指令。

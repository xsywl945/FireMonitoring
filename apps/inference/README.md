# 推理库

后端用到的算法和设备协议放在这个包里，不再单独起一个推理服务。

- `temporal.py`：每路每类的 N/M 时序确认。
- `localization.py`、`multiview_geometry.py`：2 到 4 路已有观测的几何定位，不再重新跑检测。
- `vision/qwen.py`：千问视觉研判。
- `pump.py`：主机侧水泵策略。串口报文在 `actuator_v2.py`，模拟设备和串口客户端共用它。报警节点在 `panel_v2.py`。
- `detectors/ultralytics_adapter.py`：YOLO 适配器。可选依赖是 `fire-monitoring-inference[yolo]`。

安装：

```powershell
python -m pip install -e apps/inference
```

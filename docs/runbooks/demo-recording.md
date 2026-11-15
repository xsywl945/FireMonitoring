# 演示录像

比赛现场不点火、不依赖网络。演示模式播放一组四路同步录像，检测、定位、研判和灭火状态机仍走线上同一套代码，只是输入换成录像，硬件换成模拟设备或现场串口。

页面上会一直有「演示模式」。回放画面标成「回放」，不要把它说成实况。用了缓存的千问结果时，页面写「缓存结果」。

## 仓库里的示例

`data/demo/synthetic-classroom` 是合成数据：虚拟教室、四个虚拟相机，火焰是按同一个三维点投影的程序精灵，尺寸随 t² 增长，喷水后缩小消失。检测框由投影几何生成，不是 YOLO 的输出。千问缓存是手写的合成响应。包里的 `SYNTHETIC.txt` 和 `manifest.json` 都写了这一点。

三个剧本：

- `full`：正常、疑似、确认、研判、瞄准、待喷、喷射、复核、扑灭，大约 60 秒
- `electrical`：配电箱起火，禁止用水，推荐二氧化碳并断电
- `person`：火点旁有人，不喷水

在 `config.json` 里打开：

```json
"demo": {
  "enabled": true,
  "pack": "data/demo/synthetic-classroom",
  "hardware": "sim",
  "pump_run": true,
  "detector": "replay"
}
```

`hardware` 用 `sim` 时，主机侧模拟执行节点和报警节点。改成 `serial` 就是录像输入加真实串口，水泵和报警节点沿用原来的串口配置。`pump_run` 设为 `false` 时只转云台、开激光，不发 `RUN`，页面显示「水泵已禁用」。

`detector` 用 `replay` 时从检测框文件取框，不加载模型。改成 `model` 才对录像跑 YOLO。

管理员在数据大屏上点剧本名称开始，点重置回到监视。待喷是 3 秒，喷射是 5 秒，复核后火焰消失再满 3 秒记为扑灭。示例录像按这组时间生成，改这三项之前要重新做录像。

重新生成示例包：

```bash
PYTHONPATH=apps/server/src:apps/inference/src python -m fire_monitoring.demo.synthesize
```

## 自己在实验室录

四路相机先按 [标定](calibration.md) 做完内参和控制点。教室、云台位置和四路外参确定之后再录，录的时候不要改机位。

1. 四路同时开始。用同一套时间基准，在 `manifest.json` 里给每路写 `time_offset_ms`，表示这一路相对主时钟提前多少毫秒。偏移要落在定位窗口里，示例是 0、40、80、120。
2. 分辨率和帧率四路一致，写进 `width`、`height`、`fps`。时间从 0 起，按帧号对齐。
3. 目录沿用示例包：`videos/<剧本>-<相机>.mp4`、`detections/<剧本>.json`、`qwen/<剧本>.json`，相机字段和示例里的 `cameras` 一样，控制点用这次标定的结果。

检测框文件是一个 JSON：

```json
{
  "synthetic": false,
  "fps": 8,
  "frames": [
    {
      "t": 0.0,
      "cameras": {
        "nw": [
          {"class_name": "fire", "confidence": 0.91, "bbox": [0, 0, 10, 20]}
        ]
      },
      "persons": []
    }
  ]
}
```

`bbox` 是像素 `x1,y1,x2,y2`。`persons` 是这一帧里人的地面坐标，单位米，只在需要触发避让时填写。有 GPU 时可以离线跑仓库里的 YOLO，把每帧最大的火框和烟框写进去；没有 GPU 就用 `detector: replay` 读这份文件。类别只写 `fire`、`smoke`，人不要写进 `cameras`，状态机认的是 `persons` 里的坐标。

千问缓存和在线接口用同一份证据结构，字段用下划线：`burning_objects`、`suspected_cause`、`energized_equipment`、`person_count`、`scene_type`、`smoke_density` 等。文件里写上 `note`。手写或合成的响应要设 `synthetic: true` 和 `handwritten: true`，页面会标明。有网络且缓存文件还在时，演示仍用缓存，避免现场断网时结论变掉。

录完用示例包的 `manifest.json` 当模板，换掉视频、检测框、缓存和标定。`fire_xyz` 只给验收看，播放时火点位置仍由定位程序算出来。

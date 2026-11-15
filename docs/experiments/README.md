# 实验

这些脚本只做计算和画图。输入文件不存在就退出，不会补一组数冒充结果。仓库里能直接跑完的，是合成数据或固定假响应；图和 JSON 里会写明。

中文用本机的 Droid Sans Fallback，拉丁字母和数字用 DejaVu Sans。没有 Droid Sans Fallback 时改用仓库里的文泉驿微米黑，告警 PDF 也是这套字。

受控小火要先得到保卫处批准，现场备好灭火器，并有人监护。脚本不会替你做这些。

## 定位误差

比较卷尺真值（或录像回放时已知的三维点）和系统输出、三角化结果。输出全体以及按点位、按参与相机数分组的均值、P90 和最大误差。

CSV 表头：

```text
point_id,camera_count,truth_x_m,truth_y_m,truth_z_m,est_x_m,est_y_m,est_z_m
```

坐标单位是米。`camera_count` 至少为 2。

```bash
python -m experiments.localization_error --csv 测量.csv --out docs/experiments/日期-localization
python -m experiments.localization_error --synthetic --out docs/experiments/2026-11-15-localization
```

`--synthetic` 用 `triangulate` 在已知点上加像素噪声，把生成的表写到输出目录的 `input.csv`，再算误差。图和 JSON 标明合成数据。

输出 `result.json`、`error-by-cameras.png` 和同名 SVG。

现场：在教室里用卷尺定一组点，记下世界坐标、当时参与定位的相机数，以及系统给出的 `xyz`。录像回放时也可以把合成或标定已知点写成同一张表。不要为了凑数点火。

## 云台自标定和弹道补偿

比较三种命中误差：只用人工测量的云台位姿并按视线瞄准、激光自标定后仍按视线瞄准、自标定后再做弹道补偿。收敛曲线是角度组数和误差的关系。运动学、`fit_gimbal` 和弹道积分都用 `apps/inference` 里已有的实现。

合成数据：

```bash
python -m experiments.gimbal_ballistics --synthetic --out docs/experiments/2026-11-15-gimbal-ballistics
```

实测需要三份输入。落点表：

```text
method,x_m,y_m,z_m,landing_x_m,landing_y_m,landing_z_m
```

`method` 只能是 `manual`、`self_cal`、`ballistic`。激光表：

```text
pan_cdeg,tilt_cdeg,x_m,y_m,z_m
```

至少 12 行。`--manual` 是 `GimbalParams.to_dict()` 的 JSON，当作拟合初值。

```bash
python -m experiments.gimbal_ballistics \
  --landings 落点.csv --laser 激光.csv --manual 人工位姿.json \
  --out docs/experiments/日期-gimbal-ballistics
```

合成结果里的收敛曲线是弹道补偿后的命中误差。实测曲线是激光残差，JSON 里写了这一点，两套数不能当成同一个量。

输出 `result.json`、`hit-error.png`、`convergence.png` 以及对应的 SVG。

现场：先按安装记录填写人工位姿。用激光在不同云台角度打到已知坐标，每组记 pan、tilt 和落点。试射时分别记录三种方式的弹着点。出水试射同样要批准、灭火器和监护。

## 可信喷射

在可变布局的合成定位上加喷射覆盖。三种方式：对准估计点喷一次、按固定协方差扫射、按该次定位协方差用已有的 `zigzag` 扫射。半径内算命中。同时给出名义覆盖概率和实际命中率的分箱曲线。名义概率用现有的 `cover_probability`，扫射用协方差抽样估计并集。

状态机里已经有「覆盖概率低于 `cover_threshold` 时不直接喷，先按协方差扫」的判据，配置项是 `suppression.cover_threshold`。这次没有再写一套。

```bash
python -m experiments.trusted_spray --trials 16 --out docs/experiments/2026-11-15-trusted-spray
```

这是合成数据，不是现场喷水。输出 `result.json`、`hit-rate.png`、`calibration.png` 和 SVG。

现场如果要核对照，只能在批准后的受控小火上做，记录估计坐标、协方差、实际着火点和是否打中。用水时长和首次命中时间按水泵日志算，再写成脚本能读的表之前，不要把合成图当成现场结果。

## 延迟分解

事件表每一行是一轮里的一个阶段。阶段依次是 `capture`、`detect`、`confirm`、`localize`、`aim`、`spray`。时间倒退就退出。

```text
trial,stage,t_s
```

也接受同样字段的 JSON 数组。

```bash
python -m experiments.latency_breakdown --events 事件.csv --out docs/experiments/日期-latency
PYTHONPATH=apps/server/src:apps/inference/src \
  python -m experiments.latency_breakdown --demo --script full \
  --out docs/experiments/2026-11-15-latency
```

`--demo` 播放 P7 合成包里的 `full` 剧本。堆叠图用剧本时钟：采集是 0，检测是检测文件里第一次出现火或烟的时刻，确认、定位、瞄准、出水是对应事件发布时的剧本时间。确认和定位发生在同一帧，这段可以是 0。同一次播放的墙钟在 `wall_clock_s`，定位耗时看这里。示例包是合成数据。

一轮剧本只有一组时间，分位数就等于这组时长。多轮 CSV 才会拉开 P50 和 P90。

输出 `events.csv`（演示模式）、`result.json`、`latency-stack.png` 和 SVG。

现场：从告警事件表或日志里整理成上面的表。采集、检测时间如果日志里没有，就不要估一个数填进去。

## 千问评测

清单：

```text
path,label,scene
```

`scene` 可以省略，省略时按教室。`label` 为 A、B、C、D、E、F 或 `误报`。

两种做法。直接询问让模型返回类别和灭火剂。证据加规则沿用 `fire-evidence-v4`，类别由 `classify` 和 `config/fire_rules.json` 决定。规则表目前没有从画面证据单独推出 C 类的条目，这类样本会记成类别错误。

不安全建议指真实类别是 E、F、B、D 时仍建议用水或直流水。误报率的分母是标成误报的样本，漏报率的分母是其余样本。没有单价时费用是 null，不填一个市价。

```bash
python -m experiments.qwen_eval \
  --manifest experiments/examples/qwen_manifest.csv \
  --fixtures experiments/examples/qwen_fixtures.json \
  --out docs/experiments/2026-11-15-qwen-fixture
```

真实调用只在本机手动跑。密钥读 `config.json` 的 `llm.api_key`，程序不打印它。图片路径相对清单所在目录。

```bash
python -m experiments.qwen_eval \
  --manifest 标注.csv --live --config config.json \
  --price-per-million 0 \
  --out /tmp/qwen-eval
```

不要把真实调用的 `result.json` 提交进仓库。`docs/experiments/2026-11-15-qwen-fixture` 只是固定假响应，用来确认脚本和规则表接得上，不是评测结论。

## NIST 热释放速率

读 1 秒间隔的热释放 CSV，以及火焰高度序列。高度序列表头为 `time_s,height_m`，可以带 `diameter_m`，否则用 `--diameter-m`。NIST 导出的表认 `Time (s)` 和 `Heat Release Rate (kW)`。热释放用现有的 Heskestad 公式从火焰高度和直径反算，增长档位和到达阈值的时间用现有的 t² 拟合。序列后段如果在衰减，拟合用上升最陡的 20 秒，再交给原来的函数。

```bash
python -m experiments.nist_hrr --synthetic --out docs/experiments/2026-11-15-nist-hrr
python -m experiments.nist_hrr --hrr 试验.csv --flames 火焰.csv --diameter-m 0.30 \
  --out docs/experiments/日期-nist-hrr
```

也可以对裁剪后的视频量高度：`--video 火焰.mp4 --px-per-m 像素每米 --diameter-m 池径`。画面里要只有火焰，亮区从下到上的跨度除以 `px-per-m`。NIST 页面上带热释放曲线的延时视频不能直接拿来量。

没有热释放文件、也没有 `--synthetic` 时退出。数据不要放进 git。有视频的试验和下载方式见 [nist-fcd.md](nist-fcd.md)。

输出 `result.json`、`hrr.png` 和 SVG。JSON 不重复存放整条曲线，曲线在图里。

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

三组都用 `solve_aim` 反解，不再按视线把喷嘴对准目标：

- 人工卷尺位姿，加上测量噪声，再用配置里的名义速度和阻力。
- 激光自标定得到的位姿，仍用名义速度和阻力。
- 激光自标定的位姿，加上试喷落距拟合出的速度和阻力。

上一版里自标定的命中误差比人工位姿更大（0.74 m 对 0.64 m）。那两组都按视线瞄准，没有弹道。自标定把射线对准目标之后，重力造成的落差全部变成脱靶；人工位姿的仰角偏差有时反而补上一点。不是自标定把位姿标坏了。

生成和反解不是同一个无噪声模型。生成用 `integrate` 的二次阻力，阻力系数是名义值的 2 倍，每次出水还有速度抖动，落点再加射流破碎。反解只用系统的 `solve_aim` 和 `fit_drag`。激光点坐标带三角化噪声，执行角度带步距取整和回差。8 个随机种子。图上的误差棒是种子间标准差。JSON 里有均值、P90 和最大值。

参数和取值依据：

| 参数 | 取值 | 依据 |
|---|---|---|
| 人工位置噪声 | 标准差 0.015 m | 约 95% 在 ±3 cm，按卷尺量安装点 |
| 人工角度噪声 | 标准差 1° | 约 95% 在 ±2°，加在三个安装角上 |
| 三角化噪声 | 标准差 0.016 m | `landmark_sigma_px` 为 2，演示相机焦距 430 px，约 3.5 m 处 2/430×3.5 |
| 舵机步距 | 0.01° | `NOMINAL_SCALE` |
| 回差 | ±0.2° | 协议里没有回差，按小型云台齿轮间隙取的固定值 |
| 名义弹道 | 10 m/s，阻力 0.05 | `config.example.json` 的 `suppression.speed` 和 `drag` |
| 生成阻力 | 0.10 | 名义阻力的 2 倍。0.05 不是辨识结果 |
| 出口速度抖动 | 相对标准差 2.5% | 仓库没有压力记录。压力脉动约 5% 时，速度按平方根变化 |
| 射流破碎 | 横侧、竖直各 0.02 m | 二次阻力模型没有这项。仓库没有射流宽度，没有按图改这个数 |
| 试喷俯仰 | 12°、20°、28°、36° | 让落距回到枪口高度，供 `fit_drag` 使用 |

这些数先写死再跑。8 个种子的均值：人工加名义弹道 0.123 m（标准差 0.064 m），自标定加名义弹道 0.110 m（标准差 0.028 m），自标定加试喷弹道 0.046 m（标准差 0.020 m）。自标定没有比人工位姿更差；名义阻力本身是错的，所以前两组的均值接近，自标定主要收紧了种子之间的离散。试喷拟合把阻力从 0.05 拉向生成用的 0.10，误差降到大约 5 cm，不再是无噪声时的 3 mm。收敛曲线从 12 组到 36 组都在 0.05 m 附近，因为 12 组已经把位姿收住，剩下的是速度抖动、破碎和拟合残差。

```bash
python -m experiments.gimbal_ballistics --synthetic --out docs/experiments/2026-11-15-gimbal-ballistics-noise
```

实测落点表：

```text
method,x_m,y_m,z_m,landing_x_m,landing_y_m,landing_z_m
```

`method` 为 `manual`、`self_cal`、`fitted`。激光表：

```text
pan_cdeg,tilt_cdeg,x_m,y_m,z_m
```

至少 12 行。`--manual` 是 `GimbalParams.to_dict()` 的 JSON。实测收敛曲线仍是激光残差，不是弹着点误差。

```bash
python -m experiments.gimbal_ballistics \
  --landings 落点.csv --laser 激光.csv --manual 人工位姿.json \
  --out docs/experiments/日期-gimbal-ballistics
```

输出 `result.json`、`hit-error.png`、`convergence.png` 以及对应的 SVG。

现场：卷尺量云台安装点和三个安装角。激光在不同命令角度打到可三角化的点，记下命令角度和点坐标。试喷用几个俯仰角，量落距。出水试射要批准、灭火器和监护。

## 可信喷射

比较四条路径，喷水半径 0.2 m，定位标准差从 0.05 m 扫到 0.80 m。火点相对估计点按这个协方差抽取。

- 固定点：只喷估计点。
- 固定水平扫射：原来的 `zigzag`，水平标准差固定 0.3 m，不看这次的协方差。
- 协方差二维扫射：把定位协方差投到水平落点平面上，沿主轴铺 2σ 椭圆的蛇形路径。没有用水上限。
- 二维扫射加拒喷：同一条路径，但落点数不得超过 3。单次喷射是 5 s，最多修正 2 次，所以 `max_water_s` 取 15。铺得下、并且路径的名义覆盖概率不低于 `cover_threshold`（0.5）才喷；否则停在已确认，继续观察。

0.05 m 时四条都打中，各喷 1 个点。从 0.10 m 起，2σ 椭圆超过 3 个点，拒喷比例变成 1，用水是 0，不再出现以前那种把水打到 17 s 的情况。没有上限的二维扫射在 0.20 m 用 16 个点，名义覆盖概率 0.59，命中率 0.58；门限仍然拒喷，因为 16 个点超出用水上限。标准差到 0.80 m 时，这条无上限路径要 256 s，命中率只有 0.19，竖直误差仍然落在落点平面外面。固定水平扫射的用水一直是 7 s，命中率随标准差下降。名义覆盖概率和实测命中率大体沿对角线，拒喷的那些次不放进校准曲线。

这些阈值没有按图改过。

```bash
python -m experiments.trusted_spray --draws 80 --out docs/experiments/2026-11-15-trusted-spray-sigma
```

这是合成数据。输出 `result.json`、`sigma-sweep.png`、`calibration.png` 和对应的 SVG。命中率的误差棒是二项标准误。

现场如果要核对照，只能在批准后的受控小火上做，记录估计坐标、协方差、实际着火点和是否打中。用水时长按水泵日志算。

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

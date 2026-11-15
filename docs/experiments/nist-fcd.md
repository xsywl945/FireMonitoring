# NIST Fire Calorimetry Database

热释放对比脚本不下载数据，也不把数据放进仓库。下面四组是 2026-11-15 打开试验页后核对过的：页面里有 `video/mp4`，文件地址返回 200 和 `video/mp4`，热释放 CSV 的时间列是 1 秒一格。没有逐帧看完录像。

页面上的视频是叠了热释放曲线的延时片，不能直接交给 `--video`。要用的话先裁出火焰，或者自己从画面里把高度写成 `time_s,height_m`。池径取试验页上的燃烧器尺寸，单位米，用 `--diameter-m` 传入。

| 试验 | 试验页 | 视频 | 热释放 CSV | 池径 |
|---|---|---|---|---|
| Ethanol_2 | https://www.nist.gov/el/fcd/structure-medium-scale-pool-fires/ethanol2 | https://nist-el-nfrlhrr.s3.amazonaws.com/HRR/ASSET_FILES/PoolFire/video/1581697413.mp4 | https://www.nist.gov/fcd-s3?path=/HRR/ASSET_FILES/PoolFire/data/1581697413_Ethanol_2.csv | 0.30 m，30 cm 圆盘 |
| Acetone_02 | https://www.nist.gov/el/fcd/structure-medium-scale-pool-fires/acetone02 | https://nist-el-nfrlhrr.s3.amazonaws.com/HRR/ASSET_FILES/Liquid_Pool_Fires/video/1681411265.mp4 | https://www.nist.gov/fcd-s3?path=/HRR/ASSET_FILES/Liquid_Pool_Fires/data/1681411265_Acetone_02.csv | 0.30 m，30 cm 圆盘 |
| Heptane_2 | https://www.nist.gov/el/fcd/structure-medium-scale-pool-fires/heptane2 | https://nist-el-nfrlhrr.s3.amazonaws.com/HRR/ASSET_FILES/PoolFire/video/1583260586.mp4 | https://www.nist.gov/fcd-s3?path=/HRR/ASSET_FILES/PoolFire/data/1583260586_Heptane_2.csv | 0.30 m，30 cm 圆盘 |
| propane_gas_burner14 | https://www.nist.gov/el/fcd/structure-medium-scale-pool-fires/propanegasburner14 | https://nist-el-nfrlhrr.s3.amazonaws.com/HRR/ASSET_FILES/Poolfires/video/1637261396.mp4 | https://www.nist.gov/fcd-s3?path=/HRR/ASSET_FILES/Poolfires/data/1637261396_propane_gas_burner14.csv | 0.37 m，37 cm 烧结金属圆盘 |

数据库入口是 https://www.nist.gov/el/fcd 。乙醇那份 CSV 的表头是 `Time (s),Heat Release Rate (kW),...`，脚本认前两列。

Heskestad 关系用于池火的火焰高度。上面四组都是中等尺度池火，适合拿来对照；它们多数时间接近稳态，t² 拟合会在找不到上升段时退出。那是输入不满足现有拟合的条件，不是脚本补出来的档位。仓库里的合成例子是一条超快速 t² 曲线，用来检查公式前后一致，见 `2026-11-15-nist-hrr`。

# `templates/` — 設計側のひな形

| ファイル | 用途 |
|---|---|
| `config_example_i2c.py` | `TR-1um_I2C_2026/scripts/pnr/i2c_config.py` をそのまま。設計固有の `config.py` を書くときの参照 |
| `build.sh` | RTL → 配置配線用ネットリストの段構成。`TOP` / `SRC` / `ROWS` / `LIB` / `BUFTH_NETS` / `CLK_NETS` / `ROW_ASSIGNMENT` を環境変数で受ける |
| `run_tests.sh` | RTL / NET / PNR の 3 ビューに同一 TB を流す |

## 設計側の `config.py` に書くもの

```python
from apr.config_base import *

TOP_CELL_NAME     = "…_core"           # 配置配線するコアセル
CHIP_TOP_CELL     = "tr_1um_<user>_…"  # MPW の命名規約
NET_PATH          = "out/….v"
STDCELL           = "v59_4"
N_ROWS            = 2
CORE_WIDTH_TRACKS = 299                # × 5.4 = 1614.6 µm
CH_HEIGHTS        = [...]              # 長さ = N_ROWS + 1、上下端は 5.4 の倍数
PAD_MAP           = {...}              # ★ 現状は gen_top_routing_plan.py に直書き
PER_ROW_LOCAL_NETS = {...}
BUFTH_NETS        = [...]
CLK_NETS          = [...]
NO_BOTTOM_PORTS   = 0
DOWN_FACING_INSTS = set()
```

これ以外は `apr/config_base.py` の既定値とそこからの導出で決まる
（`docs/03_core_geometry.md` §1）。

## 設計側に残すもの

`hdl/` `out/` `layout/` `src/` `info.yaml` `docs/info.md` `design_notes.md` `.github/`

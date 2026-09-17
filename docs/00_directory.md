# TR-1um_APRtools ディレクトリ構成案

作成: 2026-09-14 / 更新: 2026-09-15 / 状態: **第 1 段階まで実施済み**（`docs/05_migration_log.md`）

## 0. 前提として決まっていること

| 項目 | 決定 |
|---|---|
| 各設計からの参照方法 | **git submodule**（`tools/APRtools/` として取り込む） |
| P&R スクリプトの正本 | **TR-1um_I2C_2026 の `scripts/pnr/` 世代**（2026-09-14、最新） |
| 薄皮 `spi_config.py` | **廃止**。設定モジュール名を中立化し、`TD4_*` 環境変数は `APR_*` に統一 |
| STDCELL の版 | **v59_4（行高 59.4）を正本**に決定。v64_8 は `legacy` 扱いで凍結 |
| コア幅 | **トラックピッチ 5.4 µm の整数倍でパラメータ化**（`CORE_WIDTH_TRACKS`）。詳細は `docs/03_core_geometry.md` |
| 電源ピン名 | **`vdd` / `vss`（小文字）に統一**。フレーム側の `VDD`/`VSS` は変更不可 |
| `*` | **剥がす**（モジュール名・JSON 名・トップセル名）。`legacy/` は改名しない |
| `TD4_*` 環境変数 | **`APR_*` に統一**し、`cfg.getenv()` 経由に集約 |
| `legacy/` | **APRtools に同梱**（別リポジトリにしない） |
| `pre_check.py` の `FRAME_CELL_NAMES` | **MPW テンプレート上流に PR を出す**（`OSS_FRAME_GIO` 追加）。それまでは改名で回避 |

## 1. 構成案

```
TR-1um_APRtools/
├── README.md
├── CHANGELOG.md
│
├── apr/                       ── P&R エンジン本体（Python パッケージ）
│   ├── __init__.py
│   ├── rules.py               ★ DRC 値・レイヤ番号・グリッドの単一ソース
│   ├── config_base.py         既定値 + check() フレームワーク（旧 *_config.py の共通部）
│   ├── io/                    lef_parser / netlist_parser / netlist_util /
│   │                          gen_placement_json / read_info
│   ├── netlist/               dedup_gates / merge_muxdffrb / insert_bufth /
│   │                          insert_row_buffers / mem_wrap / gen_liberty
│   ├── place/                 place.py(step1-4) / verify_placement /
│   │                          sweep_seed / sweep_height / explore_rows
│   ├── route/                 route.py(step5-11) / route_channels /
│   │                          ripup_reroute_shorts / route_top_pins /
│   │                          add_power_pins / squeeze_channels /
│   │                          compress_channels / connect_macro_power /
│   │                          highlight_top_pins / detect_loops_jogs
│   ├── chip/                  assemble_top / gen_top_routing_plan / route_chip /
│   │                          add_top_pins / place_logo / frame_pins /
│   │                          check_top_channels / check_chip / verify_chip /
│   │                          place_ring_osc
│   ├── verify/                drc_check_cells / drc_check / drc_pdk /
│   │                          verify_connectivity{,_m1m2} /
│   │                          verify_port_connectivity / lvs_pnr / lvs_pdk /
│   │                          klayout_extract / netcmp / label_check /
│   │                          pin_grid_check / sync_cell_info
│   ├── sim/                   mklvsnet / mkchipnet / mkringoscnet /
│   │                          gen_chip_tb / gen_chip_sim_ready /
│   │                          gen_sim_from_extracted / check_chip_sim /
│   │                          frame2sim / mkframespice / spi2ngspice / spi2sim /
│   │                          gen_irsim_cmd / check_irsim_log
│   ├── export/                export_mpw / pre_check
│   └── plot/                  plot_layout / plot_placement / plot_chip_floorplan /
│                              plot_chip_routing / plot_corridors
│
├── syn/                       ── 合成・STA（設計非依存部）
│   ├── syn.sh                 段構成を環境変数で受ける版
│   ├── synth.ys.in            @TOP@ / @LIB@ / @SRC@ 置換テンプレート
│   ├── abc.constr  tr1um.genlib
│   ├── syn_report.py  cmp_cells.py  area_estimate.py  area_custom.py
│   │                  cellinfo.py  gate_count.py  block_report.py
│   └── sta/                   setup.tcl / report.tcl / path.tcl / sta.sh
│
├── char/                      ── セル特性化（現 scripts/char をそのまま）
│   ├── loadext cellspec charlib char_comb char_seq char_latch char_mem char_pad
│   ├── calib_cap genjobs runjobs.sh collect mklib verify_lib mkcellverilog mkmemsrc
│   └── models/  decks/  pack/
│
├── pdk/                       ── ★ データは置かない。参照方針だけ
│   └── README.md              TR1UM_PDK の解決順、コピー禁止対象、派生物の再生成コマンド
│
├── art/                       ── 自作の図版
│   └── opensusi_logo.txt      317 × 63 セル / 5,785 ドット（コメント文字は %）
│
├── stdcell/                   ── セルライブラリ（版で切る）
│   ├── v59_4/                 ★正本（TD4 / APR_2026 世代）
│   │   ├── TR-1um_STDCELL.gds  TR-1um_cells.lef  TR-1um_tech.lef
│   │   ├── cell_info.json
│   │   ├── simulation/*.spice   extracted/*.extracted
│   │   └── tr1um_typ_5v0_25c.lib
│   ├── v64_8/                 SCLK_SPI 世代・凍結（既提出 GDS の再現用のみ）
│   └── CELLS.md               セル一覧 / 不足セル / 追加提案
│
├── macro/                     ── 設計間で共有する再利用マクロ
│   ├── regfile/               mkspice.py / mkmemport.py / mem_array_estimate.py
│   │                          （TLAT → REG4x16 / REG8x16 → MEMPORT）
│   └── ringosc/               RING_OSC.gds / .lef / .sch / INV3D.*
│
├── templates/                 ── 新規設計のひな形
│   ├── config.py.in           設計固有の設定だけを書く雛形
│   ├── build.sh  run_tests.sh
│   ├── info.yaml.in
│   └── github/                .github/workflows/check.yml など
│
├── docs/                      ★知見の集約先
│   ├── 00_directory.md            この文書
│   ├── 01_inventory.md            3 リポジトリの資産棚卸しと移行対応表
│   ├── 02_stdcell_diff.md         STDCELL 2 世代の差分調査
│   ├── 03_core_geometry.md        コア幅のパラメータ化と TAP 列の制約
│   ├── 04_naming.md               命名の正規化計画（電源ピン名 / nrow_fm / APR_*）
│   ├── 10_pdk_facts.md            プロセス事実（訂正履歴込み）
│   ├── 11_frame_io.md             パッド・電源・GIO・ロゴ
│   ├── 12_stdcell.md              グリッド・行高・FILL/TAP・不足セル
│   ├── 20_flow_syn.md             合成 → STA
│   ├── 21_flow_place.md           step1-4
│   ├── 22_flow_route.md           step5-11
│   ├── 23_flow_chip.md            チップ組み立て
│   ├── 30_verify_drc_lvs.md
│   ├── 31_verify_ngspice.md
│   ├── 05_migration_log.md        データ移動の記録
│   ├── 40_gotchas.md          ★ 踏んだ穴集（設計非依存）
│   ├── 50_char.md
│   ├── 90_improvement_notes.md ★ 技術的負債の台帳（U1–U82。残りは §7-2）
│   └── 91_decisions.md        ★ 決定事項 1〜23（コードが引く「決定 N」の出典）
│
└── legacy/                    ── 移植原本（read-only・履歴保存・★改名しない）
    ├── async_i2c/             TR-1um_Async_I2C/script/ の原本
    ├── sclk_spi/              TR-1um_SCLK_SPI/scripts/i2c_ref/ + port_i2c_scripts.py
    │                          + port_rules.py + PORTING.md
    ├── i2c_2026/             scripts/pnr/from_async_i2c/
    └── PORTING_HISTORY.md     I2C → SPI → TD4 → APR_2026 の移植ログ
```

## 2. 設計リポジトリ側の姿

```
TR-1um_SCLK_SPI/               （再設計後）
├── tools/APRtools/            ← submodule（版を固定）
├── config.py                  ← 設計固有のみ（下記）
├── hdl/                       RTL とテストベンチ
├── out/                       合成出力
├── layout/                    step1..step11 / chip / simulation
├── docs/                      info.md / pin_list.md / cell_usage.md
├── src/                       MPW 提出物
├── info.yaml
├── design_notes.md            ← この設計の記録（引き続きここ）
└── .github/
```

`config.py` に書くのは**これだけ**にする（現状散っているものを寄せる）:

```python
from apr.config_base import *          # 既定値
TOP_CELL_NAME = "spi_slave_sclk"
CHIP_TOP_CELL = "tr_1um_3wire_SPI"
NET_PATH      = "layout/spi_slave_sclk_net_pnr.v"
STDCELL       = "v59_4"
N_ROWS        = 2
CORE_WIDTH_TRACKS = 299                # × 5.4 = 1614.6 µm
CH_HEIGHTS    = [...]
PAD_MAP       = {...}                  # ← 現在 gen_top_routing_plan.py に直書き
PER_ROW_LOCAL_NETS = {...}
BUFTH_NETS    = [...]
CLK_NETS      = [...]
```

## 3. 「共通／設計固有」の境界（4 層モデル）

| 層 | 置き場所 | 内容 |
|---|---|---|
| **プロセス** | `apr/rules.py` `docs/10_pdk_facts.md` | レイヤ番号、DRC 値、via_1 PCell、M1=水平/M2=垂直、トラックピッチ 5.4 の導出、ngspice 変換ルール |
| **セルライブラリ** | `stdcell/vXX/` `apr/rules.py` | 行高、サイト 5.4、TAP ピッチ 534.6、FILL 寸法、prBoundary はみ出し（x+12.6 / y+4.0）、電源ピン名 |
| **フレーム** | `pdk/frame/` | リング半径 920 / 921.7、レーン定数、電源バス・ライザ・脚・ストリップ、パッド極性、自前 PTECT 3 隅、ボンドパッド LVS ピン規約、ロゴ |
| **設計** | 各リポジトリ `config.py` | トップセル名 2 つ、RTL/NET パス、行数、チャネル予算、`PAD_MAP`、名指しネット、TB |

現状これらが混ざっている代表例:

- `route_chip.py` に**フレーム幾何の定数が 30 個以上ベタ書き**（`LANE_R0` / リング半径 / バス y / ストリップ / `RO_*`）
- `LANE_R0 = 847.0` は「コア端 816.3 の 30.7 µm 外」＝ **コア幅 1620 固定に依存**
- DRC 値が `drc_check.py` / `check_chip.py` / `drc_check_cells.py` / `place_logo.py` の
  **4 箇所に散在し、しかも `drc_check_cells.py` だけ値が違う**（下記）

| ファイル | M1 幅/間隔 | M2 幅/間隔 | V1 間隔 |
|---|---|---|---|
| `drc_check.py` | 1.8 / 1.4 | 3.0 / 2.0 | 1.5 |
| `check_chip.py` | 1.8 / 1.4 | 3.0 / 2.0 | 1.5 |
| **`drc_check_cells.py`** | **1.4** / 1.4 | **1.8** / 2.0 | **1.4** |

→ `apr/rules.py` に寄せ、この差が意図的か事故かを確定させる。

## 4. 移行の順序（提案）

| # | 作業 | 理由 |
|---|---|---|
| 1 | `docs/` を先に埋める（10/11/12/40） | 訂正が 3 回入っている事実（フレーム開口、GIO、BUFTH）が分散すると必ず古い版が残る |
| 2 | `stdcell/` `pdk/` `macro/` のデータ移動 | 完全に設計非依存。移すだけで二重管理が消える |
| 3 | `char/` `syn/` の移動 | 同上。`.lib` は共通資産 |
| 4 | `apr/` へ APR_2026 版を投入、薄皮廃止・`APR_*` 統一・`rules.py` 集約 | ここが本丸。3 リポジトリ同時改修になるので早い方がよい |
| 5 | `templates/` 整備 | 4 が終わってから |
| 6 | SCLK_SPI を submodule 化して再設計 | APRtools の最初の実利用者＝実地テスト |

## 5. 決定済み（2026-09-14 時点で構成上の未決事項なし）

| # | 項目 | 決定 |
|---|---|---|
| 1 | STDCELL の正本 | **v59_4** |
| 2 | コア幅 | **5.4 µm の整数倍でパラメータ化**（`docs/03_core_geometry.md`） |
| 3 | 電源ピン名 | **`vdd`/`vss` 小文字に統一**（`docs/04_naming.md` §1） |
| 4 | `*` | **剥がす**（`docs/04_naming.md` §2）。既提出設計のトップセル名は変えない |
| 5 | `legacy/` | **同梱**。改名対象外として凍結 |
| 6 | `pre_check.py` の `FRAME_CELL_NAMES` | **MPW テンプレート上流に PR**。マージされるまでは `OSS_FRAME` への改名で回避 |

残るのは実装上の判断のみ（`FILL1` を既定で有効にするか、コア幅を 296 / 299 トラックの
どちらにするか）。`docs/90_improvement_notes.md` §6-4 を参照。

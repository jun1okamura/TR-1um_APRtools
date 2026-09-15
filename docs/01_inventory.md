# 資産棚卸しと移行対応表

調査日: 2026-09-14

## 1. 出所リポジトリの現況

| リポジトリ | 最終コミット | commits | 世代 | 行高 | 行数 | コア寸法 |
|---|---|---:|---|---:|---:|---|
| `TR-1um_Async_I2C` | — | — | 原本（v9/v10） | — | 4 | — |
| `TR-1um_SCLK_SPI` | 2026-09-08 | 27 | 2 代目 | 64.8 | 2 | 1632.6 × 314.1 |
| `TR-1um_TD4` | 2026-09-14 | 68 | 3 代目 | 59.4 | 5 | 1604.7 × 1357.0 |
| `TR-1um_I2C_2026` | 2026-09-14 | 39 | **4 代目（最新）** | 59.4 | 4 | 1611.0 × 963.2 |

## 2. スクリプトの重複状況（実測）

### 2-1. APR_2026 と TD4 の `scripts/`

```
同一        : lef_parser.py, netlist_parser.py, netlist_util.py,
              route_channels.py, ripup_reroute_shorts.py,
              squeeze_channels.py, add_power_pins.py,
              route_top_pins.py, verify_connectivity_*.py,
              drc_check.py, highlight_top_pins.py,
              scripts/pnr/README.md（64,638 B で完全一致）, spice/*.md, lef/README.md,
              irsim/*, scripts/char/* の大半
差分あり    : place.py, route.py, gen_placement_*.py, route_chip.py,
              assemble_top.py, add_top_pins.py, gen_top_routing_plan.py,
              export_mpw.py, mkchipnet.py, mklvsnet.py, verify_chip.py,
              plot_*.py, sweep_*.py, syn.sh, sta/*
I2C のみ    : i2c_config.py, drc_pdk.py, lvs_pdk.py, mkringoscnet.py,
              place_ring_osc.py, check_batch14.py, gen_chip_tb_batch14.py,
              gen_chip_tb_ringosc.py, gen_chip_sim_ready.py,
              dedup_gates.py, merge_muxdffrb_rslatch.py, cmp_cells.py,
              from_async_i2c/
TD4 のみ    : td4_config.py, mkmemport.py, mem_wrap.py, connect_macro_power.py
```

→ **`scripts/pnr/` の中核 20 本超は完全一致**。共通化の効果が最も直接的に出る。

### 2-2. SCLK_SPI の `scripts/` と APR_2026 の `scripts/pnr/`

同名の `.py` 50 本を比較した結果（SPI の `scripts/*.py` を I2C の `scripts/pnr/*.py` と照合）:

```
完全一致  7 本 : add_power_pins.py, lef_parser.py, netlist_parser.py,
                 netlist_util.py, plot_layout.py,
                 verify_connectivity.py, verify_connectivity_m1m2.py
差分あり 25 本 : place.py, route.py, route_chip.py, route_channels.py,
                 squeeze_channels.py, ripup_reroute_shorts.py,
                 route_top_pins.py, highlight_top_pins.py,
                 drc_check.py, gen_placement_json.py,
                 gen_placement_gds.py, add_top_pins.py, assemble_top.py,
                 export_mpw.py, frame_pins.py, gen_chip_tb.py,
                 gen_chip_sim_ready.py, check_chip_sim.py, gen_top_routing_plan.py,
                 place_logo.py, plot_chip_floorplan.py, plot_placement.py,
                 spi_config.py, verify_placement.py, verify_port_connectivity.py
SPI のみ 25 本 : gen_liberty.py, gen_cell_spice.py, check_cell_spice.py,
                 gen_lvs_spice.py, gen_lvs_spice_top.py, gen_sim_from_extracted.py,
                 drc_check_cells.py, cell_usage.py, sync_cell_info.py,
                 pin_list.py, gate_count.py, explore_rows.py, sweep_sclk.py,
                 check_chip.py, check_top_channels.py, merge_muxdffrb.py,
                 insert_row_buffers.py, insert_bufth.py, detect_loops_jogs.py,
                 compress_channels.py, dedup_gates.py, read_info.py,
                 pre_check.py, port_i2c_scripts.py, port_rules.py
                 （+ build.sh, run_tests.sh, synth.ys.in）
```

※ `dedup_gates.py` / `insert_bufth.py` / `merge_muxdffrb*.py` / `pre_check.py` / `read_info.py` は
APR_2026 では `scripts/pnr/` ではなく `scripts/` 直下にあるため「SPI のみ」に出ているだけで、
実際には両方に存在する（内容は別物）。

→ **SPI にしか無い 25 本のうち、`drc_check_cells.py` `sync_cell_info.py` `gen_liberty.py`
`gate_count.py` `explore_rows.py` は設計非依存で有用**。APRtools に取り込むべき。
`port_i2c_scripts.py` / `port_rules.py` / `i2c_ref/` は**移植方式そのもの**なので `legacy/` へ。

## 3. データ資産（完全に共通・二重管理を解消できるもの）

| ファイル | APR_2026 | TD4 | SCLK_SPI | 移行先 |
|---|---|---|---|---|
| `TR-1um_STDCELL.gds` | 389,290 B | 同一 | 219,030 B（64.8版） | `stdcell/v59_4/` / `v64_8/` |
| `TR-1um_cells.lef` | 92,076 B | 同一 | — | `stdcell/v59_4/` |
| `TR-1um_STDCELL.lef` | — | — | 75,075 B | `stdcell/v64_8/` |
| `TR-1um_tech.lef` | 643 B | 同一 | — | `stdcell/v59_4/` |
| `TR-1um_PNR.{gds,lef}` | 415,252 / 95,829 B | 同一 | — | `stdcell/v59_4/`（MEMPORT 込み） |
| `tr1um_typ_5v0_25c.lib` | 193,112 B | 186,133 B | — | `stdcell/v59_4/`（**I2C 版が新しい＝RSLATCH 入り**） |
| `TR1um_5_stdcell{,_area}.lib` | — | — | 27,718 / 21,438 B | `stdcell/v64_8/` |
| `cell_info.json` | `layout/` 生成 | 同 | `lef/` 5,404 B | `stdcell/vXX/` |
| `TR-1um_frame_25x25.gds` | 189,282 B | 同一 | 189,858 B | `pdk/frame/`（**差分要確認**） |
| `TR-1um_frame.lef` | 16,711 B | 同一 | — | `pdk/frame/` |
| `opensusi_logo.txt` | 20,502 B | 同一 | 同一 | `pdk/art/` |
| `RING_OSC.{gds,lef}` | 23,290 / 172,327 B | — | — | `macro/ringosc/` |
| `INV3D.{sch,sym,extracted}` | あり | — | — | `macro/ringosc/` |
| `BUF_X2.{sch,sym,extracted}` | — | — | あり | `stdcell/v64_8/`（※`.sch` が BUF_X1 の回路だった既知バグ） |
| `scripts/char/` 一式 | あり | あり（+ mem/pad） | — | `char/`（**TD4 版が上位: cells_mem / cells_pad あり**） |
| `abc.constr` `tr1um.genlib` | あり | 同一 | — | `syn/` |

**フレーム GDS の版**（確認済み）: セル構成は 3 リポジトリとも同一 29 セルだが、内容は 2 版ある。

| リポジトリ | md5 | 最終更新 |
|---|---|---|
| APR_2026 / TD4 | `df0d0ec2…` | 2026-09-11 / 09-14（**新**） |
| SCLK_SPI | `6117a7a0…` | 2026-09-07（旧、189,858 B） |

→ **APR_2026 / TD4 側を `pdk/frame/` の正本にする**。SCLK_SPI 再設計時にフレームが
差し替わるので、`GIO_PIN_RADIUS` などの実測値が変わっていないか `frame_pins.py` で再確認すること
（SPI の `design_notes` §21.3 が待っていた `64e40f5 UPDATE: OSS_FRAME_GIO` がこの差分の可能性が高い）。

## 4. ドキュメント資産

| ファイル | サイズ | 実際の内容 | 移行先 |
|---|---:|---|---|
| `SCLK_SPI/design_notes.md` | 110 KB | SPI の全記録（最も詳細） | 設計リポジトリに残す。共通部は `docs/40_gotchas.md` へ抽出 |
| `SCLK_SPI/scripts/SCRIPTS.md` | 38 KB | スクリプト解説 | `docs/21_flow_place.md` / `22_flow_route.md` の素材 |
| `SCLK_SPI/scripts/PORTING.md` | 7 KB | 移植方式の説明 | `legacy/PORTING_HISTORY.md` |
| `I2C_2026/scripts/pnr/README.md` | 64 KB | **中身は TD4**（I2C という語は 3 箇所のみ） | 共通 7 割を `docs/2x_*` へ、TD4 固有 3 割は TD4 リポジトリへ |
| `TD4/reference/01〜07` | 計 45 KB | プロセス事実・設計方針・面積・ピン計画・メモリ | `03` → `docs/10_pdk_facts.md`、`05` → `docs/11_frame_io.md`、`07` → `macro/regfile/` の README |
| `I2C_2026/spice/LVS_analysis.md` | 18.5 KB | **中身は TD4 メモリの LVS 5 回分** | `docs/30_verify_drc_lvs.md`（PDK LVS の癖として汎用） |
| `I2C_2026/spice/README.md` | 16.8 KB | 同上（REG4x16/8x16） | 同上 + `macro/regfile/` |
| `I2C_2026/lef/README.md` | 8.2 KB | TD4/C4004 向け | `stdcell/CELLS.md` |
| `*/irsim/README.md` | 6 KB | REG4x16/8x16 の IRSIM | `docs/31_verify_ngspice.md` or `macro/regfile/` |
| `*/scripts/char/{README,RUN}.md` | 3.6 / 8.1 KB | 特性化手順 | `docs/50_char.md` |
| `*/scripts/sta/README.md` | 6.6 / 1.9 KB | STA + OpenSTA ビルド手順 | `docs/20_flow_syn.md` |

**重要**: `03_TR-1um_facts.md` は**3 回訂正が入っている**（① パッドは ESD のみ →
`OSS_FRAME_GIO` があるので誤り、② シュミット入力は無い → `BUFTH` がある、③ 有効コアは
四隅を避けて ~3.0 mm² → 四隅まで含めて 1,840 角）。**分散させると必ず古い版が残る**ので
最優先で 1 本化する。

## 5. 移行しないもの

- 各設計の `hdl/` `out/` `layout/` `src/` `info.yaml` `docs/info.md`
- `.pnr_stage/*.tgz`（TD4 の作業スナップショット 28 個）
- `Claude outputs/`（TD4 / SCLK_SPI の中間生成物）
- `reference/v10/`（SCLK_SPI が借用した I2C v10 の TB）→ 必要なら `legacy/` へ

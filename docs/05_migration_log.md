# データ移動の記録

実施: 2026-09-15 / 方式: **コピー**（設計リポジトリの原本は残したまま）

> 3 設計（SCLK_SPI / TD4 / APR_2026）はいずれも提出済みで動いている。
> 原本を削除するのは**各設計を submodule 参照に切り替えたとき**にする。
> それまでは APRtools 側が正、設計リポジトリ側は凍結コピー、という扱い。

## 0. 分類の原則

| 区分 | 扱い |
|---|---|
| **PDK 由来** | **コピーしない。** `TR1UM_PDK` で参照する（`pdk/README.md`） |
| **PDK から生成される派生物** | **コピーしない。** 生成スクリプトだけ `apr/` に置く |
| **設計固有** | **コピーしない。** 設計リポジトリに残す |
| **自作・設計非依存** | APRtools へコピー |
| **生成物（中間ファイル）** | コピーしない |

## 1. コピーしたもの

### `stdcell/v59_4/` — 自作セルライブラリ（正本）1.6 MB

出所: `TR-1um_I2C_2026/lef/` と `layout/cell_info.json`、`scripts/cell_area.json`

```
TR-1um_STDCELL.gds        51 セル（論理 31 + メモリ階層 + via_1）
TR-1um_cells.lef          48 MACRO
TR-1um_tech.lef           SITE / LAYER / VIA 定義
TR-1um_PNR.gds/.lef       ↑ + MEMPORT（横置きの実験。**U89 以降フローは読まない**）
tr1um_typ_5v0_25c.lib     実特性化 Liberty（RSLATCH 入り、193 KB）
cell_info.json            セル寸法表（mkcellinfo.py 生成、LEF と GDS を突き合わせ済み）
cell_area.json            面積見積り用
simulation/*.spice        36 セルの LVS ソースネットリスト
extracted/*.extracted     36 セルの抽出ネットリスト
```

### `stdcell/v64_8/` — 旧世代（凍結）360 KB

出所: `TR-1um_SCLK_SPI/lef/`。**SCLK_SPI の提出済み GDS を再現する用途のみ。**
`BUF_X4` / `BUF_X16` は LEF に MACRO があって GDS に実体が無い既知バグを含む。

### `art/` — OpenSUSI ロゴ 24 KB

`opensusi_logo.txt`（317 × 63 セル / 5,785 ドットのビットマップ。**コメント文字は `%`**）。
PDK の `GDSII/…/LOGO_opensusi.gds` とは別物（あちらはワークショップ用の GDS）。

### `macro/ringosc/` — リングオシレータ TEG 284 KB

`RING_OSC.{gds,lef,extracted}` / `RING_OSC_drc.lyrdb` / `INV3D.{sch,sym,extracted}` と、
配置・ネットリスト生成の `place_ring_osc.py` / `mkringoscnet.py`。

### `macro/regfile/` — レジスタファイル生成 72 KB

`mkspice.py`（`REGx16` の SPICE 生成、`--bits N`）、`mkmemport.py`（`REG8x16` を R90 して
`MEMPORT` を作る）、`mem_wrap.py`（マップ後ネットリストのメモリをマクロ＋グルーに差し替え）、
`mem_array_estimate.py`、`block_report.py`、`07_memory_array.md`（設計資料）。

### `apr/` — P&R エンジン 1.1 MB / 76 ファイル

出所: `TR-1um_I2C_2026/scripts/pnr/*.py`（設計固有を除く全部）+ `scripts/` 直下の
設計非依存スクリプト。**この第 1 段階ではファイル名も配置もそのまま**
（`docs/04_naming.md` §4 の手順 1「まず素通しで md5 一致を確認する」に対応）。

`apr/from_sclk_spi/` (9 ファイル) は **SCLK_SPI にしか無い設計非依存スクリプト**を
出所が分かる形で分けて保管したもの。`apr/` 本体へ統合するのは、同名ファイルとの
差分を解消してから:

```
drc_check_cells.py            STDCELL 全セルに単体 DRC
sync_cell_info.py             FOREIGN 不整合・GDS セル欠落の警告
gen_liberty.py                cell_info.json → 実面積 Liberty
gate_count.py                 規模レポート
explore_rows.py               行数の検討
detect_loops_jogs.py          ループ／ジョグ検出
compress_channels.py  チャネル圧縮（squeeze とは別系統）
gen_cell_spice.py             セル実体の SPICE
check_cell_spice.py           GDS 幾何との突き合わせ
```

### `syn/` — 合成・STA 44 KB

`syn.sh` / `abc.constr` / `tr1um.genlib` / `synth.ys.in` / `sta/{setup,report,path}.tcl` / `sta/sta.sh`

### `char/` — セル特性化 616 KB

出所: `TR-1um_I2C_2026/scripts/char/`。
スクリプト一式と**特性化結果 `char/`（セルごとの JSON）**、`RESULTS.txt`、`RUN.md`、`README.md`。
`models/` `cells_*/` `pack*/` `decks/` `logs/` は除外（`char/README_APRTOOLS.md`）。

### `legacy/` — 移植原本 3.9 MB

| 置き場 | 中身 |
|---|---|
| `legacy/async_i2c/` | `TR-1um_Async_I2C/script/` の `.py` / `.sh` 82 本 + `SCRIPTS.md` / `design_notes.md` / `README.md` / `logic_cells_mapping.md` |
| `legacy/sclk_spi/` | `scripts/i2c_ref/` 33 本 + `port_i2c_scripts.py` / `port_rules.py` / `PORTING.md` / `SCRIPTS.md` |
| `legacy/i2c_2026/` | `scripts/pnr/from_async_i2c/` 9 本 |

**`legacy/` は改名しない・整形しない。** 原本の同一性を保つのが目的。

### `templates/` 40 KB

`config_example_i2c.py`（`i2c_config.py` をそのまま。`config.py.in` を書くときの参照）、
`build.sh`、`run_tests.sh`。

## 2. 意図的にコピーしなかったもの

### 2-1. PDK 由来（`pdk/README.md` 参照）

| 対象 | 元の場所 | 理由 |
|---|---|---|
| **`TR-1um_frame_25x25.gds`** | 各設計 `lef/` | **PDK の `libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds`**。しかも TD4 / APR_2026 の版は PDK のどのリビジョンとも一致しない（`pdk/README.md` §4） |
| **`TR-1um_frame.lef`** | 各設計 `lef/` | `mkleffrm.py` が PDK の GDS から生成する派生物 |
| **`lef/simulation/OSS_FRAME_GIO*.spice`** | 各設計 | `mkframespice.py` が生成する派生物 |
| **`scripts/char/models/`** | 各設計 | **PDK `libs.tech/spice/models/` と 5 ファイル全部バイト一致**を確認済み |
| **`lef/simulation/OSS_FRAME_GIO.spice` / `_nocombine.spice`** | 各設計 | `mkframespice.py` がフレーム GDS から生成する派生物。**一度コピーしてしまい、後から除去した** |
| **`lef/extracted/OSS_FRAME_GIO.extracted`** | 各設計 | 同上 |
| `scripts/char/cells_pad/` | TD4 | フレーム由来の刺激。`cells_ext` と同じ理由で生成物扱い |
| `scripts/char/cells_mem/` | TD4 | `mkmemsrc.py` の生成物 |
| DRC / LVS デッキ、`via_1` PCell | — | そもそも設計リポジトリにも無い。`TR1UM_PDK` 経由 |

### 2-2. 設計固有

| 対象 | 理由 |
|---|---|
| `i2c_config.py` / `td4_config.py` / `spi_config.py` | 設計ごとの `config.py` になる。参照用に `templates/config_example_i2c.py` だけ残した |
| `hdl/` `out/` `layout/` `src/` `info.yaml` `docs/info.md` | 設計そのもの |
| `TD4/reference/01〜06` | TD4 の設計判断（`07_memory_array.md` だけは汎用なので `macro/regfile/` へ） |
| `gen_chip_tb_batch14.py` / `check_batch14.py` | I2C プロトコル固有のテストベンチ |
| `gen_chip_tb_ringosc.py` | RING_OSC 固有の TB（`macro/ringosc/` に入れるか要判断） |
| `stat_*.txt` | 設計ごとの合成統計 |
| `PAD_MAP`（`gen_top_routing_plan.py` 内） | **スクリプト本体に直書きされたまま移動している。** 設計固有なので `config.py` へ出す必要がある（`docs/90_improvement_notes.md` H-3） |

### 2-3. 生成物・巨大ファイル

| 対象 | サイズ | 理由 |
|---|---|---|
| `scripts/char/pack/` | **127 MB** | ngspice デッキ 14,179 本。`genjobs.py` が再生成する |
| `scripts/char/pack_rslatch/` | 1.2 MB | 同上 |
| `scripts/char/logs/` | 3 MB | 実行ログ |
| `scripts/char/decks/` | 276 KB | 生成デッキ |
| `scripts/char/cells_ext/` | 188 KB | `loadext.py` が `lef/extracted/` から生成 |
| `TR-1um_Async_I2C/script/*.json` | 129 ファイル | v8/v9/v10 世代の中間 JSON |
| `__pycache__` / `.DS_Store` | — | |
| `.pnr_stage/*.tgz` | — | TD4 の作業スナップショット 28 個 |
| `Claude outputs/` | — | 中間生成物 |

## 3. 移動後の構成と容量

```
TR-1um_APRtools/        8.3 MB / 406 ファイル
├── apr/                1.1 MB   P&R エンジン（76 + from_sclk_spi/ 9）
├── stdcell/            1.9 MB   v59_4（正本） / v64_8（凍結） / CELLS.md
├── char/               616 KB   特性化スクリプト + 結果
├── macro/              356 KB   ringosc / regfile
├── docs/               256 KB   17 文書
├── syn/                 44 KB
├── templates/           44 KB
├── art/                 24 KB
├── pdk/                  4 KB   README のみ（★ データは置かない）
└── legacy/             3.9 MB   移植原本（read-only）
```

各ディレクトリの README:
`pdk/README.md` / `stdcell/v59_4/README.md` / `stdcell/CELLS.md` /
`char/README_APRTOOLS.md` / `legacy/README.md` / `templates/README.md`

## 4. 進捗

| # | 作業 | 状態 |
|---|---|---|
| 1 | `apr/` の import 中立化（`import config as cfg` + `apr_path` + `config_base.py` / `rules.py`） | **完了**（50 ファイル） |
| 2 | APR_2026 で **step10 GDS の md5 一致**を確認 | **完了・一致**（`docs/06_verify_migration.md`） |
| 3 | フレームを PDK 版に揃えて DRC / LVS を再実行（`pdk/README.md` §4 / U19） | 未 |
| 4 | 環境変数の `APR_*` 統一（`docs/04_naming.md` §3） | 未 |
| 5 | `*` 剥がし（同 §2） | 未 |
| 6 | 電源ピン名 `vdd`/`vss` 統一（同 §1） | 未 |
| 7 | `apr/from_sclk_spi/` 9 本を本体へ統合 | 未 |
| 8 | `apr/` をサブディレクトリに分割（`docs/00_directory.md` §1） | 未 |
| 9 | TD4 / SCLK_SPI でも同じ検証 | 未 |

### 手順 1 で新設したファイル

| ファイル | 役割 |
|---|---|
| `apr/config_base.py` | 設計非依存の既定値・PDK 解決・コア幾何の導出・`check()`。設計は `config.py` で `from config_base import *` → 上書き → `finalize(globals())` |
| `apr/rules.py` | レイヤ番号・DRC 値・グリッド・電源ネット名の**単一ソース**（4 箇所に散っていた DRC 値をここへ） |
| `apr/apr_path.py` | 設計ルートを `sys.path` の**末尾**に足す（先頭ではない = `apr/` のモジュールを隠さない） |
| `apr/selfcheck.py` | KLayout 無しで下ごしらえを点検（config / 入力 / stdcell の一致 / TAP 列 / PDK 解決） |
| `templates/config_i2c_2026_verify.py` | 検証用の設計 config（成果物名は旧 `*` のまま） |

### 設計リポジトリ側に足したもの

`TR-1um_I2C_2026/config.py`（`templates/config_i2c_2026_verify.py` のコピー）。
**追加だけで、既存ファイルは変えていない。**

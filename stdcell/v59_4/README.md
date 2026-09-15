# `stdcell/v59_4` — 自作セルライブラリ（正本）

行高 **59.4 µm**、サイト **5.4 µm**。セル一覧は [`../CELLS.md`](../CELLS.md)。

> **PDK 同梱の `libs.tech/klayout/libraries/TR-1um_STDCELL.gds`（105 セル）とは別物。**
> 同名だが中身も行高も違う。`../../pdk/README.md` §2。

| ファイル | 中身 | 生成元 |
|---|---|---|
| `TR-1um_STDCELL.gds` | 51 セル | 手描き（回路図は PDK の `libs.tech/xschem/TR-1um_5_stdcell`） |
| `TR-1um_cells.lef` | 48 MACRO | `apr/mklef.py` |
| `TR-1um_tech.lef` | SITE / LAYER / VIA | 手書き |
| `TR-1um_PNR.gds` / `.lef` | 上記 + `MEMPORT` | `macro/regfile/mkmemport.py` |
| `tr1um_typ_5v0_25c.lib` | 実特性化 Liberty | `char/mklib.py` |
| `cell_info.json` | セル寸法表 | `apr/mkcellinfo.py`（LEF と GDS を突き合わせ、食い違ったら停止） |
| `cell_area.json` | 面積見積り用 | |
| `simulation/*.spice` | 36 セルの **LVS ソース**ネットリスト | 回路図から |
| `extracted/*.extracted` | 36 セルの**抽出**ネットリスト | `apr/gds_extract.py` |

**配置配線が読むのは `TR-1um_PNR.{gds,lef}` の 2 つだけ。**
ライブラリ本体（`TR-1um_STDCELL.gds` / `TR-1um_cells.lef`）は汚さない。

## ★ ここに置かないもの（PDK のフレーム GDS からの派生物）

| 対象 | 再生成 |
|---|---|
| `OSS_FRAME_GIO.spice` / `_nocombine.spice` | `apr/mkframespice.py [--no-combine]` |
| `OSS_FRAME_GIO.extracted` | `apr/klayout_extract.py` |
| `TR-1um_frame.lef` | `apr/mkleffrm.py` |
| `*.sim`（IRSIM 用） | `apr/frame2sim.py` |

生成先は**各設計リポジトリの作業ディレクトリ**。`../../pdk/README.md` §3。

## 整合チェック

```sh
python3 apr/from_sclk_spi/sync_cell_info.py     # FOREIGN 不整合・GDS セル欠落
python3 apr/from_sclk_spi/drc_check_cells.py    # 全セルに単体 DRC（GDS を触ったら回す）
python3 apr/from_sclk_spi/check_cell_spice.py   # SPICE と GDS 幾何の突き合わせ
python3 apr/pin_grid_check.py                   # ピンがトラックに乗っているか
python3 apr/normalize_prboundary.py             # セル原点と prBoundary 左下を一致させる
```

**v64_8 では `BUF_X2` の `FOREIGN` が `BUF_X1` を指しており、レイアウトに `BUF_X1` の図形が
入ったまま LVS まで気づけなかった。** `sync_cell_info.py` はそれを検出するために足した。

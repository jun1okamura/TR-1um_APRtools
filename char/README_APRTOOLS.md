# `char/` に置いていないもの

手順は [`../docs/50_char.md`](../docs/50_char.md)。
生成物と PDK 由来のものはコミットしない。実行前に作る:

| 対象 | 中身 | 用意の仕方 |
|---|---|---|
| `models/` | **PDK の SPICE モデル** | `$TR1UM_PDK/libs.tech/spice/models` を参照（**コピーしない**。`ip62_models` / `models_IP62_{cap,diode,mos,res}` の 5 ファイルとも PDK とバイト一致を確認済み） |
| `cells_ext/` | セルごとの抽出ネットリスト | `python3 loadext.py ../stdcell/v59_4/extracted -o cells_ext` |
| `cells_mem/` | メモリ特性化用の刺激 | `python3 mkmemsrc.py` |
| `cells_pad/` | パッド特性化用の刺激（**PDK のフレーム由来**） | `apr/mkframespice.py` の出力から |
| `pack/` `pack_rslatch/` | ngspice デッキ 14,179 本（**127 MB**） | `python3 genjobs.py -o pack` |
| `decks/` `logs/` | 実行の中間物 | |

コミットしているのは**スクリプト**と**特性化結果 `char/`（セルごとの JSON）**、
`RESULTS.txt`、`RUN.md`、`README.md`。

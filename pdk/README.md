# PDK は参照する — コピーしない

このディレクトリに **PDK のデータは置かない**。
`TR-1um`（OpenSUSI PDK）が持っているものを APRtools に複製すると、
必ずどこかで版がずれて「手元では通るのに CI で落ちる」が起きる。

> **例外が 1 つある**: [`pending-upstream/`](pending-upstream/README.md) には
> 「PDK に PR を出したがまだマージされていないもの」だけを置く。
> いまは `OSS_DRV` を直したフレーム（`docs/07_frame_issue.md`）。
> マージされたらファイルを消すだけで PDK 参照に戻る。

## 1. 解決方法

環境変数 **`TR1UM_PDK`** に PDK のチェックアウトを指す。未設定なら以下を順に探す
（`*_config.pdk_tech_python()` の既定と同じ）:

```
$TR1UM_PDK
~/Dropbox/91_OpenPDK/TR-1um
../TR-1um                      （設計リポジトリの兄弟）
~/TR-1um
```

## 2. PDK が持っているもの（＝コピー禁止）

| 用途 | PDK 内のパス |
|---|---|
| **フレーム GDS（GIO パッド）** | `libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds` ★これを使う |
| フレーム GDS（アナログパッド） | `libs.tech/klayout/libraries/TR-1um_frame_25x25.gds` **`OSS_FRAME_GIO` は入っていない** |
| フレームの回路図 | `libs.tech/xschem/TR-1um_frame/OSS_*.{sch,sym}` |
| ESD セル | `libs.tech/klayout/libraries/TR-1um_ESD.gds` |
| **SPICE モデル** | `libs.tech/spice/models/{ip62_models,models_IP62_*.lib}` |
| **DRC デッキ** | `libs.tech/klayout/tech/drc/{run.drc,00_Layers.drc,01_Basics.drc,02_Device.drc,03_Electrical.drc}` |
| MDP | `libs.tech/klayout/tech/drc/{run_mdp.drc,run_IP62.drc}` |
| **LVS デッキ** | `libs.tech/klayout/tech/lvs/{run.lvs,05_Compare.lvs,…}` |
| **`via_1` PCell** | `libs.tech/klayout/tech/python` |
| PDK 同梱の標準セル | `libs.tech/klayout/libraries/TR-1um_STDCELL.gds`（**105 セル・別ライブラリ**） |
| PDK 同梱ロジックセル | `STDLIB/LogicCells`（行高 62.6 µm） |
| 設計規則表 | `Document/TR-1um_Drawing_Layer_DR_Table.csv` |
| 文字セル | `libs.tech/klayout/libraries/TR-1um_Characters{1,2}.gds` |

> **⚠ PDK 同梱の `TR-1um_STDCELL.gds` は APRtools の `stdcell/v59_4/` と同名だが別物。**
> PDK 版は 105 セル（`CLKBUF_*` / `DECAP*` / `BUF_X8..X16` / `DFFR` / `FILL1TAP` を持ち、
> `BUFTH` / `RSLATCH` / `MUXDFFRB` / `TLAT` / `REG*x16` / `FILL2` / `FILL3` / `TAP2` を持たない）。
> **行高も違う。** 取り違えないこと。

## 3. PDK データから生成するもの（生成物もコミットしない）

| 生成物 | 生成コマンド | 入力 |
|---|---|---|
| `TR-1um_frame.lef` | `apr/mkleffrm.py` | PDK のフレーム GDS |
| `OSS_FRAME_GIO.spice`（ngspice 用） | `apr/mkframespice.py` | 同上 |
| `OSS_FRAME_GIO_nocombine.spice`（LVS 用） | `apr/mkframespice.py --no-combine` | 同上 |
| `*.sim`（IRSIM 用） | `apr/frame2sim.py` | 同上 |

生成先は**各設計リポジトリの作業ディレクトリ**。APRtools には置かない。

## 3-b. ★ 同名で中身の違うフレームが 2 つある

| ファイル | サイズ | セル | `OSS_FRAME_GIO` |
|---|---:|---:|---|
| `TR-1um_frame_25x25.gds` | 104,994 B | 23 | **無い**（アナログ 14 パッド） |
| `TR-1um_frame_25x25_GIO.gds` | 189,858 B | 29 | **ある**（+ `OSS_ESD_5V_DIO` / `OSS_DRV` / `OSS_*CH_DRV`） |

**設計リポジトリは GIO 版の中身を `lef/TR-1um_frame_25x25.gds` という
非 GIO 版と同じ名前で置いている。** ベース名で解決すると違うファイルを掴む。

→ `apr/config_base.pdk_frame_gds()` は **`_GIO` 付きを明示的に**返す。
設計側にコピーを置かないのはこの取り違えを構造的に無くすため。

## 4. ★ フレーム GDS が設計間でずれている（2026-09-15 確認）

タイムスタンプを除いた正規化 md5 で照合した結果:

| 出所 | 正規化 md5 | 判定 |
|---|---|---|
| PDK `dev` @ `64e40f5`（2026-08-26 `UPDATE: OSS_FRAME_GIO`） | `20f8f9f888c6` | **正** |
| `TR-1um_Async_I2C/FRAME/` | `20f8f9f888c6` | PDK と一致 |
| `TR-1um_SCLK_SPI/lef/` | `20f8f9f888c6` | PDK と一致 |
| **`TR-1um_TD4/lef/`** | **`08fd3bd6b1a3`** | **PDK の全リビジョンと不一致** |
| **`TR-1um_I2C_2026/lef/`** | **`08fd3bd6b1a3`** | TD4 から引き継ぎ |

差分はセル **`OSS_DRV`（出力ドライバ）1 個だけ**。セル構成・sref 数・text 数は同じだが、
レコード数が **1016 → 976** と 40 少なく、コンタクト／ビアの座標が違う。
PDK の `TR-1um_frame_25x25_GIO.gds` の全 3 リビジョン
（`e2eaa91` / `146b1ed` / `64e40f5`）のいずれとも一致しない。

**→ TD4 と APR_2026 は、PDK に存在しないフレームで作られている。**
提出済み GDS はそのジオメトリを含む。APRtools へ移行するときに
**PDK 版へ揃えて DRC / LVS を再実行すること**（`docs/90_improvement_notes.md` U19）。

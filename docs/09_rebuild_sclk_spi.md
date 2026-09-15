# SCLK_SPI の作り直し（2026-09-15）

`TR-1um_SCLK_SPI` は **行高 64.8 µm の旧 STDCELL** で作られている。正本は
**59.4**（`docs/02_stdcell_diff.md` / U32）。論理セルの**幅は全セル同一**だが
行高が違うので、行の y もチャネルの割り付けも別物になる。
**提出済みの GDS と突き合わせる形では検証できない**ので、I2C / TD4 のような
「再現」ではなく**合成からの作り直し**にした。

判定は **DRC / LVS / ngspice / STA** の 4 つで取る。

提出済みの 64.8 版は `TR-1um_SCLK_SPI/reference/v64_8/` に丸ごと残してある。

## 結論

| 段 | 結果 |
|---|---|
| 合成 `syn.sh`（引数なし） | 52 セル -> dedup 52 -> 畳み込み 37 -> BUFTH 3 本 = **40 セル** |
| 面積 | **132,795 µm²**（旧 64.8 版の提出 134,078 から −1.0%） |
| RTL の TB（iverilog 11 本） | **11/11 PASS** |
| ゲートレベルの TB（同じ 11 本） | **11/11 PASS** |
| STA（OpenSTA、P&R 前） | 最小周期 **27.512 ns = 36.35 MHz**、hold **+5.381 ns** |
| 配置 `place.py` / 配線 `route.py` | 通る。**短絡 0 / 25 ポート全接続** |
| コア（step10 squeeze 後） | **1598.4 × 308.7 µm**（旧 1620.0 × 1329.6） |
| チップ `verify_chip.py` | **すべて OK**（24 ネットが独立、電源はフレームまで） |
| DRC（コア / チップ / MDP） | **0 件 × 3** |
| LVS | **Netlists match** |
| ngspice（チップ全体・トランジスタ） | **12 項目すべて PASS**、tco 最悪 41.2 ns |

> DRC / LVS はクラウドの **KLayout 0.28 + `--allow-old-klayout`**。
> **サインオフは 0.29 以上で取り直すこと**（`docs/30_verify_drc_lvs.md` §0）。
> レポートが完全版かどうかは `grep -c "M1P.PE" <report>.lyrdb` が 1 か 0 か。

## 面積が 4.4 倍になった理由

旧 64.8 版のコアは **1620.0 × 1329.6 = 2.154 mm²**。内訳は

    ch0 140.0 / row0 64.8 / **ch1 900.0** / row1 64.8 / ch2 160.0

真ん中のチャネルを 900 µm 取ったまま**圧縮していない**。APRtools の
step10（squeeze）は使わなかったトラックを削るので、同じ予算
（`CH_HEIGHTS = [140.4, 700.0, 162.0]`）で回しても最終は **308.7 µm** になる。
**0.494 mm²**。

## フロアプラン

`apr/explore_rows.py --rows 1 2 3 4`（40 セル / セル幅の総和 2,235.6 µm）:

| 行数 | 最大行幅 | 収まる | 行内で閉じる網 | 行を跨ぐ網 | 最大 ch トラック | コア W×H |
|---:|---:|:--:|---:|---:|---:|---|
| 1 | 2235.6 | NO | 56 | 0 | 17 | 2236 × 151 |
| **2** | **1166.4** | **OK** | **50** | **6** | **11** | **1166 × 243** |
| 3 | 831.6 | OK | 49 | 7 | 11 | 832 × 356 |
| 4 | 615.6 | OK | 45 | 11 | 13 | 616 × 486 |

1 行では行幅の上限に入らず、3 行以上は行を跨ぐ網が増えてコアが縦に伸びる
だけ。**2 行**。旧版も 2 行だった。

**U15 もここで直る。** 旧版のコア幅 1620.0（300 トラック）は TAP の上限
1614.6（299）を超えていて、最終間隔 540.0 が実測ピッチ 534.6 を超えたまま
提出されている。新しい版は **296 トラック = 1598.4**（I2C / TD4 と同じ）。

**行ごとのクロックバッファ（旧 `insert_row_buffers.py`）は入れていない。**
配置と結び付いた 2 パスの仕組みで、正本の I2C 世代のフローには無い。
入れずに配線が通ったので、そのままにする。

## APRtools 側で直したもの

| # | 症状 | 対処 |
|---|---|---|
| 1 | `syn/syn.sh` が I2C の値を直書き（RTL・トップ・abc 制約・BUFTH の網・V10 の参照ネットリスト・周期）で SCLK_SPI では回らない | **`config.py` から取る**。段は与えられたものだけ回る（U36）。I2C でも通した |
| 2 | `syn_report.py` が `cell_area.json` を**スクリプトの隣**に探す | `cfg.stdcell_file()`（`cmp_cells.py` と同じ壊れ方、U37） |
| 3 | 手書きの `hdl/cells_sim.v` に `INV_X2` が無く、ABC が選んだ瞬間にゲート TB がコンパイルできない | `char/mkcellverilog.py` の生成物に切り替え（U38） |
| 4 | `syn/sta/{setup,report}.tcl` に I2C の網名（`scl_gated` / `scl_n`）が残っていて、SPI で回すと出力が嘘になる | 一般化（U39） |
| 5 | `explore_rows.py` が SCLK_SPI 64.8 世代を直書き（`apr/` の外を見る ROOT / 行高 64.8 / 行幅 1620） | `config.py` から |
| 6 | `CELL_INFO` が `<設計>/layout/cell_info.json` 固定で、持っていない設計で止まる | 設計に無ければ **STDCELL 正本**から。既提出設計の値は黙って置き換えない（TD4 の MEMPORT は高さが違う） |
| 7 | `verify_chip.py` の**コアタップ照合が一度も動いていなかった** | コア側は小文字 `vdd`/`vss`。境界で写像し、**0 本なら NG** に（U21 の 1 件） |
| 8 | `verify_chip.py` が RING_OSC を前提に落ちる | `cfg.HAS_RING_OSC` で節ごと畳む（U30 と同じ形） |
| 9 | チップ電源のライザ / ストリップの x が TD4 の値で直書き。下辺の **−100.0 / 0.0 がコアのポート −99.9 / −2.7 に重なって `rx_data[0]` / `rx_data[2]` が GND へ短絡** | `CHIP_VDD_RISER_X` / `CHIP_VSS_STRIP_X`（U41） |
| 10 | `mkchipnet.py` が要るフレームの LVS ソースを**フローのどの段も作らない**。しかも `lef/simulation` が xschem の作業場への **symlink** | `FRAME_LVS_SPICE` で置き場を指定。エラーに `mkframespice.py` の打ち方を書いた（U40） |

**10 件のうち 9 件が「パスと名前」か「既定値」。** 設計 3 つ目でもこの比率は
変わらない（I2C 6 件 / TD4 7 件 / SPI 10 件）。

## 設計側で直したもの

| # | 症状 | 対処 |
|---|---|---|
| 11 | `scripts/gen_chip_tb.py` が `.subckt` の**ポート順を直書き**。`gen_chip_sim_ready.py` の出す並びは KLayout 抽出の**辞書順**（P1 P10 P11 … P9 VDD VSS）で、フレーム順（P1 P2 … VSS … VDD）と違う | **ポート順は生産物から読む**（U42） |
| 12 | 同じく `gio_connections.json` の形が旧版（`connections` 辞書）前提。APRtools は `signals`（リスト） | 両方読む |
| 13 | 出力先が `ngspice/` で、`gen_chip_sim_ready.py` の `layout/chip/simulation/` と噛み合わない | 揃えた |
| 14 | 抽出ネットリストが ngspice の既定の許容差だと t≈0.41 µs で進まない | `abstol=1e-11 vntol=1e-5 itl4=200`（U43） |

> ★ **11 は落ちない種類の壊れ方**。ngspice はポート数さえ合えば黙って繋ぐので、
> 全パッドが別の網に刺さったまま走りきって **12 項目中 10 項目が FAIL、
> 残り 2 項目がまぐれで PASS** になる。「結果が変」から遡って初めて分かる。
> **生産者と消費者の契約は、必ず生産物から読むこと。**

## 回し方

```sh
cd ~/HogeHoge/LSI_Design/TR-1um_SCLK_SPI
export TR1UM_PDK=~/HogeHoge/OpenPDK/TR-1um
export APRTOOLS=~/HogeHoge/OpenPDK/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
export PYTHONHASHSEED=0

sh $APRTOOLS/syn/syn.sh                    # 合成 + TB + STA
python3 $APRTOOLS/apr/explore_rows.py      # 行数の当たり（決め直すとき）
python3 $APRTOOLS/apr/place.py
python3 $APRTOOLS/apr/route.py
python3 $APRTOOLS/apr/assemble_top.py
python3 $APRTOOLS/apr/gen_top_routing_plan.py
python3 $APRTOOLS/apr/route_chip.py
python3 $APRTOOLS/apr/add_top_pins.py
python3 $APRTOOLS/apr/verify_chip.py
python3 $APRTOOLS/apr/place_logo.py
python3 $APRTOOLS/apr/mklvsnet.py && python3 $APRTOOLS/apr/mkchipnet.py
python3 $APRTOOLS/apr/export_mpw.py
python3 $APRTOOLS/apr/pre_check.py src/tr_1um_3wire_SPI.gds --top tr_1um_3wire_SPI
```

DRC / LVS / ngspice は `docs/30_verify_drc_lvs.md` §0 と
`docs/31_verify_ngspice.md` §0。チップ TB だけは刺激が設計固有なので
`scripts/gen_chip_tb.py` と `scripts/check_chip_sim.py`（設計側）を使う。
**`tb_chip_spi.spice` はコミットしていない** — `.include` が PDK の絶対パスに
なるので回す機械で作り直す（U24 / `layout/chip/simulation/README_tb.md`）。

## ロゴ

チップ全体でいちばん広い空きを実測で探した（step3 の全図形を 4 µm 太らせて
5 µm 格子に落とし、最大の空き長方形を取る）:

    1. x −520…−140  y  180…805   380 × 625   <- ここ
    2. x  105…290   y −805…−175  185 × 630
    3. x  600…800   y −745…−175  200 × 570

紋章だけ（`LOGO_COLS = "0:64"`）を**等倍**で 323 × 313 µm。TD4 は 1/2 に
縮めて 165 × 160 しか置けなかったので、SPI の方が大きく出る。全幅（0:316）は
1,583 µm 要るのでどの空きにも入らない。

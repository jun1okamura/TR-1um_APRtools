# DRC と LVS

> **★ 原則: 自作チェッカが 0 を返したことは根拠にならない。**
> 最終判断は **PDK 公式デッキ（`drc_pdk.py` / `lvs_pdk.py`）と CI** の結果で取る。
> 実害が出た事例は `docs/40_gotchas.md` §1・§2。

## 0. 進め方（サインオフの手順）

### 下ごしらえ

```sh
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
export KLAYOUT=/Applications/klayout.app/Contents/MacOS/klayout   # ★
cd <設計を置いた場所>/<design>
python3 $APRTOOLS/apr/selfcheck.py      # klayout モジュール / klayout コマンド / 版
```

> **★ `KLAYOUT` を export する。** `drc_pdk.py` / `lvs_pdk.py` は
> `subprocess` で `klayout` を呼ぶので、**シェルの alias は見えない**
> （`docs/40_gotchas.md` §2-b）。引数付きの alias を使っているなら
> ラッパを 1 枚作ってそれを指す。
>
> `klayout.db` の **pip モジュール**（`lvs_pnr.py` / 抽出が使う）と
> **アプリ**（公式デッキ）は別物。`selfcheck.py` の `--- 0. 実行環境 ---`
> が両方を確認する。
>
> デッキは **0.29 以上**。0.28 では `--allow-old-klayout` で流せるが、
> `size_inside` を使うルール行を外すので**その分だけ検査は緩い**。
> **サインオフは 0.29 以上 か CI で取る。**

### 1) DRC — 3 対象

```sh
python3 $APRTOOLS/apr/drc_pdk.py layout/step10/route_step_6_squeezed.gds <core_top>
python3 $APRTOOLS/apr/drc_pdk.py lef/RING_OSC.gds RING_OSC          # マクロがあれば
python3 $APRTOOLS/apr/drc_pdk.py layout/chip/step3_top_pins.gds <chip_top>
```

**トップセルは必ず明示する**（§1 の実務規則 1）。`layout/step10/` の GDS は
未使用セルが残っていてトップが 13〜15 個ある。

### 2) LVS のソースを組む（**レイアウトを見ずに**）

```sh
python3 $APRTOOLS/apr/mklvsnet.py      # コア: 合成ネット + セル .spice + 配置 JSON
python3 $APRTOOLS/macro/ringosc/mkringoscnet.py   # マクロ: 回路図から
python3 $APRTOOLS/apr/mkchipnet.py     # チップ: 上 2 つ + フレーム + gio_connections.json
```

### 3) 自前の照合（速い。素子とネットのグラフ同型だけ）

```sh
python3 $APRTOOLS/apr/lvs_pnr.py layout/step10/route_step_6_squeezed.gds <core_top> \
        layout/chip/simulation/<core_top>.spice \
        -o layout/chip/simulation/<core_top>.extracted
python3 $APRTOOLS/apr/lvs_pnr.py layout/chip/step3_top_pins.gds <chip_top> \
        layout/chip/simulation/<chip_top>.spice \
        -o layout/chip/simulation/<chip_top>.extracted
```

**これが通っても根拠にならない**（両側 flatten なので階層の不一致が見えない）。
先に流すのは、落ちたときの原因が読みやすいから。

### 4) PDK 公式デッキ（**ここで判断する**）

```sh
python3 $APRTOOLS/apr/lvs_pdk.py layout/chip/step3_top_pins.gds \
        -r layout/chip/simulation/<chip_top>.lvsdb
python3 $APRTOOLS/apr/lvs_pdk.py layout/step10/route_step_6_squeezed.gds <core_top> \
        --sch layout/chip/simulation/<core_top>.spice \
        -r layout/chip/simulation/<core_top>.lvsdb
```

デッキは **GDS の隣の `simulation/<トップセル名>.spice`** しか見ない。
コアの GDS は `layout/step10/` にあってソースは `layout/chip/simulation/` なので、
`--sch` を付ける（`lvs_pdk.py` が一時ディレクトリに並べ直して流す）。

### 5) 提出物とマスクデータ

```sh
python3 $APRTOOLS/apr/export_mpw.py                  # -> src/<chip_top>.gds / .cir
python3 $APRTOOLS/apr/pre_check.py
python3 $APRTOOLS/apr/drc_pdk.py src/<chip_top>.gds <chip_top> --mdp
```

`--mdp` は `run_mdp.drc` でマスクを起こし、そのマスクに `run_IP62.drc` を
当てる（**描画ルールとは別物**。デッキの変数名も違う ―
`run_mdp.drc` は `$input`/`$cellname`/`$output`、`run_IP62.drc` は
`$input`/`$top_cell`/`$report`）。提出前に 1 回は通す。

### 6) 落ちたときに最初に見るところ

| 症状 | だいたいこれ |
|---|---|
| 全ピンが不一致 | **トップポート数が合っていない**（§2「踏んだ穴」1）。1 本ずれるだけで全部倒れる |
| ポートが 1〜2 本だけ不一致 | ラベルだけ置いてピンの実体（M2）が無い（同 2） |
| 素子数が合わない | 折り畳み / デキャップ / `m=2`。**素子数で比較しない**（同 3） |
| 短絡に見える | `SPICE は大小を区別しない`。`web` と `WEB` が潰れている（同 4） |
| 同一構造のブロックでピンが入れ替わる | KLayout が恣意的に対応を決めている。**ラベルで固定**（同 6） |
| 何も実行されない / レポートが出ない | レポートのパスが相対。`drc_pdk.py` は絶対パスにしている |

### 2026-09-15 の実測（移行後・`vdd`/`vss` 統一後）

**設計機で PDK 公式デッキを完走。サインオフ相当。**

| 対象 | DRC | LVS |
|---|---|---|
| コア `route_step_6_squeezed.gds` | **0 件** | **23/23 回路ペア Match**（トップピン 26） |
| `RING_OSC` | **0 件** | チップ側の比較に含まれる |
| チップ `step3_top_pins.gds` | **0 件** | **35/35 回路ペア Match**（トップピン 16） |
| 提出 GDS `src/<chip_top>.gds` | **0 件** | — |
| MDP マスク（`run_mdp` → `run_IP62`） | **0 件**（マスク 5.4 MB） | — |

> **★ 「デッキを完走した」ことをレポートから確かめる方法。**
> `--allow-old-klayout` は `size_inside` を使うルール行を**コメントアウト**
> するので、そのルールは**カテゴリごとレポートに現れない**。
> つまり `.lyrdb` に `M1P.PE` / `M2P.PE` があれば完全版で流れている。
>
> ```sh
> grep -c "M1P.PE" <report>.lyrdb     # 1 なら完全版、0 なら緩い方
> ```
>
> 実際: 設計機の報告はルール 266 本で `M1P.PE` / `M2P.PE` を含む。
> 0.28 + `--allow-old-klayout` は 263 本でこの 2 本が無い。
> **「0 件」だけでは、通ったのか見ていないのか区別が付かない。**

LVS の合否は**デッキの標準出力**（`Congratulations! Netlists match.`）で
出るが、後からでも `.lvsdb` から確かめられる:

```python
import klayout.db as db
lvs = db.LayoutVsSchematic(); lvs.read("<report>.lvsdb")
for cp in lvs.xref().each_circuit_pair():
    print(cp.status(), cp.first().name if cp.first() else "-")
# すべて Match (1) なら一致
```

> **★ 電源名の改名は公式 LVS を壊さない**（確認済み）。
> `05_Compare.lvs` は電源ネット名を直接見ておらず、`IP62/01_Extract.lvs` の
> `connect_global(BULK, "VSS")` も SPICE の大小無視で `vss` と同一視される
> （`docs/40_gotchas.md` §1-5）。

参考: 同じものを x86_64 / KLayout 0.28.16 + `--allow-old-klayout` でも流して
DRC 0 / `Netlists match` を得ている（**緩い方なのでサインオフではない**）。

## 1. DRC — 2 段構え

| 段 | スクリプト | 見る範囲 | 用途 |
|---|---|---|---|
| ルータの検算 | `apr/drc_check.py <gds> <top>` | M1/M2/V1 の**幅と間隔だけ** | step ごとの早期検出 |
| セル単体 | `apr/from_sclk_spi/drc_check_cells.py [cell]` | STDCELL 全セル | **GDS を触ったら回す** |
| **公式** | `apr/drc_pdk.py <gds>` | `$TR1UM_PDK/libs.tech/klayout/tech/drc/run.drc` 全ルール | **サインオフ** |
| MDP 後 | `apr/drc_pdk.py <gds> --mdp` | `run_mdp.drc` → `run_IP62.drc`（マスクデータ） | 提出前 |

### 自作チェッカが実装していないルール

| ルール | 内容 |
|---|---|
| **`M1.SW`** | 幅 10 µm 以上の M1（`M1W = M1.sized(-5.0).merged.sized(5.0)`）に接する M1 は**間隔 2.0** |
| **`M1.W3` / `M2.W3`** | M1 / M2 の**最大幅 45 µm** |
| `M1.SCR` / `M2.SCR` | スクライブ領域との間隔 5.0 |
| `M1P.PE` / `M2P.PE` | パッド引き出しは 14 µm にわたり 40 µm 幅 |
| `V1.CO` / `V1.CL` | V1 – CO 間隔 1.0 / 1.4（重なり禁止） |
| `M1.CO` / `M1.CC` / `M1.CL` | M1 の CO 囲み 0.8 / 1.3 / 1.2 |

値の一覧は `docs/10_pdk_facts.md` §3。

> **⚠ チップの電源バスバーは幅ちょうど 10.0 µm で `M1W` の判定境界に乗っている。**
> 「10.0 だから太線扱いされない」と当てにせず、周囲 2.0 µm を空ける。

### ★ 3 つの実務規則

1. **チェッカにトップセルを必ず明示する。**
   `TOP_CELL` がハードコードされていた時期があり、チップレベル GDS への呼び出しが全部
   入れ子のコアセルだけを検査していた。**その期間の「0 violations」は全部無意味**で、
   実 KLayout DRC が違反 50 件を検出した
2. **DRC は差分で見る。** パッドリングは元から幅・間隔マーカーを数個持っている。
   配線前後の両方で走らせ**増えた分だけ**を座標付きで報告する
3. **判定は「未満が違反」。** ちょうどは合法（ロゴのドット設計がこれに依存）

### KLayout のバージョン

デッキは **0.29 以上**（`02_Device.drc` の `size_inside`、`05_Compare.lvs` の
`flag_missing_ports`）。0.28 では `--allow-old-klayout` で該当行を外した写しを流すが、
**その分だけ検査が緩い**。CI は 0.30.9。**最終判断は CI。**

## 2. LVS — 3 階層

| トップ | ソースの出どころ | スクリプト |
|---|---|---|
| コア | 合成ネットリスト + `stdcell/v59_4/simulation/*.spice` + 配置 JSON の物理セル | `apr/mklvsnet.py` |
| マクロ / TEG | **その回路図**（xschem の `.sch`） | `macro/ringosc/mkringoscnet.py` ほか |
| チップ | 上 2 つ + フレーム（`--no-combine` 版）+ `gio_connections.json` | `apr/mkchipnet.py` |

**★ ソース側はレイアウトを見ずに組み立てる**（同語反復を避ける）。例外は 2 つだけ:
- `FILL2`（デキャップ。回路図が無いのでレイアウト抽出を golden として凍結）
- RING_OSC の `FILL2` の**個数だけ** GDS から数える（回路図の 206 個と一致確認のうえ）

### 自作と公式

```sh
python3 apr/lvs_pnr.py <gds> <top> <spice> -o <out.extracted>   # 速い。素子とネットのグラフ同型だけ
python3 apr/lvs_pdk.py <gds> -r <out.lvsdb>                     # PDK 公式。サインオフ
```

`lvs_pnr.py` は既定で**両側 flatten**（`--hier` で階層のまま）。
**PDK デッキは階層で比べるので、flatten では見えない不一致がある**
（APR_2026 の出力パッド 5 本がこれで自作側だけ素通りした）。

`lvs_pnr.py` は flatten の前に**並列 MOS を両側でまとめる**
（`combine_parallel_mos()`。`--no-parallel` で止まる）。`MUXDFFRB` のように
マルチフィンガで描いたセルがあると、まとめないと素子数がインスタンス数の
整数倍でずれる（U92）。KLayout 自身の `combine_devices()` は内部エラーで
落ちるので使っていない（§1-6 / `docs/40_gotchas.md`）。

### デッキの参照規約

- `05_Compare.lvs` の `Sch_file = "simulation/" + source.cell_name + ".spice"`
  → **GDS を置いたディレクトリの `simulation/<トップセル名>.spice`**
- **`-rd circuit=…` / `extracted=…` はレイアウト GDS のあるディレクトリからの相対**
  → 渡すのは**ファイル名だけ**（パスを付けると `.../src//src/xxx.cir (errno=2)`）
- **`run.lvs` の `%include` が全部コメントアウトされている**（`lvs.lylvs` の
  `# %include run.lvs` も）。**外さないと何も実行されない**

### 揃えること

| 項目 | 値 |
|---|---|
| モデル名 | 大文字 `PMOS` / `NMOS` |
| 素子行 | `M<name> D G S B <model> W=..u L=..u`（4 端子） |
| 許容差 | **`W = 1%` / `L = 0%`** — L はぴったり `1.0u` でないと不一致 |
| バルク | PMOS → `vdd`、NMOS → `vss` |
| バス表記 | 角括弧 |
| フィラー | **ソース側にも入れる**（`FILL2` / `FILL3` = 2T のデキャップ）。`TAP2` はデバイスを持たないので出さない |
| ラベル層 | **(48,0) / (49,0) だけが読まれる** |
| `combine_devices()` | **両側とも掛けない**（`DFFRB` で KLayout 内部エラー）。フレームは `mkframespice.py --no-combine` 版 |

### ★ 踏んだ穴（`docs/40_gotchas.md` §1 に全件）

1. **トップポート数が合わないとグラフ照合に入らず、全ピンが将棋倒しで不一致になる**
2. **ラベルだけではサブサーキットのピンが生えない** → M2 の実体も置く
3. **素子数で比較しない**（折り畳み・デキャップ・`m=2`）→ 折り畳み不変量で比較
4. **SPICE は大小を区別しない** → `web` と `WEB` が同一ネットに潰れて短絡に見える
5. **階層のままの `MUXDFFRB` は照合できない** → `x1_`/`x2_` で展開
6. **構造的に同一なサブ回路はピン対応が恣意的に決まる** → ラベルで固定する
7. **直列スタックの並び順**を回路図と合わせる
8. **説明のつかないポートは固有の `NC_*` で個別に浮かせる**（まとめると偽のショート）
9. **step10 の GDS はトップセルが 15 個**（未使用セル + `$$$CONTEXT_INFO$$$`）→ セル名を明示

### タグ `v1.2609.0` のデッキ不具合

`05_Compare.lvs` に **`equivalent_pins` 宣言が 14 行分無い**
（`AND2_X1` `AND3_X1` `AND4_X1` `NAND2-4` `NOR2-4` `OR2-4` `XOR2` `XNOR2`）。
同じ差分で `success = compare && flag_missing_ports` が短絡評価になっており、
**`compare` が落ちると `flag_missing_ports` が一度も呼ばれない**（診断が何も出ない）。
`dev` ブランチでは修正済み。

## 3. 抽出

```sh
python3 apr/klayout_extract.py <gds> <top>     # 階層とラベルを残したまま抽出（ngspice 用）
python3 apr/gds_extract.py                     # セル単体の抽出（char 用）
```

- `lvs_pnr.py` が出す `*_lay.spice` は**比較専用**。トップに `.SUBCKT` ポートが無く、
  ネット名が番号、素子が `M…`。**ngspice には使えない**
- `.extracted` を素の `NetlistSpiceReader` で読むと**デバイスでなく subckt 呼び出しに見える**
  （実測: circuit 94 / device 0）。読み戻すならデリゲートが要る
- **ESD 素子はモデルが別物**（`OSS_PCH_DRV`/`_ESD` → `MPE`、`OSS_NCH_*` → `MNE`）。
  抽出では PMOS 側が ESD でも `PMOS` と書かれるので**囲っているサブサーキット名で判定する**

## 4. 実績

| 対象 | 素子 / 網 / ピン | DRC | LVS |
|---|---|---|---|
| APR_2026 コア | 1852 / 737 / 26 | 0 | 一致 |
| APR_2026 `RING_OSC` | 808 / 201 / 5 | 0 | 一致 |
| APR_2026 チップ | 3288 / 1050 / 16 | **0** | 一致 |
| **同上・移行後（`vdd`/`vss`）2026-09-15** | ピン 26 / 16 | **0**（+ MDP 0） | **23/23・35/35 Match** |
| TD4 コア（縦置き step11） | 3597 / 1386 / 16 | 0 | 一致 |
| TD4 チップ | 4225 / 1503 / 16 | 0 | 一致 |
| **同上・APRtools で再現 2026-09-15** | **同じ数字** | **0**（+ MDP 0） | **一致**（ngspice 12/12） |
| SCLK_SPI コア | 27 ポート / 13 サブサーキット | 0 | 一致 |
| MDP 後マスク | — | **0** | — |

## 5. メモリマクロ LVS の教訓（TD4・全 5 回）

汎用性があるのでここに残す。

| 回 | 症状 | 真因 | 対処 |
|---|---|---|---|
| 1 | 抽出 `DEC0` が 6 素子（参照 16）、160 素子がトップに昇格 | KLayout の deep 抽出は**複数セルにまたがるデバイスを親に昇格**する | **`DEC2` を最小単位に**する |
| 2 | ピン 18 本 vs 記述 19 本 | ① デコード入力は 2 行で物理共有（アドレスピンは 5 本）② ウェル／基板タップが無く電源ピンが 4 本（`vdd/vss/vnw/vsub`） | 記述側を直す |
| 3 | 不一致（ピン数は一致） | **直列スタックの並び順**（NAND4 の NMOS は vss 側から bit3..bit0、NOR2 の PMOS は vdd 側から WEB,RDB） | 修正 + `apr/netcmp.py`（networkx VF2）で事前検証 |
| 4 | `Port mismatch 'ADD[0]' vs 'ADD[3]'` 系 4 件 | `ADDBUF` は**構造的に完全同一**。レイアウト側のピンが無名だと KLayout が**恣意的に対応を決める** | `apr/add_addbuf_labels.py` でラベルを貼る。**ソース修正は不要** |
| 5 | `WEB` `$I75-77` の 4 ネット | ① **SPICE の大小無視**で `web` と `WEB` が潰れた ② bit0 の A0/AB0 が逆割当 | 内部線を **`WEBI`** に改名 + ラベル追加 |

**ラベル層の鉄則**（半日溶かした）: デッキは `labels(48,0)` / `labels(49,0)` からしか
テキストを拾わない。48/1・49/1 に置いても無視される。

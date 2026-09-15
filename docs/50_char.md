# セル特性化

対象: `char/`（`loadext.py` / `cellspec.py` / `charlib.py` / `char_comb.py` / `char_seq.py` /
`char_latch.py` / `char_mem.py` / `char_pad.py` / `calib_cap.py` / `genjobs.py` /
`runjobs.sh` / `collect.py` / `mklib.py` / `verify_lib.py` / `mkcellverilog.py` / `mkmemsrc.py`）

**セルライブラリ単位で共通**。設計に依存しない。出力 `tr1um_typ_5v0_25c.lib` も共通資産。

## 1. 3 段構成

**生成 → 実行（並列）→ 回収**。往復するのは `results.txt` 1 本だけ。

```sh
# 0) 抽出ネットリストを読み込む（PDK モデルは TR1UM_PDK から参照）
python3 char/loadext.py ../stdcell/v59_4/extracted -o cells_ext
export TR1UM_CELLDIR=$PWD/cells_ext
export TR1UM_CELLEXT=.spi

# 1) デッキ生成
python3 char/genjobs.py -o pack           # 14,179 本・約 70 MB

# 2) 実行
./char/runjobs.sh -j 18                   # 18 コアの Mac で 10〜20 分

# 3) 回収と .lib 生成
python3 char/collect.py -p pack
python3 char/mklib.py -o ../stdcell/v59_4/tr1um_typ_5v0_25c.lib
python3 char/verify_lib.py ../stdcell/v59_4/tr1um_typ_5v0_25c.lib
```

`cells_ext/` `pack/` `decks/` `logs/` は**生成物なのでコミットしない**
（`pack` は 127 MB）。コミットするのは `char/`（セルごとの結果 JSON）と `RESULTS.txt`。

## 2. デッキ内訳（14,179 本）

| 種別 | 本数 | 内容 |
|---|---:|---|
| delay | 686 | 組合せの `cell_rise`/`cell_fall`・出力遷移（7×7） |
| cap | 49 | 入力容量 |
| calib | 124 | `INV_X1` で N 個駆動して求める等価容量 |
| ckq | 56 | CK→Q（7×7） |
| **setup** | **6,624** | 3×3 × 立上下 × dt 掃引 92 点 |
| **hold** | **6,624** | 同上 |
| verify | 12 + 4 | |

格子: SLEW 0.1〜16 ns / LOAD 10〜800 fF、NLDM 7×7。

### ★ setup/hold は二分探索でなく掃引

二分探索は前の結果に依存するので**並列化できない**。掃引なら全点が独立で、
境界付近を 0.25 ns 刻みにすれば**分解能はむしろ良い**。

## 3. ★ 並列数

**ngspice を並列に走らせすぎない。**
2 コア環境で 2 本同時に走らせると**逐次 2.0 秒の仕事が並列 99 秒**（50 倍）。
ngspice は 1 プロセスで複数スレッドを使おうとし、コア数を超えると桁違いに遅くなる。

- `OMP_NUM_THREADS=1` は効かない
- `pack/.spiceinit` の `set num_threads=1` も**ビルドによっては効かない**
- `charlib.NPROC = 1` に固定してある
- **1 本/秒を大きく下回るなら `-j` を下げる**（18 コアの Mac なら `-j 18`、クラウド 2 コアなら逐次で約 2 時間）

`runjobs.sh` は**再開可能**（結果のあるデッキは飛ばす）。

## 4. 抽出まわりの穴

### ★ 辺で接する図形は boolean `"or"` で繋がらない

`gdstk.boolean(a,b,"or")` は辺を共有するだけの図形を 1 枚にまとめないことがある。
XOR2 で電源スタブ 2 本の片方が別ネットに割れ、「出力がフルレールに振れない」
**偽の不具合**に見えた。

→ `gds_extract.merge()` で **0.01 µm 膨らませてから結合**
（最小間隔は M1 で 1.4 µm あるので誤結合しない）。
ゲート–拡散の接触判定も `bbox` 膨張ではなく `gdstk.offset` で
（bbox だと `FILL2`/`FILL3` の **L 字のゲート**で片側の拡散を取りこぼす）。

### ★ ラベルは層を合わせて拾う

層をまたいで拾うと M2 のつもりのラベルが真下の M1 電源レールに付いて
**電源ネットが信号名に化ける**（`REGBUF` で `DD`/`QQ` が vdd レールに付いた）。

### その他

- **チャネル長を 1.0 µm 決め打ちにしない。** `DEL1` の遅延段 4 個は L=2.0 µm、
  `FILL2`/`FILL3` のデキャップは L=3.2 / 8.6 µm
- **ソースとドレインが同じネットに落ちるのは異常ではない**（デキャップ）
- `\$6` / `XM$1` の `$` は ngspice のコメント文字なので `loadext.py` が `n6` / `XM1` に置換

## 5. `verify_lib.py` の 4 段

全部「逸脱なし」なら使える。

| 段 | 内容 | 実績 |
|---|---|---|
| 1 | 表の健全性（欠損なし・負荷単調） | — |
| 2 | **格子の外**（slew 1.0 ns / CL 150 fF）での ngspice 実測との差 < 15% | **0.2〜1.0%** |
| 3 | 入力容量の妥当性 < 20% | **0.2〜2.5%** |
| 4 | `.lib` 構文 | — |

`collect.py` の注記: 「掃引の下端でも取り込めた」= setup/hold に余裕があり境界が −20 ns より下
（**値は −20 で頭打ち**）、「単調でない」= 刺激かセルを疑う。

## 6. `RESULTS.txt`（2026-09-11）

| 対象 | 結果 |
|---|---|
| 組合せ 21 セル | PASS 140 / FAIL 0 |
| 順序 5 セル | PASS 79 / FAIL 0 |
| `FILL2` 容量 | 293.9 fF（うちゲート分 163.7 fF） |
| `FILL3` 容量 | 570.3 fF（うち 439.9 fF） |
| リーク | 0.00 pA |

## 7. クロス結合セル（`RSLATCH`）の測り方

```sh
./char/run_rslatch.sh -j 18       # デッキ 136 本、1 分未満
```

| 項目 | 値 |
|---|---|
| 入力容量 S/R | 電荷から 76.7 fF → **較正後 60.5 fF**（比 0.79、N=2/4 のばらつき 3.7%） |
| S→Q / R→QB（preset） | slew 0.6 ns / CL 50 fF で **2.676 ns** |
| S→QB / R→Q（clear） | 同条件 **1.242 ns** |
| 最小 High パルス幅 | **1.85 ns**（等比 10% 刻み掃引なので分解能 10%） |
| area | 1603.8 |

規則:
- **測る前に反対側の入力で初期化する**（t=0〜20 ns 反対側を VDD、21 ns で放す、100 ns で測る側を振る）
- **アクティブ端にしかアークが立たない**（preset/clear の片方向表）
- クロス結合なので反対側は 25 fF 固定
- **`dont_use` を付ける**（RTL で明示インスタンスする前提。ABC に SR ラッチを勝手に組ませない）
- **S と R が同じ値になるのが正常。片方だけずれたらレイアウトを疑う**

## 8. パッドセル（`char_pad.py`）

`OSS_ESD_5V_DIO` の特性は `docs/11_frame_io.md` §4。
`.lib` では `pad_cell : true` / `dont_use : true` / `dont_touch : true` /
`function : "OUT"` / `three_state : "HIZ"`。

## 9. ★ 未解決 — `char_mem.py`

**抽出ネットリストでは書込みが効かない。**
`stdcell/v59_4/simulation/REG8x16.spice`（設計ネットリスト）では動くが、
`extracted/REG8x16.extracted` を同じ刺激で回すと**どのアドレスを読んでも 5 V**。

切り分け済み:

| 条件 | 結果 |
|---|---|
| そのまま | 動かない |
| `AS`/`AD` だけ外す | 動かない |
| **`PS`/`PD` だけ外す** | **動く**（22.28 ns → 21.81 ns） |

`PS < W` のような異常値は 1,876 素子中 0 件で、値も PDK 既定式 `2*(sdwidth+w)` と桁が合う。
PDK モデル（`models_IP62_mos_v2.lib` の `.subckt PMOS` → `M1 … ps=ps pd=pd`）の解釈を
追う必要がある。**当面は設計ネットリストで測る。**

## 10. 副産物

| スクリプト | 出力 |
|---|---|
| `mkcellverilog.py --power --delay 1` | `tr1um_cells.v`（26 セルの振る舞いモデル。合成の段 0） |
| `mkmemsrc.py` | メモリ特性化用の刺激 |
| `cellspec.py` | **セル仕様の唯一の出典**（ピン・方向・機能） |

## セル台帳と Liberty（2026-09-15、`from_sclk_spi/` 統合で `apr/` へ）

```sh
python3 apr/sync_cell_info.py     # -> stdcell/<世代>/cell_char.json
python3 apr/gen_liberty.py        # -> stdcell/<世代>/TR1um_5_stdcell_area.lib
python3 apr/drc_check_cells.py    # セル単体 DRC（v59_4 は 52/52 clean）
```

### ★ `cell_info.json` と `cell_char.json` は**別物**

同じ名前を使っていたので `gen_liberty.py` に幾何だけの JSON が渡って
`KeyError: 'kind'` で落ちた（統合してすぐ踏んだ）。

| | 作る人 | 中身 | 置き場 |
|---|---|---|---|
| `cell_info.json` | `apr/mkcellinfo.py` | **幾何だけ**（`width_um` / `height_um` / `sites` / `cls`） | **設計の** `layout/` |
| `cell_char.json` | `apr/sync_cell_info.py` | **特性化の台帳**（`area_um2` / `transistors` / `kind` / `in_pins` / `out_pin` / `function`） | **APRtools の** `stdcell/<世代>/` |

配置配線が要るのは前者、Liberty が要るのは後者。
`gen_liberty.py` は `kind` が無ければ**何が足りないかを言って止まる**。

### v59_4 の実績（2026-09-15）

- `cell_char.json` **48 セル**
- `TR1um_5_stdcell_area.lib` **21 セル**（論理関数が定義されているもの）
- 論理関数が無い 17 セル（`REG8x16` / `TLAT*` / `DEC*` / `ADDBUF` …）は
  ABC が使えないので Liberty に出ない。**マクロと latch は合成に出さない**
  方針どおり
- **トランジスタ数は GDS だけから数える**（`.extracted` は使わない。U49）。
  数え方は `combine_devices()` → `flatten()` → 素子を数える、の順:
  - **combine しないと折り返しを二重に数える**。`BUFTH` の w=10.2u PMOS は
    2 フィンガーで描いてあるのでゲート図形は 10 枚だが、素子は 8
  - **flatten しないと階層セルを 1 回しか数えない**。`REG4x16` は `TLAT` を
    64 個並べているのに、`TLAT` という回路は 1 つしか無い
  検算になる関係（どれも実測と一致する）:

  | セル | 内訳 | Tr |
  |---|---|--:|
  | `TLAT8` | 8 × `TLAT`(12) | 96 |
  | `DEC16` | 8 × `DEC2`(32) | 256 |
  | `REG4x16` | `TLAT64`(768) + `REGBUF4`(32) + `DEC16`(256) + `ADDBUF`(20) | 1076 |
  | `REG8x16` | `TLAT128`(1536) + `REGBUF8`(64) + `DEC16`(256) + `ADDBUF`(20) | 1876 |

  **大きさの違うセルが同じ数になっていたら、数え方が壊れている合図**
  （`TLAT4` も `TLAT128` も 12 と書いてあった時期がある）。
  `FILL*` / `TAP*` は素子が本当に 0。`--set CELL:transistors=N` で上書きできる

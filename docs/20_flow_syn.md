# 合成 → ネットリスト加工 → STA

対象: `syn/`、`apr/`（`dedup_gates.py` / `merge_muxdffrb_rslatch.py` / `insert_bufth.py` /
`insert_row_buffers.py` / `gen_liberty.py` / `syn_report.py` / `cmp_cells.py`）

## 0. `syn/syn.sh` は `config.py` で動く（2026-09-15）

```sh
cd <設計>
export APRTOOLS=... ; export PYTHONPATH=$APRTOOLS/apr
sh $APRTOOLS/syn/syn.sh          # 引数も環境変数も要らない
```

以前は I2C の値（RTL の場所・トップ名・abc 制約・BUFTH のネット・V10 の参照
ネットリスト・周期）が `syn.sh` に直書きで、**TD4 でも SCLK_SPI でも
回らなかった**（U36）。いまは全部 `config.py` から取り、**与えられた段だけ
回る**。

| config.py | 効く段 |
|---|---|
| `SYN_RTL` / `SYN_TOP` / `SYN_LIB` / `SYN_CONSTR` | 2 |
| `SYN_CELLS_V` / `SYN_CELLS_GEN` / `SYN_CELLS_IN_SYNTH` / `SYN_CELLS_ARGS` | 0・1・5 |
| `SYN_BLACKBOX` | 2 |
| `SYN_TB_RTL` / `SYN_TB_NET` / `SYN_TB_INCDIR`（**リスト**） | 1・5 |
| `BUFTH_NETS` | 6 |
| `SYN_REF_NETLIST` | 8 |
| `STA_CLK_PORT` / `STA_PERIOD_NS` / `STA_FALSE_PATH_FROM` | 9 |
| `SYN_OUT_DIR` / `NET_PATH` | 出力 |

`SYN_CELLS_IN_SYNTH` は **RTL がセルを直接インスタンス化している設計だけ**
（I2C の NOR2 クロス結合 SR ラッチ）。SPI / TD4 は素の RTL なので `False`。
`SYN_CELLS_GEN` を `True` にすると `char/mkcellverilog.py` で起こす。
**手書きのセルモデルはライブラリから静かにずれる** — SCLK_SPI の
`hdl/cells_sim.v` には `INV_X2` が無く、ABC が選んだ瞬間にゲート TB が
コンパイルできなくなった（U38）。

> **★ TD4 は対象外。** トップが 4 つあり、`td4_mem` をブラックボックスで
> 合成してから `mem_wrap.py` で実物の `REG8x16` に差し替える段が要る。
> TD4 は `scripts/syn.sh` のまま（再合成すると U31 でネットリストが変わる
> ので、再現には触らない）。STA だけは `syn/sta/sta.sh` で回せる。

## 1. 段構成

| 段 | 内容 | 出力 |
|---|---|---|
| 0 | `char/mkcellverilog.py --power --delay 1` | `hdl/rtl/tr1um_cells.v`（セルの振る舞いモデル 26 個） |
| 1 | iverilog で RTL 機能検証 | All checks PASSED |
| 2 | Yosys + ABC | マップ後ネットリスト |
| 3 | **`dedup_gates.py`** | 冗長インスタンス削除 |
| 4 | **`merge_muxdffrb_rslatch.py`** | `MUX2` + `DFFRB` → `MUXDFFRB` |
| 5 | ゲートレベル TB 再実行 | All checks PASSED |
| 6 | **`insert_bufth.py --nets …`** | 入力に `BUFTH` 挿入 |
| 6b | **`insert_row_buffers.py --rows N`** | 行ごとのクロックバッファ |
| 7 | `syn_report.py` | 面積・使用率 |
| 8 | `cmp_cells.py` | 前世代との差分表 |
| 9 | `sta/sta.sh` | STA |

段の並びと `--nets` の中身は**設計固有**。`build.sh`（`templates/`）が環境変数で受ける:
`TOP` / `SRC` / `ROWS` / `LIB` / `BUFTH_NETS` / `CLK_NETS` / `ROW_ASSIGNMENT`。

## 2. Yosys

```
read_verilog <cells.v> <rtl>
blackbox RSLATCH
hierarchy -check -top <TOP>
synth -top <TOP> -flatten
dfflibmap -liberty <lib>
abc -liberty <lib> -constr syn/abc.constr
opt_clean
```

Yosys の探索順: `$YOSYS` → `yowasp-yosys` → `yosys` → `~/.local/bin` → `yowasp_yosys` の
Python ラッパ生成。

### ★ `blackbox RSLATCH` が要る理由

無いと `tr1um_cells.v` の振る舞いモデルが展開され、ABC が入力ゲートごと吸収して
**`NOR3`/`NAND3` の生ループ**に化ける（v10 では組合せループが 4 個できた）。

### ★ セルモデルは `-lib` ではなく普通の Verilog として読む

`-lib` だとブラックボックスのまま残り、後段の `merge` が効かない。

### `abc.constr`

`set_driving_cell BUF_X2` / `set_load 36.2`（= `OSS_ESD_5V_DIO` の `OUT` 入力容量）。

## 3. Liberty

| ファイル | 用途 |
|---|---|
| `stdcell/v59_4/tr1um_typ_5v0_25c.lib` | **実特性化版**。合成・STA ともこれを使う |
| `apr/from_sclk_spi/gen_liberty.py` | `cell_info.json` → 実面積だけの Liberty（面積見積り専用） |
| `syn/tr1um.genlib` | ABC 用 genlib（面積は GDS 実測、**遅延はプレースホルダ**） |

> **★ 遅延がプレースホルダの Liberty は STA に使えない。** 面積・ゲート規模の見積もり専用。

## 4. ネットリスト加工

### `dedup_gates.py` — ★ 必ず最初に通す

ABC は同じ入力に繋がった同じセルを何個も撒く。それが**配線の混雑と短絡の真の原因**になる。
実測: 5 グループ / 35 冗長インスタンス削除。

### `merge_muxdffrb_rslatch.py`

`MUX2` + `DFFRB` のペアを `MUXDFFRB` に畳む。引数化済み
（`--mux-cell` / `--ff-cell` / `--merged-cell` / `--d-pin`）。
実測: I2C で 17 対、SPI で 15 対（面積 −13,005 µm²）。

> **★ STA は必ず merge 後に当てる。** 畳み込み前は `NOR2` のクロス結合が生ループとして残り、
> OpenSTA が勝手にアークを 1 本切る。

### `insert_bufth.py --nets a,b,c`

入力パッドから来るネットに `BUFTH` を挿入する。**パッドが駆動するのは `BUFTH` 1 個
（`A` 容量 63.4 fF）だけ**になる（以前は `CLK` がパッドから 25 個の FF を直接叩いていた）。
STA 実測では `reg→reg` は不変、`in→reg` だけが増える。

### `insert_row_buffers.py --rows N [--row-assignment …]`

行ごとに 1 個のクロックバッファを入れる。
**`place.py` の行割り当て結果を `--row-assignment` で戻す 2 パスが正規手順。**
実測（SPI）: チャネル交差 [11,6,6] → [10,5,7]、コア高 286.2 → 280.8 µm。

> **⚠ クロック分配の確認項目**: 2 行構成では 1 つの行バッファが最大 1.29 mm の行全体の
> FF クロックピンを駆動する。M2 配線容量が 6 個の CK ゲート容量と同等以上なので
> **クロック枝は配線容量支配**。`BUF_X2`（W=20.4/6.8 µm）で足りるかは
> **レイアウト抽出後の SPICE で確認**すること。足りなければ `BUF_X4` の実装が素直。

## 5. STA

```sh
sh syn/sta/sta.sh <netlist> <top> <period_ns>
sh syn/sta/sta.sh <netlist> <top> <period_ns> syn/sta/path.tcl   # クリティカルパス詳細
```

`sta.sh` が `NET`/`TOP`/`PER` を先頭に置いて `setup.tcl` + レポート tcl を連結する。

### ★ クロックの無いコアで `周期 − slack` を使わない

最悪パスが半サイクルパス（例: `scl_n` ↔ `scl_gated`）だと正しく出ない。
最初これで「Fmax 0.78 MHz」という誤報を出した。

→ **周期を 2 点振って `slack(T) = a·T + b` を解く。**
実測（I2C）: 周期係数 a = 0.50、reg→reg が要求する最小周期 49.104 ns（20.36 MHz）。

### いま入っていない前提

- **配線容量ゼロ**（P&R 前なのでネット容量は駆動セルの負荷だけ）。
  **TR-1um の M2 は幅 3.4 µm と太いので、実配線が乗ると悪化する**
- **クロックツリー無し**（`set_ideal_network` で skew 0）
- `RSTB` の `recovery` / `removal` と `min_pulse_width` が未特性化（U8）。
  TD4 / I2C はリセットが**電源投入時に一度きり**なので `set_false_path` で正しいが、
  **SCLK_SPI の `cnt_rstn = rstn & ~cs_n` はフレームごとに解除される**ので
  前提が成り立たない（20 FF 中 4 個。余裕は半周期あるが**測っていない**）
- `REG8x16` は**読出しも書込みも** `.lib` に入った（U7、2026-09-16）。
  ただし **STA が実際に見るものは限られる**。OpenSTA 3.1.0 で確認した:

  | `.lib` の中身 | OpenSTA は | 条件 |
  |---|---|---|
  | `ADD -> Q` / `WEB -> Q` の組合せアーク | **見る** | — |
  | `ADD` / `D` の `hold_rising`（6.0 ns）| **見る** | ★ **`WEB` がクロックとして伝播しているときだけ** |
  | `WEB` の `min_pulse_width`（11 ns）| **見ない** | 記録として置いてあるだけ |

  ★ **`WEB` がクロックから作られていれば、宣言は要らない**（2026-09-16、TD4 の実設計で確認）。
  TD4 の `WEB` は `mem_wrap.py` が置く `OR2(clk_buf, ~wr_hi)` なので、`clk` の
  クロックネットワークがそのまま伝播し、`library hold time 6.000` が出た。
  **`WEB` が外から入る独立した線のときだけ**、設計側で当てる:

  ```tcl
  create_clock -name WEBCK -period <周期> [get_pins <マクロ>/WEB]
  ```

  ★ **`setup` は Liberty に書いていない**ので、マクロへ向かう最長パスは
  「パス無し」になる。**これが正しい姿**（測っていない数字は書かない。U7）。

  ★ **マクロを使う設計は `STA_MACRO_INSTS` を書くこと。**
  `syn/sta/report_macro.tcl` が連結され、上の表のどれが実際に効いたかが
  出力に現れる。**「Liberty に書いた」で終わりにしない**（U73 / U74）。

  ★ **最小ローパルス幅は STA では担保できない。** ライブラリに書いても
  `clock : true` を足しても違反が出ず、`set_min_pulse_width` はピンに
  当てると無反応、クロックに当てると**別のピンを検査する**。
  **ngspice の回帰で見るしかない**（`char_mem.py --web-low` の掃引）。
  数字は `char/char/REG8x16.json` の `limits.weblow`。

- **論理的にあり得ないパスは、根拠を制約の隣に書いて外す**（`STA_EXTRA_TCL`）。
  TD4 の例（`TR-1um_TD4/scripts/sta_constraints.tcl`）:

  | 外したもの | 根拠 |
  |---|---|
  | `WEB -> Q`（書込み中に `Q` が追従する経路）| 書込みは `exec=0` のときだけ。そのとき `en = exec` でコアの FF は全部止まっている。**捕まえる FF が 1 つも無い** |
  | `nib_lo -> u_mem/D`（データ保持 6.0 ns）| `nibsel` が、書込みを終える `WEB↑`（=1）と `nib_lo` の取り込み（=0）を**逆の極性で排他に選ぶ** |

  ★ **当たった個数を必ず出す。** 名前が変わって 0 個に当たっても SDC は
  無言で通る（U74 と同じ「回っていないのに OK」）。

### OpenSTA のビルド

リポジトリには入れない。macOS Apple Silicon の罠は `docs/40_gotchas.md` §8-6。

## 6. 規模レポート

| スクリプト | 内容 |
|---|---|
| `syn_report.py` | セル幅総和、FF / 組合せ の内訳、NAND2 換算ゲート数 |
| `apr/from_sclk_spi/gate_count.py` | 各段のネットリストの規模。`--density` 既定 **0.278**（I2C 実チップの実測論理セル密度 = 0.426 mm² ÷ 1.533 mm²） |
| `apr/area_estimate.py` | Yosys の `stat` 出力から面積見積り（`stdcell/v59_4/cell_area.json` を使う） |
| `apr/cmp_cells.py` | 前世代とのセル構成差分 |
| `apr/from_sclk_spi/explore_rows.py` | 行数の検討 |

1 等価ゲート = `NAND2` = 4 Tr = 16.2 × 59.4 = **962.3 µm²**（v59_4）。

## STA（`syn/sta/`、OpenSTA）— 2026-09-15 に設計非依存化

Liberty・クロックポート・false path を**設計の `config.py`** から取るようにした。
`setup.tcl` に `read_liberty lef/…` と `create_clock … [get_ports scl]` が
直書きされていて、STDCELL を正本へ移したあとも**設計の写しを読んでいた**。

```python
# 設計の config.py
SYN_LIB = None                   # 既定 = stdcell_file("tr1um_typ_5v0_25c.lib")
SYN_TOP = "spi_slave_sclk"
STA_CLK_PORT = "sclk"            # クロックを入れるポート
STA_PERIOD_NS = 100.0
STA_FALSE_PATH_FROM = ["rstn"]   # recovery/removal は未特性化なので外す（★ U8:
                                 #   外してよいのは「電源投入時だけのリセット」
                                 #   と確かめた設計だけ。設計ごとに見ること）
STA_NON_SIGNAL_PORTS = []        # 構造セルの電源ポート（I2C は VDD/GND）
```

```sh
export PYTHONPATH=$APRTOOLS/apr        # sta.sh が config.py を読む
sh $APRTOOLS/syn/sta/sta.sh <netlist> <top> <period_ns>
sh $APRTOOLS/syn/sta/sta.sh <netlist> <top> <period_ns> $APRTOOLS/syn/sta/path.tcl
```

> **★ Tcl の `proc` はグローバルを見ない。**
> `apply_period` の中で `scl` と直書きしていたときは要らなかったが、
> 変数にした瞬間 `can't read "CLK"` で落ちた。`global CLK NONSIG` が要る。

> **★ STA は RSLATCH に畳んだ後のネットリストに当てる。**
> 畳む前は NOR2 のクロス結合が生のループで残っていて、OpenSTA が
> combinational loop としてアークを 1 本**勝手に**切る。

### SCLK_SPI を 59.4 版で合成した結果（2026-09-15・確定）

RTL は `hdl/spi_slave_sclk.v`（118 行）。**旧 64.8 版とは別物になる**ので
GDS の比較はしない（U32）。`sh $APRTOOLS/syn/syn.sh` を引数なしで回した結果:

| | |
|---|---|
| 合成 | yosys 0.33 + `stdcell/v59_4/tr1um_typ_5v0_25c.lib` + `syn/abc.constr` |
| セル | 52 → dedup 52 → 畳み込み 37（MUX2+DFFRB を 15 組）→ BUFTH 3 本 = **40 個** |
| 面積 | **132,795 µm²**（旧 64.8 版の提出 134,078 から −1.0%） |
| RTL の TB | iverilog 11 本 **11/11 PASS** |
| ゲートレベルの TB | 同じ 11 本を畳み込み後のネットリストに **11/11 PASS** |
| BUFTH | `sclk` / `cs_n` / `sdio_in` の 3 本（`dis` はフレーム中に動かない静的な選択なので入れない） |

> **★ 最初の見積り（49 → 34 セル / 124,455 µm²）とは違う。**
> あれは `syn.sh` を通さず yosys を手で叩いたもので、**`abc.constr`
> （`set_driving_cell BUF_X2` / `set_load 36.2`）が入っていなかった**。
> 制約があると ABC は面積だけでなくタイミングも見てゲートを貼り直す
> （`buffer` / `upsize` / `dnsize` が走る）。**手で打つ値は、いつか
> 打ち忘れる値**（`docs/40_gotchas.md` §4-0）。

STA（period 100 ns、**P&R 前なので配線容量は入っていない**）:

```
  reg->reg    slack    36.244 ns   _88_/Q -> _78_/D
  in->reg     slack    20.991 ns   sdio_in -> _79_/D
  reg->out    slack    20.679 ns   _78_/Q -> sdio_out
  hold r->r   slack     5.381 ns   _87_/QB -> _87_/D
  => reg->reg が要求する最小周期 27.512 ns  (36.35 MHz)
     周期係数 a = 0.50 -> 半周期パス（立上り <-> 立下り）。経路の実遅延は 13.756 ns
```

**`sclk` の立上りで出て立下りで取り込む半周期パス。** hold が +5.381 ns
あるので、この構造でもホールド側には余裕がある。

> **★ この 36 MHz は上限ではなく出発点。** 配線容量が入っていない。
> P&R 後の**抽出したチップ**に ngspice を当てた実測（2026-09-15）は
> クロック→パッドの `tco` が最悪 **41.2 ns**（外部負荷 0 pF）で、
> SCLK の半周期がこれを上回る必要がある → **おおむね 10 MHz** が実用上限。
> 外部仕様の 10 MHz と一致する（`docs/09_rebuild_sclk_spi.md`）。

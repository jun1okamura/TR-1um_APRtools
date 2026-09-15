# 合成 → ネットリスト加工 → STA

対象: `syn/`、`apr/`（`dedup_gates.py` / `merge_muxdffrb_rslatch.py` / `insert_bufth.py` /
`insert_row_buffers.py` / `gen_liberty.py` / `syn_report.py` / `cmp_cells.py`）

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
- `RSTB` の `recovery` / `removal` と `min_pulse_width` が未特性化
- `REG8x16` のタイミングが `.lib` に無い（マクロを使う設計は STA にかけられない）

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

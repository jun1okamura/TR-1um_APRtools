# 特性化を手元の Mac で流す手順

`.lib` を作るには ngspice を **14,179 本**流す必要があります。
クラウド側は 2 コアなので逐次で 2 時間近くかかりますが、18 コアの Mac なら
並列で **10〜20 分**で終わります。そのため

  **生成（デッキを全部書き出す） → 実行（並列） → 回収（JSON 化）**

の 3 段に分けてあります。往復するのは `results.txt` 1 本だけです。

---

## 0. 前提

```sh
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um
cd $APRTOOLS/char
which ngspice          # 見つからなければ brew install ngspice
python3 -V             # 3.9 以上
```

★ **モデルは PDK を参照します。リポジトリにはコピーしません。**
`TR1UM_PDK/libs.tech/spice/models/ip62_models` を使います
（`TR1UM_MODELS` で上書き、`runjobs.sh` は `-m` でも指定できます）。
以前は設計リポジトリの `scripts/char/models/` に 5 本を写していて、
道具を APRtools へ移したときに**入力だけが設計側に残りました**（U65）。

---

## 1. 抽出ネットリストを取り込む

正本の `stdcell/v59_4/extracted/*.extracted` を ngspice が読める形に直します。
ネット名の `\$6` や素子名の `XM$1` は `$` が ngspice のコメント文字なので、
ここで `n6` / `XM1` に置き換えています。

```sh
python3 loadext.py ../stdcell/v59_4/extracted -o cells_ext
```

→ `cells_ext/` に 36 セル。以降のスクリプトはすべてこれを見ます。
**`cells_ext/` は生成物**（`.gitignore`）で、正本は `stdcell/v59_4/extracted/` です。

マクロとパッドを測るときは、入力もここで起こします:

```sh
# REG8x16（設計ネットリスト由来。char_mem.py の既定）
python3 mkmemsrc.py <設計>/lef/simulation/REG8x16.spice -o cells_mem/REG8x16_src.spi
# フレーム（char_pad.py 用）
python3 loadext.py <設計>/lef/extracted -o cells_pad
```

## 2. デッキを生成する

```sh
export TR1UM_CELLDIR=$PWD/cells_ext
export TR1UM_CELLEXT=.spi
python3 genjobs.py -o pack
```

→ `pack/decks/` に 14,179 本（約 70 MB）、`pack/jobs.json` に対応表。

内訳:

| 種類 | 本数 | 何を測るか |
|---|---:|---|
| delay | 686 | 組合せセルの cell_rise/fall・出力遷移（7×7） |
| cap | 49 | 入力に流れ込む電荷から出した入力容量 |
| calib | 124 | INV_X1 で N 個駆動して求める**遅延計算用の等価容量** |
| ckq | 56 | 順序セルの CK→Q（7×7） |
| setup / hold | 6,624 ×2 | 制約（3×3 × 立上下 × dt 掃引 92 点） |
| verify | 12+4 | 格子の**外**での検算と、実負荷ファンアウトの検算 |

setup/hold は二分探索をやめて**掃引**にしてあります。二分探索は前の結果に
依存するので並列にできません。掃引なら全点が独立で、しかも境界付近を
0.25 ns 刻みにしてあるので分解能は二分探索より良くなります。

## 3. 流す

```sh
./runjobs.sh -j 18
```

- 途中で Ctrl-C しても構いません。**もう一度叩けば続きから走ります**
  （結果のあるデッキは飛ばします）。
- 20 秒ごとに `本/秒` と残り時間が出ます。**1 本/秒 を大きく下回るようなら
  並列数を下げてください**（`-j 9` など）。ngspice は 1 プロセスで複数
  スレッドを使おうとし、コア数を超えると桁違いに遅くなります。
  対策として `pack/.spiceinit` に `set num_threads=1` を置いていますが、
  ビルドによっては効かないことがあります。
- モデルを別の場所から読ませたいとき: `./runjobs.sh -j 18 -m /path/to/pdk/models`

→ `pack/results.txt`（1 行が `タグ 測定名 値`、数 MB）

## 4. 回収して `.lib` を作る

```sh
python3 collect.py -p pack      # results.txt -> char/*.json
python3 mklib.py -o ../stdcell/v59_4/tr1um_typ_5v0_25c.lib
python3 verify_lib.py ../stdcell/v59_4/tr1um_typ_5v0_25c.lib
```

`verify_lib.py` は `char/_verify.json`（collect.py が置きます）があれば
ngspice を回さず、**手順 3 と同じ実行の実測値**で検算します。

---

## 何が出れば成功か

`verify_lib.py` の 5 段がすべて「逸脱なし」なら `.lib` は使えます。
引数を省くと `char/` → `stdcell/<版>/` の順に探します。**見つからなければ
「要確認」**で終わります（回らなかった検査を「OK」と言わないため。U74）。

1. **表の健全性** — 欠損なし、負荷を増やすと必ず遅くなる（単調）
2. **格子の外での照合** — 入力遷移 1.0 ns / 負荷 150 fF（どちらも格子点では
   ない）での ngspice 実測と、`.lib` を線形補間した値のずれが 15% 未満
3. **入力容量の妥当性** — INV_X1 が INV_X1 を N 個駆動したときの実測遅延と、
   `.lib` を「負荷 = N × capacitance」で引いた値のずれが 20% 未満
4. **マクロの書込みパス** — `REG8x16.json` の `webq` / `limits` が `.lib` に
   **値まで一致して**出ているか。測っていない制約が紛れていないか
5. **`.lib` の構文** — 括弧の対応と必須項目

動作確認では 2 が 0.2〜1.0%、3 が 0.2〜2.5% で一致しています。

`collect.py` が出す注記のうち、

- `掃引の下端でも取り込めた` — その条件では setup/hold に余裕があり、
  境界が掃引範囲（−20 ns）より下にあるという意味。値は −20 で頭打ちになります。
- `単調でない` — dt を大きくしたのに取り込めない点があるということなので、
  刺激かセルを疑ってください。

---

## ファイルの役割

| ファイル | 役割 |
|---|---|
| `loadext.py` | `lef/extracted/*.extracted` → `cells_ext/*.spi` |
| `cellspec.py` | セルの真理値表・Liberty 関数・FF の定義（**唯一の出典**） |
| `charlib.py` | 格子（SLEWS/LOADS）・しきい値・アーク列挙 |
| `char_comb.py` / `char_seq.py` | デッキの組み立て（測定条件はここ） |
| `calib_cap.py` | 入力容量の較正（表の逆引き） |
| `genjobs.py` | 上記を使ってデッキを全部書き出す |
| `runjobs.sh` | 並列実行して `.meas` の行だけ集める |
| `collect.py` | `results.txt` → `char/*.json` |
| `mklib.py` | `char/*.json` → Liberty |
| `verify_lib.py` | `.lib` の検算 |
| `check_comb.py` / `check_seq.py` / `check_pass.py` | 論理の確認（`.lib` とは独立） |

---

# セルを 1 つ足す（`run_rslatch.sh`）

★ **`RSLATCH` は正本 `stdcell/v59_4/tr1um_typ_5v0_25c.lib` に既に入っています。**
これは「セルを 1 つ特性化して `.lib` に足す」手順を**動く形で残したもの**で、
そのまま流すと同じ値が出ます（増えたセル 0・変わったセル 0）。

元の経緯: Async I2C は SR ラッチを 3 個使うので、`.lib` に無いと `abc -liberty`
が貼れず OpenSTA も遅延を持てない。それを埋めるために作った一式です。

```sh
cd <APRtools>/char
./run_rslatch.sh -j 18
```

`-j` の既定は物理コア数です。

デッキは 136 本しかないので 1 分もかからない。中でやっているのは

| 段 | 中身 |
|---|---|
| 0 | `stdcell/<版>/extracted/RSLATCH.extracted` → `cells_ext/RSLATCH.spi`（無ければ） |
| 1 | `char_latch.py gen` → `pack_rslatch/decks/` に 136 本 |
| 2 | `runjobs.sh -p pack_rslatch` で並列実行 → `results.txt` |
| 3 | `char_latch.py collect` → `char/RSLATCH.json` と格子外での検算 |
| 3.5 | `calib_cap.py RSLATCH` → 入力容量を等価容量へ較正 |
| 4 | `mklib.py` で `.lib` を作り直す（**RSLATCH 以外が変わっていないことも確認する**） |
| 5 | `verify_lib.py` |

## 出るはずの値（2 コアのクラウドで事前に流したときの実測）

| | |
|---|---|
| 入力容量 S / R | 電荷から 76.7 fF → 較正後 **60.5 fF**（比 0.79、N=2/4 のばらつき 3.7%） |
| S→Q / R→QB（preset） | slew 0.6ns / CL 50fF で **2.676 ns** |
| S→QB / R→Q（clear） | 同条件で **1.242 ns** |
| 最小 High パルス幅 | **1.85 ns**（等比 10% 刻みの掃引なので分解能 10%） |
| 格子の外（slew 1.0 / CL 150fF）での照合 | ずれ 0.0〜0.2% |

S 側と R 側が同じ値になるのは、レイアウトが対称（PMOS 10.2u / NMOS 3.4u が
両側同じ）だから。**片方だけずれたらレイアウトを疑うこと。**

## 測り方で気をつけたところ

- **測る前に反対側の入力で初期化する。** t=0 から 20ns まで反対側を VDD に張り、
  21ns で放す（NOR ラッチはそのまま保持する）。100ns で測る側を振る。
- **アクティブ端にしかアークが立たない。** S↓ / R↓ では出力は動かないので、
  Liberty には preset / clear のアーク（片方向の表）として書く。
- **クロス結合なので反対側の出力の負荷が効く。** 測る側に負荷を掃引し、
  反対側は 25 fF 固定。この条件は `.lib` のコメントにも書いてある。
- **`dont_use` を付ける。** RTL で明示インスタンスする前提のセルで、ABC に
  SR ラッチを勝手に組ませてはいけない。`.lib` に入れるのは P&R の負荷計算と
  OpenSTA のため。

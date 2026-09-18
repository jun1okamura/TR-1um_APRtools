# `syn/sta/` — OpenSTA

`.lib` は実測（ngspice）なので、STA が当てられる。ここはその足回り。
**設計のルートで**、`PYTHONPATH` に `apr/` を入れて回す（値は設計の `config.py` から取る）。

```sh
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr

sh $APRTOOLS/syn/sta/sta.sh out/td4_soc_arr_pnr.v td4_soc_arr 100
sh $APRTOOLS/syn/sta/sta.sh out/td4_soc_arr_pnr.v td4_soc_arr 100 $APRTOOLS/syn/sta/path.tcl
```

★ **当てるのは `config.NET_PATH`（最後のネットリスト）。** 途中の版を渡しても
落ちずに**別の回路の数字**が出る。TD4 の `out/` には 4 つあり、
`td4_soc_arr.v` は**メモリが DFF 128 個に展開された版**（セルは全部 Liberty に
あるので、セル検査では気づけない）。`sta.sh` は当てる前に下見をして、
`NET_PATH` と違う / モジュールが 2 つ以上 / Liberty に無いセルがある、を言う。

| ファイル | 中身 |
|---|---|
| `sta.sh` | ドライバ。下見 → `NET` / `TOP` / `PER` を先頭に置いて `setup.tcl` + レポート tcl を連結して流す |
| `setup.tcl` | 読み込みと SDC 相当の制約（クロック・駆動セル・負荷・入出力遅延） |
| `report.tcl` | reg→reg / in→reg / reg→out / hold の最悪 slack と Fmax |
| `report_macro.tcl` | **マクロの制約を STA が実際に見ているか**（`STA_MACRO_INSTS` があるときだけ連結。U73） |
| `path.tcl` | reg→reg のクリティカルパス詳細 |
| `macro_probe.v` / `check_macro_arcs.tcl` | 最小ネットリストで「どの制約が効くか」を確かめる探針（U73） |

## OpenSTA のビルド

このリポジトリには入れていない。`sta` が PATH にあれば `syn/syn.sh` の段 9 と
`syn/sta/sta.sh` が自動で使う。別の場所に置くなら `STA=/path/to/sta` で渡せる。

### macOS（Apple Silicon / Homebrew）

**Xcode 付属の Tcl / Flex / Bison では通らない**（上流 README が明記）。
Homebrew のものを PATH の先に置くのが要点。

```sh
git clone https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA
```

#### 依存を入れる

上流の `Brewfile` の中身は bison / cmake / eigen / flex / swig / tcl-tk@8 と
**`mht208/formal/cudd`**。最後だけ Homebrew 本体ではなく 3rd party タップにある。

**Homebrew 6.0（2026-06）から、3rd party タップは明示的に信頼しないと読み込まれない。**
`brew bundle install` はここで

```
Error: Invalid formula (...): .../mht208/homebrew-formal/abc.rb
Refusing to load formula mht208/formal/abc from untrusted tap mht208/formal.
```

と止まる（タップ内の**全**formula について出るので行数が多いが、原因は 1 つ）。
どちらかを選ぶ:

**(a) タップを信頼する** — 上流が想定している道。CUDD をビルドしなくて済む。
タップの Ruby コードが自分の機械で走ることを許すので、範囲は狭い方で。

```sh
brew trust --formula mht208/formal/cudd    # この formula だけ
# brew trust mht208/formal                 # タップ丸ごと（abc/boolector 等も使うなら）
brew bundle install
```

**(b) タップを使わず CUDD を自前で建てる** — 本体だけで済ませたいとき。

```sh
brew install bison cmake eigen flex swig tcl-tk@8

git clone https://github.com/cuddorg/cudd.git
cd cudd && git checkout cudd-3.0.0

# (1) clone 直後にそのまま make すると autotools を再生成しようとして
#     `Makefile:983: aclocal.m4  Error 127` で止まる。git は
#     configure より aclocal.m4 を新しい時刻で展開しうるため。
#     生成物の時刻を「上流→下流」の順に付け直しておく。
#     （`*/Makefile.in` は cudd には無いので、無い名前は飛ばす）
for f in configure.ac aclocal.m4 configure config.h.in Makefile.in */Makefile.in; do
  [ -e "$f" ] || continue; touch "$f"; sleep 0.05
done

# (2) **--build を明示する。** CUDD 3.0.0 同梱の config.sub は 2014 年版で、
#     Apple Silicon の `arm64-apple-darwin` を知らない（実測: "machine
#     `arm64-apple` not recognized"）。同じ機械を指す `aarch64-apple-darwin`
#     なら通る。これを渡さないと configure が "cannot guess build type" で死ぬ。
./configure --prefix="$HOME/.local/cudd" --enable-shared --enable-obj \
            --build=aarch64-apple-darwin
make -j"$(sysctl -n hw.physicalcpu)" && make install
cd ..
```

(1)(2) とも aarch64 の Linux で実際に踏んで直したもの。`-fcommon` の類は
要らなかった（`-fno-common` が既定の新しいコンパイラでも警告なしに通る）。

#### ビルド

```sh
# Apple 版を押しのける。**これを忘れると Apple の bison 2.3 が使われ、
# parser 生成で落ちる。**
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
export CMAKE_INCLUDE_PATH="$(brew --prefix flex)/include"
export CMAKE_LIBRARY_PATH="$(brew --prefix flex)/lib;$(brew --prefix bison)/lib"

# (a) なら $(brew --prefix cudd)、(b) なら $HOME/.local/cudd
cmake -B build -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR="$(brew --prefix cudd)"
cmake --build build -j"$(sysctl -n hw.physicalcpu)"
build/sta -version
```

つまずきどころ:

| 症状 | 原因と手当て |
|---|---|
| `Refusing to load formula ... untrusted tap` | Homebrew 6.0 のタップ信頼。上の (a) か (b) |
| `bison: ... version 2.3` / parser 生成で syntax error | export が効いていない。`which bison` が `/opt/homebrew/...` を指しているか |
| Tcl が見つからない | `tcl-tk@8` は keg-only。`-DCMAKE_PREFIX_PATH="$(brew --prefix tcl-tk@8)"` を足す |
| `CUDD not found` | `-DCUDD_DIR` が (a)/(b) のどちらの場所を指すべきか取り違えている |

`tclreadline` は Homebrew に無い（上流 README）。対話シェルの補完が無いだけで、
`sta.sh` のように `-exit` で流す使い方には関係しない。

置き場所はどちらでもよい:

```sh
sudo cp build/sta /usr/local/bin/     # PATH に置く
export STA="$PWD/build/sta"           # か、sta.sh / syn.sh に環境変数で渡す
```

動作確認（この手順で **OpenSTA 3.1.0** が建つことを確認済み。2026-09-14）:

```sh
cd <設計を置いた場所>/TR-1um_I2C_2026
PYTHONPATH=$APRTOOLS/apr sh $APRTOOLS/syn/sta/sta.sh out/i2c_slave_async_pnr.v i2c_slave_async 2500
```

### Ubuntu 24.04

```sh
apt-get install -y cmake swig bison flex tcl-dev libeigen3-dev zlib1g-dev
# CUDD は apt に無いので自前ビルド
git clone --depth 1 https://github.com/cuddorg/cudd.git
cd cudd && ./configure --prefix=/usr/local --enable-shared --enable-obj && make -j && make install
cd ..
git clone --depth 1 https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA && cmake -B build -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR=/usr/local && make -C build -j
# build/sta を PATH に置くか STA=... で指定する
```

## いま入っていない前提

- **配線容量ゼロ。** P&R 前なのでネット容量は駆動セルの負荷だけ。
  TR-1um の M2 は幅 3.4 um と太いので、実配線が乗ると悪化する。
- **クロックツリー無し。** `set_ideal_network` で skew 0。
- **`RSTB` の `recovery` / `removal` を特性化していない**（U8）。TD4 / I2C の
  リセットは電源投入時に一度きりなので `set_false_path` で正しいが、
  SCLK_SPI は**フレームごとに解除される**ので、そこは数字で言えない。
- **`REG8x16` の `min_pulse_width`（`WEB` の低幅。値は `.lib` から引く）は OpenSTA が見ない**（U73）。
  Liberty には記録として入っているが、担保は ngspice の回帰側。

`REG8x16` のタイミングは **2026-09-16 に読出し・書込みとも `.lib` に入った**（U7）ので、
マクロを含む `td4_soc_arr` も STA にかけられる（`STA_MACRO_INSTS` と `report_macro.tcl`）。

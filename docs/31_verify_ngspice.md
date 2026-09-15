# ngspice / IRSIM による機能・速度検証

対象: `apr/gen_chip_tb.py` / `check_chip_sim.py` / `klayout_extract.py` /
`frame2sim.py` / `spi2ngspice.py` / `spi2sim.py` / `check_ngspice.py` /
`gen_irsim_cmd.py` / `check_irsim_log.py`、
`apr/from_sclk_spi/{gen_chip_sim_ready.py,gen_sim_from_extracted.py}`

## 0. 実行手順（APRtools から回す）

設計ディレクトリ（`TR-1um_I2C_2026` など）を **cwd** にして、`apr/` を
`PYTHONPATH` に置く。`apr_path.py` が cwd（または `APR_DESIGN_ROOT`）を
`sys.path` の**末尾**に足すので、設計の `config.py` がそこから読まれる。

```sh
export TR1UM_PDK=$HOME/Dropbox/91_OpenPDK/TR-1um
export APRTOOLS=$HOME/Dropbox/91_OpenPDK/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
export PYTHONHASHSEED=0                 # ルータが非決定的（docs/40_gotchas.md）
cd $HOME/Dropbox/98_LSI_Design/TR-1um_I2C_2026
```

### 1) レイアウトから抽出して ngspice 用に直す（APRtools 側）

```sh
python3 $APRTOOLS/apr/gen_chip_sim_ready.py                 # RING_OSC 入り  -> <top>_sim.spice
python3 $APRTOOLS/apr/gen_chip_sim_ready.py --no-ringosc    # 長い回帰用     -> <top>_noosc_sim.spice
```

内部で `apr/klayout_extract.py` を `subprocess` で呼ぶ。

> **★ 要るのは pip の `klayout` モジュールで、KLayout アプリではない。**
> `/Applications/klayout.app` を入れても `import klayout.db` はできない
> （逆に PDK 公式デッキの DRC/LVS はアプリでしか流せない）。
>
> ```sh
> python3 -m pip install klayout      # Homebrew の python なら --break-system-packages か venv
> ```
>
> 親スクリプトは `sys.executable` で子を起動するので、**venv に入れてあるなら
> 親をその python で呼べばよい**。`selfcheck.py` の `--- 0. 実行環境 ---` が
> モジュール / アプリ / ngspice の 3 つを先に確認する。
> 詳細は `docs/40_gotchas.md` §2-b。

### 2) テストベンチを作る（**設計側**のスクリプト）

刺激とパッド割り当ては設計ごとに違うので、TB 生成は設計リポジトリに残す。

```sh
python3 scripts/pnr/gen_chip_tb_batch14.py                     # 14 項目回帰（544 µs）
python3 scripts/pnr/gen_chip_tb_ringosc.py --until 12u --tmax 500p
```

> **★ TB に埋まる `.include` は絶対パスである。**
> `$TR1UM_PDK` をその場で展開して書き込むので、**別の機械で作った
> `tb_*.spice` はそのままでは読めない**（`/home/claude/...` のような
> 他所のパスが残る）。回す機械で TB を作り直すこと。

### 3) 回して判定する

```sh
cd layout/chip/simulation
ngspice -b tb_batch14.spice > batch14.log 2>&1
python3 ../../../scripts/pnr/check_batch14.py batch14.log

ngspice -b tb_ringosc.spice > ringosc.log 2>&1
```

`ngspice` は PDK にもモデルにも依存しない普通のバイナリ（Debian/Ubuntu は
`apt install ngspice`、macOS は `brew install ngspice`）。**KLayout の CLI が
要らないので、DRC/LVS と違ってどこでも回せる。**

### 移行後の実測（2026-09-15、`vdd`/`vss` 統一後）

クラウド（x86_64 / ngspice 42）で `tb_batch14.spice`（`.tran 50n 544u 0 10n`）を
流した結果:

```
Total analysis time (seconds) = 164.3
---- RESULT ----
All 14 checks PASSED
```

抽出ネットリストを移行前と比べると、**電源名を正規化した差分は 0 行**
（素の差分 946 行は全て `VDD`->`vdd` / `GND`->`vss`）。
回路は 1 素子も動いていない。コアの `.SUBCKT` が

```
.SUBCKT i2c_slave_async_nrow_fm vdd … rst_n vss
```

になり、チップのパッドは `VDD` / `VSS` のまま（`rules.PAD_PWR` / `PAD_GND`）。

> **★ `gen_chip_sim_ready.py` の `EXTRACT` は APRtools では同じ `apr/` の中。**
> 設計側では `scripts/pnr/` から `scripts/klayout_extract.py` を見ていたので
> `os.path.dirname(HERE)` だった。移行時にここを直し忘れて
> `apr_root/klayout_extract.py` を探して落ちた（2026-09-15 に修正）。

## 1. どのネットリストを回すか

| 用途 | 作り方 | 特徴 |
|---|---|---|
| **参照側** | 合成ネットリスト + セルの回路図 | 設計意図そのもの。**寄生を悲観的に見積もる** |
| **抽出側** | `klayout_extract.py`（階層とラベルを残す） | W/L も AS/AD/PS/PD も**実測値** |
| LVS 用 `*_lay.spice` | `lvs_pnr.py` | **ngspice には使えない** |

**両方を回して突き合わせる**のが正規手順。SCLK_SPI では 12 チェック / 54 measure が
参照・抽出とも一致し、最大差 0.69 mV。

### ★ 参照側は速度を悲観的に見積もる

PDK 既定の `AS/AD = w*sdwidth`、`PS/PD = 2*(sdwidth+w)` は
**行内で隣接セルが共有する拡散を二重に数える**。抽出側は実測なので一度しか数えない。
実測差: `tco_sdio` 38.55 → 37.10 ns（−3.6%）、`tco_data` 27.90 → 27.55 ns。

### ★ 抽出の意味（回路図では出ない差が出る）

`INV3D` は `INV_X1` と W/L が同じ（PMOS 10.2/1.0、NMOS 3.4/1.0）で違うのは**レイアウトだけ**。
抽出拡散面積が `AS=539.5p` 対 `14.6p` なので接合容量で 3.6 倍遅い。
リングオシレータ実測: `INV_X1`×95 が **6.450 MHz**、`INV3D`×95 が **1.790 MHz**（比 3.60）。
移行後（`vdd`/`vss`）の再抽出でも **6.44992 / 1.79020 MHz**（比 3.603）で、
**抽出が拾う `AS/AD/PS/PD` が壊れていない**ことの裏付けになる。
**回路図から作ったネットリストでは両者が同じ回路になる。**

## 2. 変換（回路は触らない）

`.extracted` / LVS ネットリストをそのまま ngspice に食わせることはできない。

| # | 変換 | 理由 |
|---|---|---|
| 1 | `M<name> … PMOS` → `X<name>` | PDK の `PMOS`/`NMOS`/`MPE`/`MNE` は `.model` ではなく **`.subckt`** |
| 2 | `rx_data[0]` → `rx_data_0` | 角括弧 |
| 3 | `*.PININFO` の `+` 継続行 → `*+` | **コメントは改行で終わる**ので継続行が回路行として読まれる |
| 4 | ダイオードの `A=` / `P=` → `AREA=` / `PJ=` | |
| 5 | `NMOSE` → `MNE` | **PDK に `NMOSE` は無い** |
| 6 | `\$107` → `net_107`、`X$1`/`XM$1`/`D$17` → `X_1`/`XM_1`/`D_17` | **`$` は ngspice のコメント文字** |
| 7 | `PAD\|VDD` → `PAD_VDD` | |

> **★ 改名は書き出す前に全数の衝突照合にかける。**
> 別々のネットが同じ名前になると、後からは本物のショートと区別がつかない。
> 置換数を全数印字し、書き出し後に KLayout の SPICE リーダで読み直して確認する。
>
> **「変換して壊れたネットリストは、変換しなかったより悪い。」**

トップ `.SUBCKT` のポートは KLayout がアルファベット順に書くので
**ボンドパッド順に並べ替える**（並べ替えないと黙ってパッドが入れ替わる）。

フレームは `frame2sim.py` / `mkframespice.py` が別途扱う（ESD 素子のモデル名判定を含む）。

## 3. テストベンチ

```sh
python3 apr/gen_chip_tb.py --models $TR1UM_PDK/libs.tech/spice/models/ip62_models
ngspice -b tb_chip.spice > spice_chip.log
python3 apr/check_chip_sim.py spice_chip.log
```

期待値は `*_expected.json` に出し、ログだけで合否が付くようにする。

### ★ `.control` に `run` を書かない

解析が 2 回走る。I2C 版の TB がそうなっていて、2 回分の 54 measure が最後の桁まで一致したので
「間違いではなく倍の時間を使っていただけ」と判明した。
**`print` を書くと今度は本当に壊れた 2 回目が走る。**
→ **`.control` は `save` を置くためだけに使う。** `save` を 16 パッドに絞ってメモリ約 10 MB。

### ★ `.tran` の Tmax = 1 ns

50 ns だと **10 ns 未満のセットアップ余裕を解像できず、適応ステップ制御が誤った側に丸める**。
IRSIM・Verilog・ゲートレベルの全てで通るフレームが SPICE だけ落ちる現象を数セッション
追いかけて判明した。**Tmax を 1 ns にするだけで 10/14 → 14/14。**

区間限定の手段が無いので全区間に効き遅い（37.5 µs で設計機 24 秒 / クラウド約 80 秒）。
チップ全体（4,225 素子・3,150 ns を 0.5 ns 刻み）で約 1 分 52 秒。

### ★ `vss` は節点 0 の別名

`Vgnd vss 0 0` は「shorted VSRC」で止まる。**電源は vdd だけ置く。**

### 双方向パッド

**両側から駆動しない。** 各パッドに対 VSS の抵抗を入れて動作点の DC 経路と Hi-Z 電位を決める
（DATA 1 MΩ / SDIO 20 kΩ、駆動側は `TXGATE`/`MGATE` を DIS に追随させる）。

READ 値は **LSB=1 にする**（LSB が 0 だと「手を離した」と「まだ駆動している」が区別できない）。
TB 駆動の 4.95 V は 10 kΩ / 1 MΩ の分圧そのもの。

「測っていないのに通っている」を避けるため、**DATA パッド上を複数パターンで走査する**
（`0x00` → `0xA5` → `0x3D` → `0xA5` → `0x5A`）。

## 4. 速度の測り方

### ★ 測っているのが部品か測定系かを分ける

20 pF 負荷の掃引が 12 MHz で止まったが、落ちたのは**チップではなく TB のマスタ**
（1 kΩ 直列 × 20 pF = 時定数 20 ns）。`--master-ohm 100` で同じ 20 pF が 15 MHz まで通った。

> **測定系を切り分けられるようにしておかないと、部品に無い上限を報告してしまう。**

**シミュレータが落ちた点は FAIL ではなく ERROR** として区別する。

### エッジ時間

エッジは `TCK/25`（上限 20 ns）で縮めるが、**リセットだけは 100 ns 固定**
（2 ns のランプをリセットパッドの ESD 構造に入れたら "timestep too small" で落ちた掃引点が実在した）。

低速での `tco` はエッジの鈍りによる測定アーティファクトが乗る
（1 MHz で 37 ns、エッジを速くすると 30.7 ns に収束）。

### コーナー

**全ての速度値が typical / 27 °C / 5.0 V。** 遅い側のコーナーでは `tco` が伸びる。
**外部仕様は余裕を持って書く**（SCLK_SPI は実測 16 MHz に対し推奨最大 10 MHz）。

負荷感度の実測: **0.28 ns/pF**（SCLK_SPI の `tco`）。
`OSS_ESD_5V_DIO` 単体は約 0.17 ns/pF（`docs/11_frame_io.md` §4）。

## 5. IRSIM（スイッチレベル）

```sh
python3 apr/gen_irsim_cmd.py --bits N
irsim TR-1um.prm <sim> -   # .cmd を流す
python3 apr/check_irsim_log.py <log>
```

### 合否はログだけで完結させる

`.cmd` 言語には条件分岐も算術も無い。読出のたびに
`print CHECK tag=… exp=…` / `assert QV …` / `d AV QV` の 3 行を出して集計する
（期待値ファイル不要）。

### 設定

- `stepsize 1`（→ 1 ns）
- **`settle 10`** — 背中合わせインバータの帰還ノードが一瞬の競合で X 判定されないよう時間を与える

### 既知の警告

```
There are too many transistors in parallel (> 30)
```

`MAX_PARALLEL`（既定 30）。電源投入直後、ワードラインがまだ X で全 16 行のパスゲートが
「導通かもしれない」状態のときにアレイ全体が 1 つのステージになるため。
アドレスが確定すれば 1 行しか導通しないので**実害なし**（512 項目すべて Verilog 版と一致）。

### ★ 配線容量が入っていない

`.sim` に配線形状を持たせていないので、ビット線（M2 878 µm）やワードラインの容量は入らない。
**実物はこれより遅い。** 最終速度はレイアウト抽出か SPICE で確認する。

実測（TD4 メモリ、配線容量なし）: 読出アクセス 14 ns / 書込レイテンシ 12 ns /
最小 `WEB` パルス幅 3 ns。

## 6. 三重化のパターン

同じベクタを **Verilog（論理と接続）→ IRSIM（スイッチレベルの遅延）→ ngspice（実デバイス）**
に流す。RTL / NET / PNR の 3 ビューに同一 TB を流すのも同じ考え方
（SCLK_SPI: 12 本 × 187 チェック × 3 = **561 チェック / 36 ラン**）。

アレイなら何にでも使える検査項目: x/z が無いこと、`RD` がちょうど 1 本、
`WR` が同時に 2 本以上立たないこと。

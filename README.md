# TR-1um_APRtools

TR-1um（OpenSUSI / IP62、1 µm CMOS・**M1/M2 の 2 層配線**）向けの**自作 配置配線ツール群**と、
標準セル・マクロの共通データ、蓄積した設計知見の集約先。

商用 EDA も一般的な OSS フローも 3 層以上の配線を前提にするため、TR-1um には使えない。
`TR-1um_Async_I2C` 以来 4 世代にわたって自作してきた P&R 一式を、
**設計ごとにコピーするのをやめて 1 箇所にまとめる**のがこのリポジトリ。

**設計固有のものはここに置かない。** 刺激・ピン割り当て・寸法は設計の
`config.py` にあり、道具は引数も再現用の環境変数も取らない。

---

## 使い方

### 0. 環境

```sh
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um        # PDK は参照する（コピーしない）
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
export PYTHONHASHSEED=0                              # 集合の反復順を固定する（決定 24）
```

設計ディレクトリを **cwd** にして呼ぶ。`apr/apr_path.py` が設計ルートの
`config.py` を**ファイルとして**読み込むので、`config` という名前が
仮想環境の別のパッケージと衝突しても正しい方を掴む（U98）。

### 1. 下ごしらえの点検

```sh
cd <設計を置いた場所>/<design>
python3 $APRTOOLS/apr/selfcheck.py        # KLayout 無しで環境と入力を点検
```

### 2. 合成 → 配置 → 配線 → チップ

```sh
sh      $APRTOOLS/syn/syn.sh              # 合成・畳み込み・TB・面積・STA（段は config.py 次第）
python3 $APRTOOLS/apr/place.py            # 配置 step1〜4
python3 $APRTOOLS/apr/route.py            # 配線 step5〜11
python3 $APRTOOLS/apr/assemble_top.py     # チップ step1（フレームに載せる）
python3 $APRTOOLS/apr/route_chip.py       # チップ step2〜4
python3 $APRTOOLS/apr/export_mpw.py       # 提出物
```

### 3. 検証

```sh
python3 $APRTOOLS/apr/verify_chip.py      # 接続性（自作）
python3 $APRTOOLS/apr/drc_pdk.py          # PDK 公式 DRC
python3 $APRTOOLS/apr/lvs_pdk.py          # PDK 公式 LVS
```

> ★ **自作チェッカが 0 を返したことは根拠にならない。**
> サインオフは**公式デッキ**で取る（`docs/30_verify_drc_lvs.md` §0）。

### 4. 台帳とリポジトリの健全性

**数字を文書に写さない**ための道具。どれも引数なしか設計を並べるだけで走る。

```sh
python3 $APRTOOLS/apr/lint.py                 # パスと名前の静的検査
python3 $APRTOOLS/apr/check_ledger.py         # 台帳の索引と本文が 1 対 1 か
python3 $APRTOOLS/apr/check_copies.py <設計>… # 設計側に残る同名の写しを分類
python3 $APRTOOLS/apr/check_no_home_paths.py <設計>…   # 個人のパスが混じっていないか
python3 $APRTOOLS/apr/lib_query.py cap <lib> <セル> <ピン>   # .lib の値を引く（写さない）
python3 $APRTOOLS/char/verify_lib.py          # .lib の検算（5 段）
python3 $APRTOOLS/char/regress_limits.py      # STA が見ない制約を ngspice で守る
```

### 設計側に置くもの

`config.py`（`config_base` を継承）と RTL / LEF / 期待値、
そして**刺激が設計固有のテストベンチ生成**だけ。ひな形は `templates/`。

★ **道具の写しを設計側に置かない。** 置くと、いつか古い方を呼ぶ
（U89 / U14 で 2 度踏んだ）。残すなら `# copy: ok <理由>` を書き、
`check_copies.py` が「古いだけ」を 0 に保っているか毎回数える。

---

## 構成

```
apr/          P&R エンジン（役割別の地図は apr/README.md）
              config_base.py  設計非依存の既定値と導出 + check()
              rules.py        DRC 値・レイヤ番号・グリッドの単一ソース
              apr_path.py     設計の config.py をファイルとして読み込む
              selfcheck.py    実行環境と下ごしらえを点検（KLayout 不要）
              lint.py         パスと名前を静的に検査する
              cmp_gds.py      GDS を正規化 md5 + 幾何 XOR で比べる
syn/          合成・STA（syn.sh / sta/ / tr1um.genlib。abc.constr は .lib から生成）
char/         セル特性化（スクリプトと特性化結果、Liberty 生成）
stdcell/      v59_4（正本） / v64_8（凍結） / CELLS.md
macro/        ringosc/ regfile/
art/          opensusi_logo.txt
templates/    設計側のひな形
pdk/          README のみ。★ PDK のデータは置かない
legacy/       移植原本（read-only・改名しない）
docs/         下記
```

---

## ドキュメント

★ **「参照」は更新する。「記録」は書き換えない**（`docs/00_directory.md` 冒頭）。

### 参照 — いまどうなっているか

| 文書 | 内容 |
|---|---|
| [`apr/README.md`](apr/README.md) | **`apr/` の地図**。役割別の分類表（`lint` の `file-table` が「表に無い道具」を NG にする）|
| [`docs/00_directory.md`](docs/00_directory.md) | ディレクトリ構成、共通/設計固有の 4 層モデル、docs の読み方 |
| [`docs/03_core_geometry.md`](docs/03_core_geometry.md) | コア幅のパラメータ化（5.4 µm の整数倍）と TAP 列の上限 |
| [`docs/04_naming.md`](docs/04_naming.md) | 命名の規約（`vdd`/`vss` / `APR_*` / 日本語の用語）|
| [`docs/10_pdk_facts.md`](docs/10_pdk_facts.md) | プロセス事実 — レイヤ番号、DR 値、グリッド導出、**訂正履歴** |
| [`docs/11_frame_io.md`](docs/11_frame_io.md) | フレーム・パッド 44 端子・電源・リングレーン・ロゴ |
| [`stdcell/CELLS.md`](stdcell/CELLS.md) | セル一覧、物理セルの使い分け、**足りないセル** |
| [`docs/20_flow_syn.md`](docs/20_flow_syn.md) | 合成 → ネットリスト加工 → STA |
| [`docs/21_flow_place.md`](docs/21_flow_place.md) | 配置 step1〜4 |
| [`docs/22_flow_route.md`](docs/22_flow_route.md) | 配線 step5〜11 |
| [`docs/23_flow_chip.md`](docs/23_flow_chip.md) | チップ組み立て |
| [`docs/30_verify_drc_lvs.md`](docs/30_verify_drc_lvs.md) | **DRC / LVS — §0 にサインオフの手順** |
| [`docs/31_verify_ngspice.md`](docs/31_verify_ngspice.md) | ngspice / IRSIM |
| [`docs/50_char.md`](docs/50_char.md) | セル特性化 |
| [`docs/40_gotchas.md`](docs/40_gotchas.md) | **踏んだ穴 — 設計非依存の落とし穴集**（★ は 2 回以上踏んだもの）|
| [`docs/90_improvement_notes.md`](docs/90_improvement_notes.md) | **技術的負債の台帳** — 番号 `U<n>`。**状態は §7-1 の索引だけ**、開いているものは §7-2、教訓は §8 |
| [`docs/91_decisions.md`](docs/91_decisions.md) | **決定事項 1〜26** — コードと docs が引く「決定 N」の出典 |
| [`pdk/README.md`](pdk/README.md) | **PDK は参照しコピーしない** — 対象一覧 |

### 記録 — いつ何が起きたか（書き換えない）

| 文書 | 内容 |
|---|---|
| [`docs/92_closed.md`](docs/92_closed.md) | **決着した台帳項目の経緯**（U 番号順）。状態は書かない |
| [`docs/01_inventory.md`](docs/01_inventory.md) | 2026-09-14 の資産棚卸し |
| [`docs/02_stdcell_diff.md`](docs/02_stdcell_diff.md) | STDCELL 2 世代の差分 → v59_4 を正本に決定 |
| [`docs/05_migration_log.md`](docs/05_migration_log.md) | データ移動の記録 |
| [`docs/06_verify_migration.md`](docs/06_verify_migration.md) | 移行の検証（I2C）|
| [`docs/07_frame_issue.md`](docs/07_frame_issue.md) | フレーム GDS の問題（U19 / U22）|
| [`docs/08_migration_td4.md`](docs/08_migration_td4.md) | TD4 の移行 |
| [`docs/09_rebuild_sclk_spi.md`](docs/09_rebuild_sclk_spi.md) | SCLK_SPI の作り直し |
| [`pdk/PR-TR-1um-OSS_DRV.md`](pdk/PR-TR-1um-OSS_DRV.md) | PDK への PR 本文 |
| [`pdk/pending-upstream/README.md`](pdk/pending-upstream/README.md) | 上流 PR 待ちのデータ（マージされたら消す）|

---

## 出所

| リポジトリ | 世代 | 貢献 |
|---|---|---|
| `TR-1um_Async_I2C` | 原本 | チャネルルータ、リング配線エンジン、5 パス配線 |
| `TR-1um_SCLK_SPI` | 2 代目 | 設定の単一ソース化、ポート接続性検証、セル単体 DRC、Liberty 生成 |
| `TR-1um_TD4` | 3 代目 | ハードマクロ対応、メモリアレイ（TLAT/REG8x16/MEMPORT）、特性化フロー |
| `TR-1um_I2C_2026` | 4 代目 | 配置のパッド近接項、トップピン振り分け、PDK 公式 DRC/LVS、RING_OSC 同居 |

**3 設計とも APRtools で全段そろって回る。** 移行時に提出物と幾何一致まで
突き合わせた記録は `docs/06_verify_migration.md` / `08_migration_td4.md` /
`09_rebuild_sclk_spi.md`。

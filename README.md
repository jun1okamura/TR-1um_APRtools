# TR-1um_APRtools

TR-1um（OpenSUSI / IP62、1 µm CMOS・M1/M2 の 2 層配線）向けの**自作 配置配線ツール群**と、
標準セル・マクロの共通データ、および蓄積した設計知見の集約先。

商用 EDA も一般的な OSS フローも 3 層以上の配線を前提にするため、TR-1um には使えない。
そこで `TR-1um_Async_I2C` 以来 4 世代にわたって自作してきた P&R 一式を、
**設計ごとにコピーするのをやめて 1 箇所にまとめる**のがこのリポジトリの目的。

## 状態

**データ移動・ドキュメント整備・命名の正規化まで完了し、提出物が再生成できることを確認済み。**

> - `TR-1um_I2C_2026` の `step10/route_step_6_squeezed.gds` が提出済みの原本と
>   **ビット単位で一致**（GDS 9 本 + JSON 16 本、全 25 項目）
> - `vdd`/`vss` 統一後もチップ 5 本の GDS が **幾何 XOR 空**（差はラベル 16 個のみ）、
>   `pre_check.py` OK
> - 抽出ネットリストで **ngspice 14 項目回帰 All PASSED**
>
> → [`docs/06_verify_migration.md`](docs/06_verify_migration.md)

決定済み: 参照は **git submodule** / P&R の正本は `TR-1um_I2C_2026` 世代 /
STDCELL は **v59_4（行高 59.4）** / コア幅は **トラックピッチ 5.4 µm の整数倍** /
電源ピン名は **`vdd`・`vss`**（**コア側のみ完了**。チップ側は U21） / **`*_nrow_fm` を剥がす** /
環境変数は **`APR_*`** / `legacy/` は同梱 / `OSS_DRV` を含むフレームは**上流に PR 済み**
（マージまで `pdk/pending-upstream/` を使う）。

残りは `apr/from_sclk_spi/` の統合・`apr/` のサブディレクトリ分割・
チップ側レール名（U21）・TD4 / SCLK_SPI での同一検証
（`docs/90_improvement_notes.md` §7）。

## 構成

```
apr/          P&R エンジン（81 + from_sclk_spi/ 9 ファイル）
              config_base.py  設計非依存の既定値と導出 + check()
              rules.py        DRC 値・レイヤ番号・グリッドの単一ソース
              apr_path.py     設計ルートを sys.path に足す
              selfcheck.py    実行環境と下ごしらえを点検（KLayout 不要）
              cmp_gds.py      GDS を正規化 md5 + 幾何 XOR で比べる
syn/          合成・STA（syn.sh / abc.constr / tr1um.genlib / sta/）
char/         セル特性化（スクリプト + 特性化結果）
stdcell/      v59_4（正本） / v64_8（凍結） / CELLS.md
macro/        ringosc/ regfile/
art/          opensusi_logo.txt
templates/    設計側のひな形
pdk/          README のみ。★ PDK のデータは置かない
legacy/       移植原本（read-only）
docs/         下記
```

## 使い方

```sh
git submodule add git@github.com:jun1okamura/TR-1um_APRtools.git tools/APRtools
```

設計ディレクトリを **cwd** にして、`apr/` を `PYTHONPATH` に置いて呼ぶ。
`apr/apr_path.py` が cwd（または `APR_DESIGN_ROOT`）を `sys.path` の**末尾**に
足すので、設計の `config.py` がそこから読まれる。

```sh
export TR1UM_PDK=~/Dropbox/91_OpenPDK/TR-1um      # PDK は参照する（コピーしない）
export APRTOOLS=~/Dropbox/91_OpenPDK/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
export PYTHONHASHSEED=0                            # ルータが非決定的（docs/40_gotchas.md）

cd ~/Dropbox/98_LSI_Design/<design>
python3 $APRTOOLS/apr/selfcheck.py                 # KLayout 無しで下ごしらえを点検
python3 $APRTOOLS/apr/place.py
python3 $APRTOOLS/apr/route.py
```

設計側に置くのは `config.py`（`config_base` を継承）と RTL / LEF / 期待値、
そして**刺激が設計固有のテストベンチ生成**だけ（`templates/` にひな形）。

## ドキュメント

### 決定・移行

| 文書 | 内容 |
|---|---|
| [`docs/00_directory.md`](docs/00_directory.md) | ディレクトリ構成、共通/設計固有の 4 層モデル、移行手順 |
| [`docs/01_inventory.md`](docs/01_inventory.md) | 3 リポジトリの資産棚卸しと移行対応表 |
| [`docs/02_stdcell_diff.md`](docs/02_stdcell_diff.md) | STDCELL 2 世代の差分 → v59_4 を正本に決定 |
| [`docs/03_core_geometry.md`](docs/03_core_geometry.md) | コア幅のパラメータ化（5.4 µm の整数倍）と TAP 列の上限 |
| [`docs/04_naming.md`](docs/04_naming.md) | 命名の正規化計画（`vdd`/`vss` / `*` / `APR_*`） |
| [`docs/05_migration_log.md`](docs/05_migration_log.md) | **データ移動の記録** — 何を移し、何を移さなかったか |
| [`docs/06_verify_migration.md`](docs/06_verify_migration.md) | **移行の検証** — md5 一致の手順と結果 |
| [`pdk/README.md`](pdk/README.md) | **PDK は参照しコピーしない** — 対象一覧 |
| [`docs/07_frame_issue.md`](docs/07_frame_issue.md) | **フレーム GDS の問題（U19 / U22）** — 同名ファイル 2 つと `OSS_DRV` のずれ、および決定 |
| [`pdk/PR-TR-1um-OSS_DRV.md`](pdk/PR-TR-1um-OSS_DRV.md) | **PDK への PR 本文**（`fix/oss-drv-gio-frame`・push 済み、CI 確認中） |
| [`pdk/pending-upstream/README.md`](pdk/pending-upstream/README.md) | 上流 PR 待ちのデータ（マージされたら消す） |

### 技術資料

| 文書 | 内容 |
|---|---|
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
| [`docs/40_gotchas.md`](docs/40_gotchas.md) | **踏んだ穴 — 設計非依存の落とし穴集**（★ は 2 回以上踏んだもの） |
| [`docs/90_improvement_notes.md`](docs/90_improvement_notes.md) | **改善準備の記録** — 負債・再発した失敗・改善候補・未解決 |

## 出所

| リポジトリ | 世代 | 貢献 |
|---|---|---|
| `TR-1um_Async_I2C` | 原本 | チャネルルータ、リング配線エンジン、5 パス配線 |
| `TR-1um_SCLK_SPI` | 2 代目 | 設定の単一ソース化、ポート接続性検証、セル単体 DRC、Liberty 生成 |
| `TR-1um_TD4` | 3 代目 | ハードマクロ対応、メモリアレイ（TLAT/REG8x16/MEMPORT）、特性化フロー |
| `TR-1um_I2C_2026` | 4 代目 | 配置のパッド近接項、トップピン振り分け、PDK 公式 DRC/LVS、RING_OSC 同居 |

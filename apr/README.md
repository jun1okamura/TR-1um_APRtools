# `apr/` の中身 — 91 本の地図

> **★ ファイルは 1 本も動かしていない。** `apr/` 直下に平置きのまま、**ここに分類表を置く**
> ことにした（2026-09-15 の決定）。動かす案も検討したが、純粋なライブラリは実測で
> **3 本しかなく**（`apr_path` / `rules` / `netlist_util`）、しかもその 3 本は docs から
> 18 箇所参照されている。**移動の危険に見合う見通しの改善が無い**。
> この 2 日で壊れた 39 件のうち **35 件が「パスと名前」**だったことも効いている。
>
> **この表は `apr/lint.py` の `file-table` が検査する**（決定 20「表・台帳は 1 箇所」）。
> `apr/*.py` を足したら**ここに 1 行足さないと lint が NG になる**。

## 回し方に出るのはこの 21 本だけ

残り 70 本は、**下請け・単発の道具・図・ライブラリ作り**。
下の表の「流」列が ○ のものが、この 21 本。

```sh
python3 $APRTOOLS/apr/selfcheck.py                 # 実行環境 + 命名 + 縦の詰まり + lint
python3 $APRTOOLS/apr/explore_rows.py              # 行数の当たり（決め直すときだけ）
python3 $APRTOOLS/apr/mkcellinfo.py                # layout/cell_info.json（無ければ）
python3 $APRTOOLS/apr/place.py                     # step1〜4
python3 $APRTOOLS/apr/route.py                     # step5〜11
python3 $APRTOOLS/apr/assemble_top.py              # チップ step1
python3 $APRTOOLS/apr/gen_top_routing_plan.py
python3 $APRTOOLS/apr/route_chip.py                # チップ step2
python3 $APRTOOLS/apr/add_top_pins.py              # チップ step3
python3 $APRTOOLS/apr/verify_chip.py
python3 $APRTOOLS/apr/place_logo.py                # チップ step4（I2C だけ配線の前）
python3 $APRTOOLS/apr/mklvsnet.py && python3 $APRTOOLS/apr/mkchipnet.py
python3 $APRTOOLS/apr/export_mpw.py
python3 $APRTOOLS/apr/pre_check.py src/<chip_top>.gds --top <chip_top>   # 上流のゲート。click が要る
#   ★ export_mpw.py が**同じ 4 項目を既に見ている**（トップ 1 個 / dbu / bbox / フレーム）。
#     手元で上流版まで回すなら `pip install click`。回さなくても提出物は出る。
python3 $APRTOOLS/apr/drc_pdk.py / lvs_pdk.py      # サインオフ
python3 $APRTOOLS/apr/gen_chip_sim_ready.py        # ngspice
python3 $APRTOOLS/apr/cmp_gds.py HEAD:<path> <path>   # 再現の確認
```

`gen_chip_tb.py` は流れに出るが **TD4 の期待値が埋まっている**（U25）。他設計は自分の `scripts/gen_chip_tb.py` を使う。

## 分類表

列の意味 — **流**: 回し方に出る / **行**: 行数 / **読**: `apr/` の何本がこれを `import` するか

### A. 基盤 — 設定・定数・パス

**ここだけは全員が読む。** 値を書き足すならまずここを見る。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `apr_path.py` |  | 25 | 53 | 設計ルートを `sys.path` に足すブートストラップ。**53 本が読む。** これを `apr/` 直下から動かすと自分を見つけられない |
| `config_base.py` |  | 930 |  | 設計非依存の既定値と導出。設計の `config.py` が `from config_base import *` で読む。`ENV_KNOBS`（39 個の台帳）と `chip_stack()` もここ |
| `rules.py` |  | 179 | 14 | プロセス定数の単一ソース（レイヤ番号・DRC 値・グリッド・フレーム実測値・電源名の写像）。**数値を他所に書き写さない** |
| `lib_query.py` |  | 130 |  | Liberty から値を引く（ピンの入力容量 / `min_pulse_width`）。`syn.sh` / `sta.sh` が **`set_load` を写さずに `.lib` から取る**ために使う（U99）。`rules.py` と同じ「数値を書き写さない」の系統 |
| `check_copies.py` |  | 165 |  | 設計側に残る**同名の写し**を数えて分ける（同一 / 古いだけ / 設計固有 / CI）。**「古いだけ」が事故の形**（U89 / U14）。`# copy: ok <理由>` で残す理由を書ける。`check_no_home_paths.py` と同じ「数えて言う」系統（U94）|

### B. 合成のあと — ネットリスト加工

yosys の出力を P&R に渡せる形にする。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `netlist_parser.py` |  | 98 | 7 | 構造 Verilog を読む（`mklvsnet` など 7 本が読む） |
| `netlist_util.py` |  | 103 | 6 | yosys `write_verilog -noattr` の最小の読み書き（6 本が読む） |
| `insert_bufth.py` |  | 194 |  | 外部入力を `BUFTH`（シュミットトリガ）で一度受ける。対象ネットは `config.BUFTH_NETS` |
| `dedup_gates.py` |  | 189 |  | 同じ入力の同じゲートをまとめる |
| `merge_muxdffrb_rslatch.py` |  | 301 |  | `MUX + DFFRB` を `RSLATCH` に寄せる（TD4）。`.VDD(VDD)` を書くので TB は `--power` が要る |
| `syn_report.py` |  | 87 |  | マッピング後のネットリストから面積と所要コア面積を出す |
| `syn_equiv.py` |  | 121 |  | RTL とマッピング後のネットリストが同じ回路かを形式的に確かめる |
| `cmp_cells.py` |  | 82 |  | 2 つのマップ後ネットリストのセル構成を突き合わせる |

### C. 配置

`place.py` が step1〜4。残りは下請けと検算。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `place.py` | ○ | 845 | 2 | 標準セル配置。**STEP ごとに GDS を残す**。`PYTHONHASHSEED=0` に自分で再 exec する |
| `explore_rows.py` | ○ | 240 |  | 行数の当たりを付ける（決め直すときだけ） |
| `mkcellinfo.py` | ○ | 97 |  | 配置器が使うセル寸法表 `layout/cell_info.json` を作る |
| `lef_parser.py` |  | 76 | 4 | LEF を読む（`place` / `gen_placement_*` / `verify_port_connectivity`） |
| `frame_pins.py` |  | 98 | 2 | GIO パッドリングのピン幾何を GDS から読む |
| `gen_placement_gds.py` |  | 134 | 2 | 配置結果を GDS に落とす |
| `gen_placement_json.py` |  | 196 | 1 | ルータが読む配置 JSON へ変換する |
| `compress_channels.py` |  | 136 |  | 一度配線して使用トラック数を測り、チャネル高を詰めて**回し直す**（`squeeze_channels` は引き直さない方） |
| `squeeze_channels.py` |  | 496 | 1 | 既存配線を保ったままチャネルを詰める |
| `sweep_height.py` |  | 132 |  | コア高を詰めるための探索 |
| `sweep_seed.py` |  | 115 |  | 配置シードを振って、配線して短絡が最少になる配置を選ぶ |
| `verify_placement.py` |  | 166 |  | 配置結果の検証（重なり・グリッド・行） |

### D. 配線（コア）

`route.py` が step5〜11。**下の 10 本は `route.py` が順に呼ぶ**ので単体で回すことは普通ない。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `route.py` | ○ | 429 |  | 配置 GDS → 配線済みコア。step5〜11 のパイプライン |
| `route_channels.py` |  | 2688 | 2 | チャネルルータ本体（2,688 行。`apr/` で最大） |
| `route_top_pins.py` |  | 785 | 1 | トップピンまで引き出す |
| `ripup_reroute_shorts.py` |  | 1295 | 1 | 短絡を剥がして引き直す（1,295 行） |
| `add_power_pins.py` |  | 126 | 1 | 電源ピンを打つ |
| `highlight_top_pins.py` |  | 300 | 3 | トップピンの到達を色分けして出す |
| `connect_macro_power.py` |  | 259 | 3 | マクロの電源をコアのレールに繋ぐ（step11） |
| `detect_loops_jogs.py` |  | 170 |  | `net_shapes_*.json` のループ・無駄な折れを機械で洗う |
| `verify_connectivity.py` |  | 125 |  | 接続性。ピンを **M1 だけ**で引く版。トップピンを打つ前用で、フローは回さない |
| `verify_connectivity_m1m2.py` |  | 130 |  | 接続性。ピンを **M1 で引き、外れたら M2**。**`route.py` が step7 で回すのはこちら** |
| `verify_port_connectivity.py` |  | 203 | 1 | **トップピンが本当にセルまで届いているか** |

### E. チップ（フレームに載せる）

コアを `OSS_FRAME_GIO` に落としてから MPW に出すまで。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `assemble_top.py` | ○ | 205 |  | 配線済みコアをパッドリングに落とす（チップ step1） |
| `gen_top_routing_plan.py` | ○ | 355 | 1 | チップレベルの接続表と配線プラン。`PAD_MAP` を読む |
| `check_top_channels.py` | ○ | 228 |  | **配線前**にチャネルの容量を見積もる（チップ step2b）。輪を 1 本の座標へ伸ばして区間の重なりを数える。1 本 1 トラックの**下限** |
| `route_chip.py` | ○ | 1210 |  | コアをパッドリングに配線する（チップ step2）。電源の描き方は `CHIP_POWER` で 3 方式 |
| `add_top_pins.py` | ○ | 158 |  | ボンドパッドに LVS 用のピンを打つ（チップ step3） |
| `place_logo.py` | ○ | 204 |  | 空いているところに OpenSUSI のロゴを置く（チップ step4） |
| `verify_chip.py` | ○ | 260 |  | チップ配線の接続性と短絡。**コアの電源タップ 0 本は NG**（U21） |
| `export_mpw.py` | ○ | 139 |  | MPW に出す 2 つのファイルを `src/` に置く。config と `info.yaml` の食い違いも見る |
| `pre_check.py` | ○ | 143 |  | MPW テンプレート同梱の提出前ゲート。**上流由来（Apache-2.0）なので値を変えない**。`pya` と `click` に依存 |
| `mkleffrm.py` |  | 388 |  | フレームとパッドセルの LEF を生成する |

### F. 抽出と LVS ソース

**「レイアウトから起こす」側と「設計意図から起こす」側**。LVS はこの 2 つを突き合わせる。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `klayout_extract.py` |  | 197 | 6 | KLayout のエンジンで GDS からネットリストを抽出する（6 本が読む） |
| `gds_extract.py` |  | 263 |  | STDCELL GDS から 1 セルを簡易抽出して SPICE サブサーキットを起こす |
| `mklvsnet.py` | ○ | 492 |  | 配置配線したコアの LVS ソースネットリスト（492 行） |
| `mkchipnet.py` | ○ | 352 |  | チップレベルの LVS ソース。フレーム側が無ければ `mkframespice` を呼んで起こす（U40） |
| `mkframespice.py` |  | 173 | 1 | フレームの LVS ソース。`write()` は `mkchipnet` からも呼ばれる |
| `lvs_pnr.py` |  | 193 |  | 配置配線したコアの LVS（レイアウト抽出 vs 設計意図） |
| `lvs_check.py` |  | 67 |  | 書き出した `.spice` がレイアウトと一致するかを KLayout の比較器で確かめる |
| `netcmp.py` |  | 154 |  | 2 つの SPICE サブサーキットをグラフ同型判定で突き合わせる（LVS の予行演習） |
| `label_check.py` |  | 174 |  | 電源ラベルが正しいネットに乗っているかを**素子の側から**検査する |
| `gen_cell_spice.py` |  | 349 |  | `stdcell/<世代>/TR-1um_STDCELL.spice` を組む |
| `check_cell_spice.py` |  | 194 |  | LVS 参照ネットリストをレイアウトと突き合わせる。**`BUF_X2` は GDS の 6 が正しい**と docstring が言っている（U49） |

### G. DRC・静的検査・比較

**サインオフはここ。** `drc_pdk` / `lvs_pdk` が PDK の本物のデッキ。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `drc_pdk.py` | ○ | 209 | 1 | **PDK の本物の DRC デッキ**を当てて要約する。`--mdp` で提出物も見る |
| `lvs_pdk.py` | ○ | 157 |  | **PDK の本物の LVS デッキ**を当てて要約する |
| `drc_check.py` |  | 107 |  | 自作の簡易 DRC。**デッキと同じ除外**（`MASK`+`SCRB`、パッドの `V1P`）を当てるので、きれいなチップは 0 と出る。**トップセル名を省くとコア名にフォールバック**する |
| `drc_check_cells.py` |  | 201 |  | 自作 DRC を 1 セルずつ当てる。PDK デッキと同じ綴りで 11 規則（`M1.SW` / `M1.W3` / `M2.W3` / `V1.W1` / `V1.GA` を含む）。**スクライブ層のある入力は断る**（セル用）。**本物のデッキと 6 規則で一致を確認済み**（U56） |
| `cmp_gds.py` | ○ | 240 |  | 2 つの GDS が同じものかを判定する。**生バイトはタイムスタンプで毎回変わる**ので `cmp` ではなくこれ |
| `pin_grid_check.py` |  | 165 |  | prBoundary とピンが配置グリッドに乗っているか |
| `mk_drc_probe.py` |  | 92 |  | **DRC チェッカが空振りしていないか**を見るための違反セルを合成する。`T_OK` は否定対照 |
| `check_no_home_paths.py` | ○ | 107 |  | 追跡ファイルに**個人のホームパス**が入っていないかを数える（U35 / U93）。`git ls-files` の全部を見る。凍結物（`legacy/` `reference/`）は対象外、`path-ok` の行は数えない |
| `lint.py` | ○ | 542 |  | 「パスと名前」を静的に検査する。`escape-apr` / `moved-dir` / `baked-path` / `env-knob` / `rail-map` / `file-table` / `drc-const` / `foreign-path`。**既定で `apr/` `macro/` `char/` を見る**。`--constants` で「`rules.py` の値と一致する数値リテラル」の一覧も出せる |
| `selfcheck.py` | ○ | 224 |  | KLayout 無しで実行環境・命名規則・チップの縦の詰まり・つまみの現在値を点検する |

### H. シミュレーション（ngspice / IRSIM）

**刺激と期待値は設計側の `scripts/` に置く**（U25 で TD4 の 2 本を戻した）。ここに残るのは設計に依らないものだけ。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `gen_chip_sim_ready.py` | ○ | 206 |  | 抽出ネットリストを ngspice で読める形にする |
| `chip_tb_lib.py` |  | 84 | 1 | **TB の設計に依らない部分だけ**。ポート順の読み取り（U42）/ PWL / `models.spice` の生成（U24）/ 置き場の決め方。**刺激と期待値は設計側の `scripts/gen_chip_tb.py`**（U25） |
| `check_ngspice.py` |  | 109 |  | `.meas` の結果をまとめて表にする |
| `frame2sim.py` |  | 92 |  | フレームの `.extracted` を ngspice で回せる形に直す |
| `spi2ngspice.py` |  | 65 |  | LVS ソースネットリスト → ngspice で読める形 |
| `spi2sim.py` |  | 140 |  | SPICE サブサーキット → IRSIM `.sim`（階層フラット化） |
| `gen_irsim_cmd.py` |  | 265 |  | IRSIM コマンドファイル生成 |
| `gen_irsim_timing.py` |  | 139 |  | IRSIM タイミング測定用コマンドファイル生成 |
| `check_irsim_log.py` |  | 119 |  | IRSIM 実行ログの合否集計 |
| `check_irsim_timing.py` |  | 90 |  | IRSIM タイミング測定ログの読み取り |

### I. セルライブラリ（`stdcell/` `char/` 向け）

**設計を回すときは触らない。** ライブラリを作り直すときだけ。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `cellinfo.py` |  | 240 |  | STDCELL GDS を読んでセルの実寸法 / Tr 数 / ピンを表にする |
| `gdsread.py` |  | 100 |  | **依存なしで GDS を読む**（`gdstk` も `klayout` も要らない）。セルごとの図形数 / ラベル / 参照 / bbox を数えて 2 ファイルを突き合わせる。`selfcheck` §3b が使う |
| `sync_cell_info.py` |  | 325 |  | セルを測り直して `cell_info.json` / `cell_char.json` を更新する。`.extracted` が無いセルは **GDS から直接**数える（U33） |
| `gen_liberty.py` |  | 150 |  | 実測値から Liberty を組む。`FUNCS` に無いセルは論理関数なし（U34） |
| `mklef.py` |  | 375 |  | STDCELL GDS から LEF（tech + セル + マクロ）を生成する |
| `gate_count.py` |  | 90 |  | セル / トランジスタ / 面積 / 等価ゲート数の表 |
| `area_estimate.py` |  | 148 |  | yosys `stat` を実測セル面積に換算する |
| `area_custom.py` |  | 81 |  | カスタムセルを当てた面積の再見積り（TD4 / C4004 方針） |

### J. 図（目視確認用・フロー外）

**どれも判定はしない。** 落ちても設計物には影響しない。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `plot_layout.py` |  | 94 |  | 配線済み GDS を PNG に描く |
| `plot_placement.py` |  | 95 |  | 配置 4 STEP の可視化 |
| `plot_floorplan.py` |  | 213 |  | フロアプラン案の可視化 |
| `plot_corridors.py` |  | 160 |  | 優先 M2 コリドー（全行同じ x に抜ける列）の確認 |
| `plot_chip_floorplan.py` |  | 213 |  | チップ組み立ての確認図 |
| `plot_chip_routing.py` |  | 107 |  | チップ配線の確認図（step2） |

### K. GDS の手直し（単発）

**流れの中では呼ばれない。** 手で 1 回当てる道具。

| ファイル | 流 | 行 | 読 | 何をするか |
|---|:--:|--:|--:|---|
| `add_prboundary.py` |  | 111 |  | 階層マクロのトップに prBoundary (235,0) を入れる |
| `normalize_prboundary.py` |  | 171 |  | セルの中身ごと平行移動して prBoundary の左下を原点に揃える |
| `relabel.py` |  | 91 |  | GDS のテキストラベルを一括で改名する |
| `add_addbuf_labels.py` |  | 81 |  | `ADDBUF` のピンにラベルを付ける（LVS の曖昧性解消）。**KLayout マクロ**なので `python3` では回らない |
| `read_info.py` |  | 108 |  | **GDS は読まない。** `info.yaml` から CI の出力変数を組み立てて `$GITHUB_OUTPUT` に書く（GitHub Actions 用） |

## この表から見えること

- **大きい順**: `route_channels` 2688 行 / `ripup_reroute_shorts` 1295 行 / `route_chip` 1210 行 / `config_base` 930 行 / `place` 845 行。上 2 本で `apr/` 全体の 17% を占める。
- **17 本は要約の 1 行目が無いか、当時の依頼文のままだった**（`add_power_pins.py` の 「(this session, user request:」など）。本文は長いのに**何をするファイルなのかが 1 行目に書いていない**状態で、この表の元にもならなかった。2026-09-15 に全部書いた（U51）。残っている経緯記述が参照する `design_notes.md` は `legacy/async_i2c/` にある。
- `apr_path` を **53 本**が読む。**`apr/` 直下から動かせない唯一のファイル**（`sys.path` を組み立てる本人なので、自分を探せなくなる）。
- `route.py` は下請けを 8 本呼ぶ。**D 群を単体で回すことは普通ない。**
- J 群（図）と K 群（単発）の 11 本は、落ちても設計物に影響しない。

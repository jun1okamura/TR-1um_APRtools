# 命名の正規化計画

作成: 2026-09-14 / 更新: 2026-09-15 / 状態: **実施済み（コア側）**

APRtools への集約に伴う機械的な改名を 3 件まとめる。いずれも **`apr/` へ投入する
タイミングで一括**でやる（設計リポジトリ 3 つが同時に影響を受けるため、小出しにすると
どの版がどの名前かわからなくなる）。

| # | 対象 | 決定 |
|---|---|---|
| 1 | 電源ピン名 | **`vdd` / `vss`（小文字）に統一** |
| 2 | `*` サフィックス | **剥がす**（ファイル名・モジュール名・JSON 名・トップセル名） |
| 3 | `TD4_*` 環境変数 | **`APR_*` に統一** |

---

## 0. 日本語の用語

| 英語 | 日本語 | 使わない |
|---|---|---|
| net | **ネット** | ~~網~~ |

**2026-09-18、設計者指示。** ネットリストの `net` は日本語でも**ネット**と書く。
「網」は使わない（`legacy/` と各設計の `reference/` は凍結物なので対象外）。
一括置換したのは **4 リポジトリ 61 ファイル / 266 箇所**。
★ **`網羅`（coverage）は別の語なので置換しない。**

---

## 1. 電源ピン名を `vdd` / `vss` に統一

### 1-1. 現状は 3 つの名前空間が混在している

| 層 | 現在の名前 | 出どころ |
|---|---|---|
| セルピン（v59_4 LEF / GDS） | **`vdd` / `vss`** | `TR-1um_cells.lef`、配置 JSON の TAP ピンも `vdd`/`vss` |
| セルピン（v64_8 LEF、凍結） | `VDD` / `GND` | `TR-1um_STDCELL.lef` |
| コアのトップピン・ラベル | **`VDD` / `GND`** | 自作フローが付けている |
| フレーム / ボンドパッド | **`VDD` / `VSS`** | `OSS_FRAME_GIO` の LEF ピン名 |

`I2C_2026/scripts/pnr/*.py` の文字列リテラル実測: `"VDD"` 49 / `"GND"` 45 / `"VSS"` 17 /
`"vdd"` 15 / `"vss"` 16。**セルは既に小文字なのにスクリプトは大文字のまま**という
ちぐはぐな状態。

### 1-2. 方針

- **自作フローが名前を決める場所は全て小文字 `vdd` / `vss`**
  — コアのトップピン、ラベル (48,0)/(49,0)、LVS ソースネットリスト、電源メッシュのネット名
- **`GND` は使わない**（`vss` に統一）
- **フレーム由来の名前は変えない** — ボンドパッドのラベルは `OSS_FRAME_GIO` が持っている
  `VDD` / `VSS` のまま。ここは自作側の裁量ではない
- 名前は `apr/rules.py` の定数から取る:

```python
# apr/rules.py
PWR_NET   = "vdd"
GND_NET   = "vss"
PAD_PWR   = "VDD"    # フレーム側。変更不可
PAD_GND   = "VSS"    # 同上
```

### 1-3. ★ 大小だけで区別しない

**SPICE は大文字小文字を区別しない。** TD4 のメモリ LVS 第 5 回で、内部線 `web` と
ポート `WEB` が同一ネットに潰れ、WE バッファ 2 段の入出力が短絡して見えた
（内部線を `WEBI` に改名して解決）。

したがって:

- `VDD` → `vdd` の改名そのものは LVS を壊さない（もともと同一視されている）
- しかし **`vdd` と `VDD` を別のネットとして扱う設計は作れない**。
  改名の途中で「コア側 `vdd` / パッド側 `VDD`」を別ネットのつもりで配線してはいけない
- KLayout の SPICE リーダは回路名を大文字化するので、**照合は大小無視で行う**

### 1-4. 実際にやったこと（コア側）

`apr/rules.py` に `PWR_NET = "vdd"` / `GND_NET = "vss"` を置き、**コアのレール名を
決めている箇所だけ**を定数参照に置き換えた:

| ファイル | 変更 |
|---|---|
| `add_power_pins.py` | step9 が書くラベル `"GND"`/`"VDD"` → `rules.GND_NET`/`PWR_NET` |
| `highlight_top_pins.py` | 同上 |
| `route.py` | `POWER_PORTS` と `check_port_pins(extra=)`（旧名も弾くようにした） |
| `mklvsnet.py` | `PWR` タプル。ついでに `SIM_DIR` を `stdcell/v59_4/simulation` へ |
| `lvs_pnr.py` | 電源ネットの判定 |
| `route_chip.py` | `core_power_pins()` の辞書キー（**コアのラベルを読むので結合している**） |

**検証**: 図形は 15 本すべて完全一致。差分は step9 / step10 のラベル文字列だけで、
`GND 8 → 0` / `VDD 8 → 0` / `vdd 61 → 69` / `vss 58 → 66`
（= TAP 列 4 × 2 辺 = 8 個ずつが小文字側へ移った）。JSON は全一致。

### 1-5. ★ 保留 — チップ側のレール名

`route_chip.py` の描画・`mkchipnet.py` の `RAIL` マップ・`verify_chip.py` の
プローブは**まだ `"VDD"`/`"GND"` を使っている**。理由:

- チップ組み立てはフレームを要するが、**フレームが PDK 版とずれている（U19）**ため
  いま回しても結果を信用できない
- 本プロジェクトの原則は「最終判断は PDK 公式デッキで取る」。検証できない改名はしない

**2026-09-15 追記**: チップ組み立てを実際に回したところ、`route_chip.py` の
`core_power_pins()` がコアのラベルを名前で拾っていたため `KeyError: 'GND'` で止まった。
→ **境界で写像する**形にした（`RAIL_OF = {vdd: "VDD", vss: "GND", …}`。旧世代の
大文字ラベルも読める）。これでチップ段は通り、**幾何は原本と完全一致**することを確認済み
（`docs/06_verify_migration.md` §5-c）。

残るチップ側の小文字化（`route_chip.py` の描画・`mkchipnet.py` の `RAIL`・
`verify_chip.py` のプローブ）は**独立してできる**。LVS で名前が効くので、
`lvs_pdk.py` を回せる環境でやること。**ボンドパッド側の `VDD` / `VSS` は
フレームの LEF ピン名なので変更しない。**

---

## 2. `*` を剥がす

`nrow` = N 行、`fm` = Fiduccia–Mattheyses（行割り当ての分割アルゴリズム）。
移植の世代を示す痕跡で、**いまや全てのスクリプトが N 行対応・FM 分割なので情報量がゼロ**。

`I2C_2026` での実測: 文字列 `nrow_fm` は **22 ファイル / 約 130 箇所**に出現。

### 2-1. モジュール名

**実施済み**（2026-09-15、`apr/` はまだフラット。サブディレクトリ分割は別の段）:

| 旧 | 新（現在の `apr/`） | 将来（分割後） |
|---|---|---|
| `route_channels_nrow_fm.py` | `route_channels.py` | `route/channels.py` |
| `route_top_pins_nrow_fm.py` | `route_top_pins.py` | `route/top_pins.py` |
| `add_power_pins_nrow_fm.py` | `add_power_pins.py` | `route/power_pins.py` |
| `squeeze_channels_nrow_fm.py` | `squeeze_channels.py` | `route/squeeze.py` |
| `compress_channels_nrow_fm.py` | `compress_channels.py` | `route/compress.py` |
| `highlight_top_pins_nrow_fm.py` | `highlight_top_pins.py` | `route/highlight_top_pins.py` |
| `gen_placement_gds_nrow_fm.py` | `gen_placement_gds.py` | `place/gen_gds.py` |
| `drc_check_nrow_fm.py` | `drc_check.py` | `verify/drc_check.py` |
| `verify_connectivity_nrow_fm.py` | `verify_connectivity.py` | `verify/connectivity.py` |
| `verify_connectivity_nrow_fm_m1m2.py` | `verify_connectivity_m1m2.py` | `verify/connectivity_m1m2.py` |

`ripup_reroute_shorts.py` は `_nrow_fm` を含まないのでそのまま。

### 2-2. 成果物（JSON）

**パスは全て `config` の 1 箇所で定義されている**ので、改名は config + 各スクリプト内の
リテラル数個で済む。

| 現在 | 改名後 |
|---|---|
| `placement.json` | `placement.json` |
| `pin_map.json` | `pin_map.json` |
| `pin_map_rr.json` / `_sq` / `_tp` | `pin_map_rr.json` / `_sq` / `_tp` |
| `net_shapes.json` | `net_shapes.json` |
| `net_shapes_rr/_sq/_tp/_tp2.json` | `net_shapes_rr/_sq/_tp/_tp2.json` |
| `channel_usage.json` | `channel_usage.json` |
| `force_jog_events.json` | `force_jog_events.json` |
| `per_row_spine_events.json` | `per_row_spine_events.json` |
| `compaction_info.json` | `compaction_info.json` |

`layout/stepN/route_step_N_*.gds` の命名は**変えない**（既に世代非依存）。

### 2-3. トップセル名

現在: `i2c_slave_async` / `td4_soc_arr` / `spi_slave_sclk`

**`TOP_CELL_NAME` は全スクリプトが既に `_cfg.TOP_CELL_NAME` 経由で参照しており、
リテラルは config の 1 行だけ**（確認済み）。したがって改名は config を書き換えるだけ。

推奨: **`<module>_core`**（例 `spi_slave_sclk_core`）。

> **⚠ ただしトップセル名を変えると連動するものがある**:
> - `layout/**/simulation/<トップセル名>.spice` — KLayout の LVS デッキは
>   「レイアウト GDS と同じディレクトリの `simulation/<セル名>.spice`」を探す
> - `*.extracted` の中身
> - GDS 内のセル名（過去の step GDS は再生成が必要）
>
> **既に提出済みの設計（SCLK_SPI / TD4 / I2C_2026）のトップセル名は変えない。**
> 改名するのは**これから作る設計から**。SCLK_SPI は再設計なので新名でよい。

### 2-4. 作業

1. `apr/` へ投入するときにファイル名を §2-1 で置く
2. import 文を書き換える（`import route_channels` → `from apr.route import channels`）
3. `config_base.py` の成果物パスを §2-2 で置く
4. 残った `nrow_fm` リテラルを `grep -rn nrow_fm apr/` でゼロにする
5. `legacy/` 配下は**改名しない**（原本の同一性を保つため）

---

## 3. `TD4_*` → `APR_*`

config 側の環境変数は `I2C_*` に改名済みだが、**ルータ本体のチューニング用は `TD4_*` のまま
19 ファイルに残っている**。しかも `I2C_TRACK_PITCH` と `TD4_TRACK_PITCH` が**二重定義**で、
config 側に設定してもルータに届かない（実質バグ）。

| 現在 | 改名後 | 既定 | 意味 |
|---|---|---|---|
| `TD4_TRACK_PITCH` / `I2C_TRACK_PITCH` | **`APR_TRACK_PITCH`**（統合） | 5.4 | ★二重定義を解消 |
| `TD4_PRL_MIN_PINS` | `APR_PRL_MIN_PINS` | 5 | per-row-local の最小ピン数 |
| `TD4_PRL_NETS` | `APR_PRL_NETS` | — | per-row-local 指定ネット |
| `TD4_FORCE_JOG` | `APR_FORCE_JOG` | — | 強制ジョグネット |
| `TD4_SPAN_LANE_PACK` | `APR_SPAN_LANE_PACK` | 0 | spanning のレーン詰め |
| `TD4_RIPUP_AFTER_TOPPINS` | `APR_RIPUP_AFTER_TOPPINS` | 1 | step8b の有無 |
| `TD4_COMPONENT_CHECK` | `APR_COMPONENT_CHECK` | 1 | union-find 短絡検査 |
| `TD4_SIMPLE_PIN_MAX` | `APR_SIMPLE_PIN_MAX` | 60 | |
| `TD4_STRICT_MAX_TRACKS` | `APR_STRICT_MAX_TRACKS` | 30 | |
| `TD4_DEBUG_STRICT` | `APR_DEBUG_STRICT` | — | |
| `TD4_PROTECT_PAD` | `APR_PROTECT_PAD` | 1 | 圧縮時の保護区間膨らませ |
| `TD4_TOPPIN_RIGHT` | `APR_TOPPIN_RIGHT` | auto | |
| `TD4_TOPPIN_ADJACENT_CH` | `APR_TOPPIN_ADJACENT_CH` | 1 | |
| `I2C_TOPPIN_SIDE_BY_X` | `APR_TOPPIN_SIDE_BY_X` | 1 | ピン x で辺を選ぶ |
| `TD4_MACRO_MODE` / `_POWER` / `_ROW` | `APR_MACRO_MODE` / `_POWER` / `_ROW` | | |
| `TD4_SIDE_BUS` / `_SLACK` / `_PINS` | `APR_SIDE_BUS` / `_SLACK` / `_PINS` | | |
| `TD4_N_ROWS` / `I2C_N_ROWS` | `APR_N_ROWS` | | |
| `TD4_CH_HEIGHTS` / `I2C_CH_HEIGHTS` | `APR_CH_HEIGHTS` | | |
| `TD4_USE_FILL1` / `I2C_USE_FILL1` | `APR_USE_FILL1` | | |
| `TD4_PRI_CELL` / `_PITCH` / `_MODE` / `_X` | `APR_PRI_CELL` / `_PITCH` / `_MODE` / `_X` | | |
| `I2C_PAD_WEIGHT` | `APR_PAD_WEIGHT` | 1.0 | 配置のパッド近接重み |
| `I2C_CORE_WIDTH` | `APR_CORE_WIDTH_TRACKS` | | ★トラック本数に変更（`docs/03_core_geometry.md`） |
| `I2C_NO_BOTTOM_PORTS` | `APR_NO_BOTTOM_PORTS` | | |
| `I2C_RINGOSC_X/Y` / `_LOGO_GAP` / `_CORE_LOGO_GAP` / `_CORE_CENTER` | `APR_*` | | |
| `TR1UM_PDK` | **`TR1UM_PDK`（そのまま）** | | PDK チェックアウト位置 |

### 3-1. 方針

**直接 `os.environ` を読まない。** `apr/config_base.py` に

```python
def getenv(name, default=None, cast=None): ...   # "APR_" を自動で付ける
```

を置き、各モジュールは `cfg.getenv("PROTECT_PAD", 1, int)` と書く。
これで**変数名の一覧が config に集まり、二重定義が構造的に起きなくなる**。

---

## 4. 実施順と確認

改名は**動作が変わらないこと**が唯一の合格条件。順序:

| # | 作業 | 確認 |
|---|---|---|
| 1 | `apr/` に I2C_2026 版をそのまま投入し、動くことを確認 | I2C_2026 を submodule 参照に切り替えて `place.py` → `route.py` を通し、**step10 の GDS が md5 で一致**すること |
| 2 | `TD4_*` → `APR_*`（§3） | 同上。環境変数を全部既定のままで md5 一致 |
| 3 | `*` 剥がし（§2） | JSON 名が変わるので md5 比較は GDS のみ。**短絡 0 / DRC 0 / LVS 一致**を再確認 |
| 4 | 電源ピン名の統一（§1） | `lvs_pdk.py` で素子数・ネット数・ポート数が変わらないこと |
| 5 | `legacy/` を凍結（改名対象外） | |

> **`PYTHONHASHSEED=0` を立てたうえで**比較すること。ルータは非決定的で、
> 同じ入力から短絡 3 件 → 0 件と揺れた実績がある（`docs/90_improvement_notes.md` 2-6）。

# 配線 — step5〜step11

対象: `apr/route.py`（ステージドライバ）と、それが呼ぶ
`gen_placement_json.py` / `gen_placement_gds.py` / `route_channels.py` /
`ripup_reroute_shorts.py` / `route_top_pins.py` / `highlight_top_pins.py` /
`add_power_pins.py` / `squeeze_channels.py` / `connect_macro_power.py`

```sh
export TR1UM_PDK=<PDK>            # via_1 PCell に必須
python3 apr/route.py              # step5..step10(11)
python3 apr/route.py --from 6 --to 6   # 配線だけやり直す
python3 apr/plot_layout.py layout/step10/route_step_6_squeezed.gds -o layout/routed.png
```

## 1. ステップ

| STEP | スクリプト | 出力 |
|---|---|---|
| **step5** | `gen_placement_json.py` + `gen_placement_gds.py` | `layout/placement*.json` / `step5/route_step_1_placement.gds` |
| **step6** | `route_channels.py`（本体・158 KB） | `step6/route_step_2_*.gds` + `pin_map` / `net_shapes` / `channel_usage` / `force_jog_events` / `compaction_info` JSON |
| **step7** | `ripup_reroute_shorts.py`（引数末尾 = `SIMPLE_PIN_MAX`、既定 60） | `step7/route_step_3_ripup_reroute.gds` |
| **step8** | `route_top_pins.py` | `step8/route_step_4_top_pins.gds` |
| **step8b** | `ripup_reroute_shorts.py` 再実行（引数 30。`APR_RIPUP_AFTER_TOPPINS=0` で無効） | step8 を上書き |
| **step9** | `add_power_pins.py` | `step9/route_step_5_power_pins.gds` |
| **step10** | `squeeze_channels.py` | `step10/route_step_6_squeezed.gds` ※通常はここが最終 |
| **step11** | `connect_macro_power.py` | `step11/route_step_7_macro_power.gds`（縦置きマクロがある設計のみ） |

> **★ step5 をフローの外に置かない。** 以前 `gen_placement_json.py` は手で叩く別コマンドで、
> 忘れると**前の設計の配置を今のネットリストに対して配線**していた。
> 症状は step8 でトップポートが 1 本黙って消えるだけ。`docs/40_gotchas.md` §4-4

> **★ 最終 GDS の選択は存在チェック付きで config に持たせる。**
> TD4 は `APR_MACRO_MODE` を付け忘れて step10（マクロの電源が金属で何にも繋がっていないコア）を
> チップに組み込んだ。`CHIP_CORE_GDS = MACROPWR_GDS if exists else FINAL_GDS`

## 2. step5 — 配置 JSON への変換

`place.py` の出力を**ルータのスキーマ**に直す:
- LEF のピン矩形を絶対座標化
- ネット解決（バスの別名は `BUS_PORT_NET_ALIAS` でビットごとに展開が要る。
  スカラーは `netlist_parser` の union-find が解決する）
- TAP 直後の `FILL2` を `FILLPRI_*` に（優先コリドー）
- **レイヤ名を `M1`/`M2` に正規化。** LEF は `METAL1`/`METAL2` と書くがルータは `"M2"` と
  文字列比較するので、直さないと**ピンが 1 本も見つからないまま静かに通る**。
  知らない名前は `SystemExit`

## 3. step6 — チャネル配線の 5 パス

各パスの結果も GDS に落ちる（`route_step_2_{1..5}_*.gds` + `routed_raw.gds`）。

| パス | 内容 |
|---|---|
| 1 | **TAP2 電源メッシュ**（`draw_tap_power_mesh()`）。TAP の vdd/vss M2 ストラップをチャネル越しに繋ぎ、その x 範囲を `x_forbidden` に登録 |
| 2 | **行内ローカル配線**（トランク + スタブ） |
| 3 | **高ファンアウト / 隣接ペア**。`HIGH_FO_THRESHOLD = 8` ピン以上は専用トラック領域を先頭に確保し、両側に `HIGH_FO_GUARD_TRACKS = 1` 本の空きトラック |
| 4 | **複数行またぎ（spanning）**。`find_row_clear_x` で「その行の実セル M2 が無い x」を探し、必要なら `draw_jog`（via_1 → M1 水平 → via_1）で 1 回だけ x を変える |
| 5 | **強制ジョグ**（`APR_FORCE_JOG`） |

### 内部定数

```
M1_TRUNK_WIDTH 1.8   M1_PAD_SIZE 3.4   M2_MIN_GAP 2.0
TRACK0_OFFSET  2.0   LANE_MARGIN 2.0   X_GRID 5.4
HIGH_FO_THRESHOLD 8  HIGH_FO_GUARD_TRACKS 1
TAP_GND_X_LOCAL (1.0, 4.4)   TAP_VDD_X_LOCAL (6.4, 9.8)   TAP_STRAP_MARGIN 1.1
```

**トラックピッチ 5.4 の下限検査**が入っており、下回ると `SystemExit`（根拠は `docs/10_pdk_facts.md` §4）。

### ★ 同じネットでも via のカット間隔は見る

`exclude_net` は「同じネットなら 1 本の導体」の趣旨だが、**DRC のカット間隔だけは導体が
同じでも効く**。カット 1.4 + 間隔 1.5 → **中心間 2.9 µm 以上**を同じトラック上で要求する。

### ★ spanning のレーンを詰めない（`APR_SPAN_LANE_PACK=1` で従来に戻る）

`assign_lanes` は**ジョグ前**の区間でレーンを決めるのに、トランクは**ジョグ後**のピン x で
描かれる。行またぎでピンが右へ動くとトランクが割り当て時の区間を飛び出して隣人を踏む。
使われないトラックは step10 の圧縮が丸ごと削るので、**詰めない方が安い**。

### ★ 途中の行でも「次のレグ」を見る

最後に跨ぐ行だけ先の走行を条件に入れていたので、途中の行では行を跨いだ先が塞がった x を
平気で選び、そこから `draw_jog` が無検査フォールバックへ落ちていた。

## 4. チャネル予算

```python
CH_HEIGHTS = [...]        # 長さ = N_ROWS + 1（下マージン / 行間 … / 上マージン）
```

**方針は「広めに取って配線 → step10 で圧縮」。**
`place.py` のネット交差数ベースの見積もりでは必ず不足する
（**ルータのジョグ機構は行またぎ 1 本ごとに新しいトラックを確保する**ため）。

実測（SCLK_SPI・2 行）:

| | 予算 | 使用 | 圧縮後 |
|---|---:|---:|---:|
| ch0（下） | 140.0 (26 trk) | 8 | 42.8 |
| ch1（行間） | 900.0 (166 trk) | 25 | 138.6 |
| ch2（上） | 160.0 (29 trk) | 3 | 22.6（PIN 保護 +3.0） |
| **コア高** | **1,329.6** | | **314.1（−76.4%）** |

### ★ `CH_HEIGHTS` の上下端は 5.4 の倍数にする

131.6 / 153.2 のままだと ch0 の最上トラックが row0 のセルの M1 に 1.2 µm まで寄り、
**M1 間隔違反が 3 件**出る（step6 で発生し step10 まで残る）。140.4（26 トラック）/
162.0（30 トラック）で 0 件。

### ★ 縦置きマクロがある設計では多めにしてはいけない

マクロは参照なので**圧縮がその y 範囲を貫通できず**、マクロが跨ぐチャネルの余りが
そのままコア高に乗る。

## 5. step7 / step8b — リップアップ再配線

`find_conflicts` は net_shapes の箱同士の**正の重なり**しか見ない。漏れるのは
① 違うネットの箱がぴったり接している（隙間 0）② **via のパッド**（via は net_shapes に載らない）。
→ `component_conflicts`（`APR_COMPONENT_CHECK`、既定 1）が step10 と同じ union-find を
リップアップのループ内で回す。

**片側ドッグレッグ**（`try_fix_vertical_detour`）: 全長を別列へ移す従来の直し方は
(a) 全長クリアな列 (b) 両端の via を持ち上げる自由、の両方が要る。ドッグレッグはどちらも
要らず、重なっている所だけ横へ逃がす。
**ドッグレッグが足す via も全部クリアチェックすること**（落として M1 間隔 2 件 + V1 間隔 1 件を出した）。

## 6. step8 — トップピンの引き出し

### ★ ポート名はネットリストから導出する

`highlight_top_pins.py` に I2C 設計のポート名が直書きされており、
その表に載るポートしか探さなかった。**スカラーポート 9 本がまるごと未引き出しのまま
最終 GDS に残った**（バス 16 本だけ偶然一致して通っていた）。
→ `input` / `output` 宣言から導出する（`PORT_DIR` も）。`docs/40_gotchas.md` §4-1

### ★ 左右の振り分けは「行」でなく「ピンの x」で（`APR_TOPPIN_SIDE_BY_X`、既定 1）

行単位だと 4 行 + `NO_BOTTOM_PORTS` で row0/1 のポートが全部右へ回り、
**左端のピンが右端まで 1,400 µm 走る**。実測: `rx_data[5]`（x=229.5）が x=1598.4 まで引かれ
`[CHECK] 経路が空いていない` と自己申告したうえで `scl_gated` と短絡した。

### 行数への写像

`route_top_pins.py` は N 行に一般化済み（`by_row[n_rows-1]`、中間行の前半→右端 /
後半→左端）。**`n_rows == 4` では原本と完全に同一挙動**であることを確認済み。

`NO_BOTTOM_PORTS = 1` はコアの下に別のブロック（ロゴ / RING_OSC / マクロ帯）を積む設計で立てる。

### ★ step8 には無検査フォールバックがある

「どのトラックも衝突するので一番マシなものを選んだ」（ログの `[CHECK]`）。
→ step8 の形状も `net_shapes` に記録して **step8b で再度リップアップ**する。

## 7. step9 — 電源ピン

TAP 列 × 2 ネット × 2 辺（y=0 と y=core_h）に M2PIN (49,1) + TXM2 (49,0) の
`vdd` / `vss` を置く（4 列なら 16 個）。

## 8. step10 — チャネル圧縮

未使用トラックを削ってコア高を詰める。**2 つの穴に注意**（どちらも実害が出た）:

1. **トップ辺の PIN マーカーを高さ 0 に潰す**（SCLK_SPI で 18 個）。
   → (48,1)/(49,1)/(48,0)/(49,0) の Y 区間を `protect_y` として identity にする。
   **保護分の 3.0 µm だけコアが高くなる**（311.1 → 314.1）
2. **`compaction_info` は step6 の記録で、step7/8 が足した配線を知らない**。
   記録上「未使用」のトラックに実際は M1 が乗っていてスライスごと削られ、
   **M1 が高さ 0 に潰れて隣と地続き**になる（実測: 短絡 1 + V1 間隔違反 1）。
   → 入力 GDS の M1 を実測して使用トラックに足す

`APR_PROTECT_PAD`（既定 1 トラック）で保護区間を膨らませる。0 にすると保護区間のすぐ脇に
次のトラックが寄って **M1 間隔違反 15 件**。1 で足りるのは M1 パッド 3.4 + 最小間隔 1.4 = 4.8 < 5.4 だから。

> **★ 縮退値をそのまま渡さない。** マクロを持たない設計では `macro_box()` が `(0,0,0,0)` を返す。
> そのまま `extra_protect` に渡すと y=0 に幅ゼロの保護区間ができ、`PROTECT_PAD` で
> ±1 トラック膨らんで **ch[0] の底が理由もなく圧縮から外れる**。

## 9. 自動検査（`route.py:checks()`）

| チェック | 見るもの |
|---|---|
| `drc_check.py <gds> <top>` | M1/M2/V1 の幅・間隔のみ。**トップセルを必ず明示** |
| `verify_connectivity_m1m2.py` | 短絡と導通（ルータが記録したネット） |
| `check_port_pins()` | 全トップポートに PIN マーカーがあるか |
| **`verify_port_connectivity.py`** | **PIN マーカーが実際にセルピンへ届いているか**（ジオメトリの連結成分） |

step8 直後と step10 後の 2 回走らせる。

> **★ 自作チェッカの 0 は根拠にならない。** 最終判断は `drc_pdk.py` / `lvs_pdk.py` と CI。
> 自作チェッカに無いルール（`M1.SW` / 最大幅 45 µm）は `docs/10_pdk_facts.md` §3-2。

## 10. 非決定性

同じ配置 JSON（md5 一致）から step6 が **3 短絡 → 0 短絡と揺れた**。
どこかで集合を反復している（**原因未特定**）。
→ `route.py` / `place.py` の `__main__` で `PYTHONHASHSEED=0` を立てて `os.execv` で起動し直す。

関連: **import 時に確定する値が 1 つ前の実行を見る**。
`PER_ROW_LOCAL_NETS` が読む `PLACEMENT_JSON` は step5 が作り直すので、import 時点では
前回のものが残る。→ 関数化して使う時点で呼ぶ。行数アサートも `place.py` の生出力から取る。

## 11. 設計固有の名指し

| 変数 | 意味 |
|---|---|
| `PER_ROW_LOCAL_NETS` | 行内ローカルに固定するネット名 |
| `APR_FORCE_JOG` | 強制ジョグ |
| `APR_PRL_MIN_PINS` / `APR_PRL_NETS` | per-row-local の閾値と指定 |
| `DOWN_FACING_INSTS` | ピンが下向きにしか出ないインスタンス（`MEMPORT` など） |
| `NO_BOTTOM_PORTS` | 下辺にトップピンを出さない |

いずれも `config.py` に置く。SCLK_SPI は `FORCE_HIGH_FO_NETS` / `FORCE_JOG_NETS` が空で済んだ
（spanning ネットが 0 だったため）が、I2C は多数の個別チューニングを要した。

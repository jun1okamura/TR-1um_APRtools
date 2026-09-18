# TD4 の移行（2026-09-15）

`TR-1um_TD4` を APRtools で回す。`docs/06_verify_migration.md` の I2C と同じ
やり方で、**提出済みの成果物と突き合わせて**進める。

## 結論 — **コアもチップも再現した**

| 段 | 結果 |
|---|---|
| `config.py`（旧 `td4_config.py` との導出値の照合） | **35/35 一致** |
| 配置 `place.py`（引数なし） | マクロ・行幅 1150.2・TAP `[0, 378, 756, 1139.4]` |
| 配線 `route.py`（step5〜11） | **短絡 0 / 14 ポート全接続** |
| コア最終 `step11` | **幾何は完全一致**（556,244 B 同値） |
| チップ `step2_routed` / `step3_top_pins` | **幾何は完全一致**（622,018 / 624,978 B 同値） |
| チップ最終 `step4_final` | **幾何は完全一致**（666,410 B 同値） |

**差は全段とも電源ラベル 16 個だけ**（`GND`/`VDD` -> `vss`/`vdd`）。
図形は 1 つも動いていない。I2C と同じ絵になった。

## 再現に要った設定

旧 `td4_config.py` は**環境変数 6 個 + `--seed 1`** を毎回手で並べる作り
だった（`scripts/pnr/README.md`）:

```sh
TD4_MACRO_MODE=portrait TD4_MACRO_ROW=1 TD4_PRI_CELL=FILL3 \
TD4_SIDE_BUS=8 TD4_SIDE_BUS_PINS="Q[" \
TD4_CH_HEIGHTS="250,450,230,190,190,85.4" \
  python3 scripts/pnr/place.py --seed 1
```

全部 `config.py` に入れた。**引数も環境変数も無しで再現する**
（`docs/40_gotchas.md` §4-0）。

`PAD_WEIGHT = 0.0` が要る。TD4 の提出はパッド近接（`docs/21_flow_place.md`
§6）が**入る前の世代**なので、0 にして当時と同じ評価関数に戻す。

## APRtools 側で直したもの

| # | 症状 | 対処 |
|---|---|---|
| 1 | `TAP_X` が `[0, 534.6, 1069.2, 1139.4]` になり最後の区間が 70.2 µm | `tap_columns()` が**痩せすぎた最後の区間も**等間隔に振り直す。刻みは 1 回だけ丸める（i ごとに丸めると 756.0 が 761.4 になる） |
| 2 | 縦置きの行幅が出ない | `finalize()` が `MACRO_SIDE_GAP = SLACK + TRACKS x 5.4`、`ROW_WIDTH = CORE - MACRO_W - GAP` を導出 |
| 3 | その `MACRO_SIDE_GAP` が 0.0 のまま | **`setdefault` が空振りしていた**。`from config_base import *` で `MACRO_SIDE_GAP = 0.0` が設計の名前空間に既に入っているので、`ns.setdefault` は必ず既存値を見る。導出値は代入で決める |
| 4 | `core_size()` を設計で上書きしても `chip_core_box()` が base を呼ぶ | `_f(name)` を通す。**Python の名前解決はモジュール単位**なので、`import *` した後の上書きは base の中からは見えない |
| 5 | `CH_HEIGHTS` の端が 5.4 の倍数でないと止まる | TD4 は 250.0 / 85.4 で **DRC 0**。`CH_END_OFF_GRID_OK = True` で警告に落とす（既提出設計の再現用） |
| 6 | `gen_top_routing_plan.py` の `PAD_MAP` が I2C 直書き | **`config.py` から取る**（U20 解決）。I2C の表は `TR-1um_I2C_2026/config.py` へ移した |
| 7 | `RING_OSC` が無い設計で落ちる | `RING_OSC_ORIGIN` が無ければ素通し |
| 8 | チップの段の順番が I2C 固定（`step1c_logo.gds` が無い） | `CHIP_*_GDS` を `config.py` で組み替えられるようにした。I2C はロゴが配線の**前**、TD4 は**後** |

**8 件のうち 7 件が「パスと名前」。** `apr/lint.py` を入れた後でも、
`lint` が見ているのは*書き方*なので、**設計 2 つ目を実際に回して初めて出る**
類（既定値・導出式・段の順番）はこうして出る。

## U30 — チップ床の直書きを解いた（解決）

`route_chip.py` は I2C のチップ床を実測値で持っていて、TD4 で走らせると
**存在しない RING_OSC の電源バーを描いた**。原因は 2 つの世代で
**電源の取り方そのものが違う**こと:

| | APR_2026（`ringosc`） | TD4（`top_bottom`） |
|---|---|---|
| 下のチャネル | RING_OSC の帯とロゴで**塞がっている** | 空いている |
| VDD | 上辺のタップ -> 上のバス(804) | 上辺のタップ -> 上のバス(690) |
| GND | **上辺**のタップ -> バス(790) -> リング | **下辺**のタップ -> 下のバス(-690) |
| 下辺 VSS 壁ピン | RING_OSC 下の VSS バー経由 | バスからまっすぐ |
| 追加の構造 | RING_OSC 上下の M1 バスバー + コア両脇のストラップ | 無し |

定数をいじって済む話ではないので、**電源の描き方を 2 つの関数に分けて
`config.CHIP_POWER` が選ぶ**形にした（`power_ringosc` / `power_top_bottom`）。
`power_ringosc` は今までのコードをそのまま移しただけで、
**I2C の `step2_routed.gds` は正規化 md5 が 1 ビットも変わっていない**
ことを確認してある。

あわせて設計で違う値を `config.py` へ:

| 値 | APR_2026 | TD4 |
|---|---|---|
| `CHIP_POWER` | `ringosc` | `top_bottom` |
| `CHIP_LANE_R0` | 815.4（帯を避ける） | 810.0 |
| `CHIP_VDD_BUS_Y` / `CHIP_GND_BUS_Y` | 804.0 / 790.0 | 690.0 / **-690.0** |
| `CHIP_VDD_CROSS_Y` | 914.5 | 916.0 |
| `LOGO_BOX` | （RING_OSC の上に導出） | (410, -680, 790, -470) |
| `LOGO_SCALE` / `LOGO_COLS` | 1 / 全幅 | 2 / `0:64`（紋章だけ） |

ロゴも同じ形だった。**`--scale 2 --cols 0:64` を手で打つ前提**になっていて、
既定のまま回すと「1583 µm が空き 380 µm に入らない」で止まる。
config に入れて引数なしで通るようにした。

## 検証 — DRC / LVS / ngspice も通った（2026-09-15）

x86_64 / KLayout 0.28.16 + `--allow-old-klayout`（**サインオフは 0.29 以上で**）。

| 対象 | DRC | LVS |
|---|---|---|
| コア `step11` | **0 件** | **一致**（layout = source = 3597 素子 / 1386 ネット / 16 ピン） |
| チップ `step4_final` | **0 件** | **一致**（4225 / 1503 / 16） |
| 提出 GDS `src/tr_1um_jun1okamura.gds` | **0 件** | — |
| MDP マスク（`run_mdp` → `run_IP62`） | **0 件**（マスク 6.0 MB） | — |

`pre_check.py` OK（トップセル名 / dbu 0.001 / 2500 µm 角 / フレームあり）。
素子・ネット・ピンの数は `docs/30_verify_drc_lvs.md` §4 の実績表と**同じ数字**。

### ngspice — 12 サイクルすべて期待どおり

レイアウト抽出から起こしたネットリストで LED フラッシャが回る:

```
OUT = 3, 6, 12, 8, 8, 3, 6, 12, 8, 8, 3, 6   （CF は終始 0）
```

`JMP` のサイクルは `OUT` が動かないので 1 周 5 サイクルで `[3,6,12,8,8]`。

### この段で追加で直したもの

| # | 症状 | 対処 |
|---|---|---|
| 9 | `mkchipnet.py` が RING_OSC の 3 つ目のインスタンスを前提にしている | `cfg.HAS_RING_OSC` で畳む。**`RING_OSC_CELL` は既定で名前が入っているので、セル名の有無で判定してはいけない**（最初それで嵌った） |
| 10 | `gen_chip_sim_ready.py` の既定 GDS が `step3_top_pins.gds` 固定 | `cfg.CHIP_FINAL_GDS`（TD4 は `step4_final`） |

`TR-1um_TD4` リポジトリの成果物は**そのまま**にしてある（提出済みで、
幾何は今回の再生成と完全一致。電源ラベルだけが違う）。

## 分かったこと

- **STDCELL は TD4 と APRtools で 4 ファイルともバイト一致**。
  `TR-1um_cells.lef` / `TR-1um_STDCELL.gds` に `REG8x16` が入っている
  ので、マクロを持つ設計でも APRtools の STDCELL をそのまま使える
  （`MEMPORT` だけが別の `TR-1um_PNR.*` 側にあったが、U89 でフローの
  入力から外した）。
  差があるのは Liberty（`tr1um_typ_5v0_25c.lib`）だけで、これは合成用。
  **TD4 の `out/*.v` は古い Liberty で合成されている**ので、再合成すると
  ネットリストが変わる（再現には触らない）。
- `layout/portrait/portrait_5row_bus8_clean_step10.gds` は提出版とは**別の
  実験**。step11 とは繋がらない（step11 の方が提出版）。

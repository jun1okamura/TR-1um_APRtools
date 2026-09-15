# TD4 の移行（2026-09-15）

`TR-1um_TD4` を APRtools で回す。`docs/06_verify_migration.md` の I2C と同じ
やり方で、**提出済みの成果物と突き合わせて**進める。

## 結論（現時点）

| 段 | 結果 |
|---|---|
| `config.py`（旧 `td4_config.py` との導出値の照合） | **35/35 一致** |
| 配置 `place.py`（引数なし） | 通る。マクロ・行幅・TAP まで一致 |
| 配線 `route.py`（step5〜11） | 通る。**短絡 0 / 14 ポート全接続** |
| **コア最終 `step11`** | **幾何は完全一致**（Region XOR 全層で空）。差は電源ラベル 16 個だけ |
| チップ組み立て | **まだ通らない** — `route_chip.py` が I2C のチップ床を直書き（U30） |

**コアは再現した。** `portrait_5row_bus8_pwr_step11.gds`（提出時の版）と
バイト数まで同じ 556,244 B で、`GND`/`VDD` -> `vss`/`vdd` の 16 ラベル以外は
図形が 1 つも動いていない。I2C と同じ絵になった。

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

## 残り — U30: `route_chip.py` がチップ床を直書きしている

チップ配線は TD4 では**まだ回せない**。`route_chip.py` はモジュール先頭に
I2C のチップ床を実測値で持っている:

```
RO_STRAP_X = {"VDD": (-801.9, 807.3), "GND": (-807.3, 801.9)}
RO_M2_TOP, RO_M2_BOT = -537.1, -758.1     # RING_OSC の M2 の上端 / 下端
RO_VDD_BAR_Y, RO_VDD_BAR_W = -522.5, 6.0
VDD_BUS_Y = 804.0 / GND_BUS_Y = 790.0 / GND_RING_R = 884.0 / VDD_RING_R = 902.0
```

TD4 で走らせると、**存在しない `RING_OSC` の電源バーを描く**。
コア段（place/route）が設計非依存になっているのに対し、チップ段は
**4 世代のうち I2C の 1 世代ぶんしか入っていない**。

次にやること（順に）:

1. `RING_OSC` に関する描画を `cfg.RING_OSC_*` が無ければ丸ごと畳む
2. バスバー / リング半径 / ストラップ x を `config_base` の導出か
   `config.py` の値にする（`docs/11_frame_io.md` の実測値が根拠）
3. TD4 のチップを `layout/chip/step4_final.gds` と突き合わせる

## 分かったこと

- **STDCELL は TD4 と APRtools で 4 ファイルともバイト一致**。
  `TR-1um_PNR.lef` / `.gds` には `REG8x16` と `MEMPORT` が既に入っている
  ので、マクロを持つ設計でも APRtools の STDCELL をそのまま使える。
  差があるのは Liberty（`tr1um_typ_5v0_25c.lib`）だけで、これは合成用。
  **TD4 の `out/*.v` は古い Liberty で合成されている**ので、再合成すると
  ネットリストが変わる（再現には触らない）。
- `layout/portrait/portrait_5row_bus8_clean_step10.gds` は提出版とは**別の
  実験**。step11 とは繋がらない（step11 の方が提出版）。

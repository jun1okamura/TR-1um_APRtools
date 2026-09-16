# 配置 — step1〜step4

対象: `apr/place.py`、`apr/verify_placement.py`、`apr/mkcellinfo.py`、
`apr/sweep_seed.py` / `sweep_height.py`、`apr/plot_placement.py`

## 1. 事前

```sh
python3 apr/mkcellinfo.py        # -> layout/cell_info.json
```

LEF の `SIZE` と GDS の prBoundary (235,0) を突き合わせ、**食い違ったら停止**する。

## 2. ステップ

```sh
python3 apr/place.py             # step1..step4
python3 apr/verify_placement.py
python3 apr/plot_placement.py    # -> layout/placement_steps.png
```

| STEP | 内容 | 成果物 |
|---|---|---|
| step1 | **行割り当て**（FM 風ハイパーグラフ分割、`cut_cost`） | `layout/step1/place_step1_rows.gds` / `.json` |
| step2 | **行内順序**（バリセンタ反復、HPWL 評価） | `layout/step2/place_step2_ordered.gds` |
| step3 | **TAP 挿入**（固定ピッチのセグメント分割） | `layout/step3/place_step3_tap.gds` |
| step4 | **FILL 挿入**（行幅を厳密に揃える）※最終 | `layout/step4/place_step4_fill.gds` / `.json` |

CLI: `--netlist` `--cell-info` `--restarts` `--order-passes` `--seed`
`--fill-mode {alternate,distributed,end}` `--balance-tol`

**既定値は設計の `config.py` から来る**（`PLACE_SEED` / `PLACE_RESTARTS` /
`PLACE_ORDER_PASSES` / `PLACE_BALANCE_TOL` / `PAD_WEIGHT`。優先順は
**環境変数 `APR_*` > config.py > 既定**）。
`I2C_2026` は `PAD_WEIGHT=16.0` / `PLACE_SEED=4` を持つので、
**引数を 1 つも付けずに提出物が再現する**。
使った値は 1 行目に印字され `layout/place_params.json` にも残る
（`docs/40_gotchas.md` §4-0）。

副産物 `layout/row_assignment.json` を `insert_row_buffers.py --row-assignment` に戻す
**2 パス**が正規手順（`docs/20_flow_syn.md` §4）。

## 3. 配置の不変条件（`verify_placement.py` が見る 7 項目）

1. ネットリストのインスタンスが**過不足なく 1 回ずつ**置かれているか
2. 行内アバット（重なり・隙間なし）で、**行幅ちょうど**で終わるか
3. 全部が**サイトグリッド 5.4 µm** に乗っているか
4. **TAP が全行同じ x** か（縦 M2 電源メッシュの前提）
5. マクロ位置
6. コア枠／フレーム開口に収まるか
7. GDS の実体（参照数・実寸）と JSON の一致

加えて全体の約束:

- **全参照が回転 0・反転なし。** 行のミラーリングをしない
- **x=0 から行幅ちょうどまで隙間なく**充填する

## 4. TAP

- セル `TAP2`（幅 10.8）、**ピッチ `534.6 µm`（= 5.4 × 99、I2C 実チップ実測）以内**
- 配置は x=0 から 534.6 刻み + **最後の 1 本を行末（W − 10.8）に固定**
- **4 列で成立するコア幅の上限は 1614.6 µm（= 299 トラック）**。
  詳細と SCLK_SPI の超過事例は `docs/03_core_geometry.md` §2
- 縦置きマクロがある設計では**等間隔に振り直す**（534.6 刻みだと最後の区間だけ極端に狭くなり、
  そこへ回されたセルが入らず step3 が落ちる）

## 5. FILL の詰め方

- **右端に固めない。** 区画ごとの目標量を「残りのセル幅 : 残りの容量」の比（quota）で決め、
  区画内では `alternate`（偶数区画は右寄せ、奇数区画は左寄せ、**全行で同じ振り方**）。
  区画の境目に幅の広い空き列が縦一直線に揃う
- 幅 10.8 の隙間からは via パッド 3.4 + 間隔 2.0 が両側に要るので
  **行またぎ用の x が 1 本しか取れない**。140 µm の塊なら 25 本取れる。
  だから `distributed` より `alternate`
- **優先 M2 コリドー**（`PRI_CELL` 既定 `FILL3`、`PRI_MODE` 既定 `both` = TAP の両側 6 本/行）は
  区画に含めない（グローバル配線用の予約）
- `FILL3`（3 トラック）を使う理由と `FILL1` の扱いは `stdcell/CELLS.md` §2

### ★ コリドーを増やしても効かない

実測（TD4・5 行・配置率 79%）:

| 設定 | 行またぎの clear x 失敗 | 短絡 |
|---|---:|---:|
| ピッチ 108（コリドー 11 本/行） | 63 | **40** |
| TAP 直後のみ（3 本/行） | — | **32** |

同じ x に集まりすぎて互いに衝突する。**効くのは配置率そのもの。**
ただし**短絡が実際に出ている x にだけ 1 本足すのは話が別**
（`PRI_EXTRA_X`。1 本 = 行あたり 16.2 µm で実質タダ）。

## 6. ポートのネットを評価に入れる（APR_2026 移植 (11)）

`cut_cost` は行またぎしか数えず、`hpwl` は `is_port_net` を弾いていた。

実測（2026-09-14、重み無し）: リング配線の回り込みが最大 3,529 µm / 合計 56.9 mm、
同じ辺に出ているのは 32 本中 5 本（`tx_data[5]` は左辺に出るのにパッドは右辺）。

→ 行割当（`cut_cost`）と行内順序（`hpwl`）の**両方にパッド近接項**を追加。
`_EDGE_ROW = {"BOTTOM":0, "TOP":-1, "RIGHT":1, "LEFT":2}`、重み `cfg.PAD_WEIGHT`
（`APR_PAD_WEIGHT` で上書き可）
（既定 1.0、I2C 採用値 **16**）。

> この規約は `route_top_pins` の左右振り分けに依存しており、
> `NO_BOTTOM_PORTS` や行数で意味が変わる。**規約そのものは共通、行数への写像は設計固有。**

## 7. シード掃引

```sh
python3 apr/sweep_seed.py        # seed 1..9
python3 apr/sweep_height.py
```

実測（TD4・縦置き 5 行）: **HPWL は 118.8k〜122.7k とほぼ差が無いのに、短絡は 1〜9 件と
9 倍振れる**。配線の質はランダム性に大きく左右される。

> **★ `sweep_seed.py` は最良シードを捨てることがある。**
> 短絡 0 のとき `PROBLEM(S) FOUND` が出ないのを「配線が落ちた」と誤判定していた
> （seed 1 と 9 が 0 件なのに seed 8 の 1 件を「最良」と報告）。`docs/40_gotchas.md` §4-16

> **★ 比較の前に `PYTHONHASHSEED=0`。** ルータは非決定的（`docs/40_gotchas.md` §4-2）。

### ★ 選んだ値の隣に「どう選んだか」を書く（U61）

掃引で決めた値は `config.py` に入るが、**入っているのは結果だけ**で、
何を振ったのか・掃引したのかどうかが残らない。あとから見た人は
「考えて選んだ 1」と「触っていない 1」を区別できない。

**3 つのどれかを 1 行で書く。**

    PLACE_SEED = 4     # 掃引 1..9 -> 短絡 0 はこれだけ（2026-09-14）
    PLACE_SEED = 1     # 提出時の種。再現のため固定
    PLACE_SEED = 1     # 既定のまま。掃引していない

★ **掃引していないものを「掃引した」と書かない。** 書けることは
「この値で通った」だけで、それは「最良」とは違う。

なぜ要るか: `APR_PAD_WEIGHT=16` を export し忘れた 1 回が別の配置になり、
しかも **cut 131 -> 88 と「良い」方へ動いたので出力を見ても間違いだと
気づけなかった**（`TR-1um_I2C_2026/config.py` に記録）。
**数字が良くなることは、正しさの証拠にならない。**

## 8. 実績

| 設計 | 行 | 行幅 | 配置後コア | 配置率 |
|---|---:|---:|---|---:|
| SCLK_SPI | 2 | 1620.0 | 1,632.6 × 280.8 µm | 63.3% / 75.7% |
| APR_2026 | 4 | 1598.4 | 1,611.0 × 963.2 µm | 約 67% |
| TD4（縦置き） | 5 | 1134.0 | 1,598.4 × 1,347.4 µm | 82.6% |
| TD4（横倒し） | 4 | 1598.4 | 1,611.0 × 1,643.8 µm | 71% |

> 面白い逆転: **配置率が高く「行またぎの空き x が枯れる」はずの縦置きの方が、
> 最終的なコアは小さかった**（マクロ帯 502.2 + 隙間 27.0 = 529.2 µm を丸ごと積まずに済むため。
> 縦置きは行とマクロが高さを共有する）。

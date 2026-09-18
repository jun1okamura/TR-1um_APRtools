# チップ組み立て

対象: `apr/assemble_top.py` / `gen_top_routing_plan.py` / `route_chip.py` /
`add_top_pins.py` / `place_logo.py` / `frame_pins.py` / `verify_chip.py` /
`macro/ringosc/place_ring_osc.py`

> ★ **`check_chip.py` / `pin_list.py` は APRtools に移していない**（U80、
> 2026-09-17）。実体は `TR-1um_SCLK_SPI/scripts/` にあり、U29 で
> `apr/from_sclk_spi/` を統合したときに置いていかれた。**どちらも読むだけの
> 道具**（自作 DRC・ピン表）なので、無くても GDS は出る。回すなら SCLK_SPI の
> ルートから直接呼ぶこと。`check_top_channels.py` は **2026-09-17 に
> `apr/` へ移した**（同じ U80）。

幾何の根拠は `docs/11_frame_io.md`、コア幅の扱いは `docs/03_core_geometry.md`。

## 1. ステップ

| step | スクリプト | 出力 |
|---|---|---|
| 1 | `assemble_top.py` | `layout/chip/step1_assembled.gds`（フレーム @ (0,0) + コアをオフセット。**配置のみ**） |
| 1b | `macro/ringosc/place_ring_osc.py` | `step1b_ringosc.gds`（RING_OSC TEG を載せる設計のみ） |
| 1c/4 | `place_logo.py` | ロゴ + 未使用セル刈り |
| 2a | `gen_top_routing_plan.py` | `gio_connections.json`（論理接続表）/ `signal_routing_plan.json`（物理端点） |
| 2b | `check_top_channels.py` | **配線前**のチャネル容量確認（`signal_routing_plan.json` を読む。回さなくても GDS は出る） |
| 2c | `route_chip.py` | `step2_routed.gds`（PTECT 削除済み） |
| 3 | `add_top_pins.py` | `step3_top_pins.gds`（ボンドパッドに LVS ピン） |
| — | `verify_chip.py` / `check_chip.py` | 検査 |
| — | `pin_list.py` | `docs/pin_list.md` |
| — | `export_mpw.py` | `src/<top>.gds` / `.cir` |

**ロゴを置く位置は設計で違う**: I2C は step1c（コア配置直後）、SCLK_SPI / TD4 は step4（最後）。
`export_mpw.py` がどちらを最終とするかは config で持つ。

## 2. フロアプラン

コアは開口 1,840 × 1,840 µm に落ちる。外側からの半径:

```
921.7   パッド端子（P / HIZ / OUT）と VSS 壁ピン
920.0   フレーム内壁（金属は四辺ともきっかり 920.0）
 …      信号レーン（LANE_R0 から LANE_PITCH = 5.4 刻み）
        コア
```

コアのオフセットは **`ox = -(l + r)/2`（native GDS bbox の中心）**。
縦は設計次第で、コアの下に別ブロックを積む設計では上寄せにする
（I2C: 壁 −920 → 下辺レーン → RING_OSC → 20 µm → ロゴ → 20 µm → コア → 上チャネル → 壁 +920）。

`check_opening()` は**配線が終わってから**使う。

### コリドー（SCLK_SPI の実測例）

```
corridor    width  tracks  needed
T (コア上)   90.0      16      12   ok
R           103.7      19      10   ok
B (PTECT下)  80.0      14       5   ok
L           103.7      19       9   ok
U (コア下)   80.0      14       7   ok
```

## 3. 接続表

`gen_top_routing_plan.py` が 2 つの JSON を出す。

- **`gio_connections.json`** — 論理の接続表（どのパッドのどの端子がどのネットか）
- **`signal_routing_plan.json`** — 物理端点。各ネットについて
  `core`（座標・辺・層・box）/ `gio`（端子名・座標・辺・層）/ `core_native` / `ring_run_um` / `same_edge`

### ★ `PAD_MAP` が唯一の手書き

```python
PAD_MAP = { <pad番号>: {"role": …, "P": …, "OUT": …, "HIZ": …}, … }
UNBONDED = {…}        # パッドに出さないコアポート
PAD_ONLY_NETS = {…}   # パッドだけのネット（例: DIS）
```

「パッド割り当ては設計判断」として明示的に許容されている。全コアポートが突き合わされるので
**抜けはエラーになる**。

> **⚠ `PAD_MAP` はいまも `gen_top_routing_plan.py` の中に直書きされたまま。**
> `config.py` へ出すのが移行時の作業（`docs/05_migration_log.md` §2-2）。

### 端子は GDS から実読みする

`frame_pins.py` がフレーム GDS から `P<n>` / `HIZ<n>` / `OUT<n>` の 42 端子を読む。
**表を手写ししない**（I2C 版はそうしていた）。

### ★ ピンの辺は x でなく層で決めることがある

RING_OSC の `ENB`（帯の左下の M2）を x だけで決めると LEFT になり、M1 の足が
RING_OSC の VSS レールのまん中を走って**引いた瞬間に短絡**する。

## 4. リング配線（`route_chip.py`）

`T/R/B/L` を閉ループ、`U`（コア下）はそこから生えた枝として扱い、
同心レーンに区間を詰め込む。`perimeter_s` / `s_to_xy` / `ring_waypoints` / `project_to_R` /
`seg_layer` / `unroll` / `pack` / `edge_layer()` / `stub_order()` は
**Async_I2C から 4 世代無改変で渡っているエンジン**。

守るべき規則（いずれも実際に踏んで得た。`docs/40_gotchas.md` §5）:

1. **1 ルート = 1 本のポリライン**（別呼び出しに分けると角の via が誰の持ち物でもなくなる）
2. **区間は非ラップの `[min,max]`、向きはその中に収まる方に強制**
3. **同じネット / 同じ端子は 1 本の幹 + 端点ごとの足にまとめる**（I2C で 14 → 10 レーン、総長 −19%）
4. **端子の上に via を打たない**（出ていく向きに合った層を重ねるだけで繋がる）
5. **足の重なり** — 同じ辺で近接するコア側とパッド側の足は、パッド側のレーンが外でないと必ず重なる
6. **1 ネットが何本にも分かれる** — ルートはネット名でなく 1 本ずつの `_key` で持つ

### 定数はフレーム由来

`LANE_R0` / `LANE_PITCH` / `NEAR_R` / `TIE_R` / `VDD_BUS_Y` / `GND_LEG_X` / `VSS_STRIP_*` …
30 個以上が `route_chip.py` に直書きされている。**これらは `OSS_FRAME_GIO` の物理的性質
であって設計固有ではない**ので、フレーム記述オブジェクト + コア幾何からの導出に直すのが
移行時の作業（`docs/03_core_geometry.md` §1）。

## 5. 電源

経路と実装値は `docs/11_frame_io.md` §5。要点:

- **VDD はコア境界の上辺 1 箇所（M1 タップ、くびれ 80 µm）からしか入らない**。VSS は全周
- **TAP 柱はコア上下を貫くので片端給電で足りる**
- **リングの VDD ピン(M1) と VSS ピン(M2) は上辺で重なる。** ライザーは M1 のまま via を置かない
  （**I2C 版はここで一度ショートさせている**）
- 電源 PAD への接続は**幅 10 µm × 5 本、ピッチ 12**（TD4 版の 3.4 µm × 5 本は電流容量 1/3）
- **スタブ幅はコア側ストラップと厳密一致**（幅が変わる継ぎ目はノッチとして拾われる）
- 幅 10 µm の M1 は `M1.SW`（太線間隔 2.0）の境界。周囲 2.0 µm 空ける

### 縦置きマクロの電源（step11）

`connect_macro_power.py`。`REG8x16` を R90 すると電源ポートが左右辺に移り、
左辺は OBS 全面なので**右辺の 2 本ずつだけを上辺へ引き出す**。
マクロ内部で左右は繋がっているので電気的には足りるが、**電流経路は片側だけ**
→ チップの電源メッシュ側で太く受ける。

## 6. PTECT

自作のキープアウト層 (63,1)。配線後に削除するので、**削除後の検証を 3 分割する**:

1. 自分の PTECT マーカーが消えているか（残っていたらルータが走っていない）
2. **フレーム由来の PTECT 3 隅**に金属が入っていないか（消す前後の全レイヤ）
3. 信号ネットが元のボックスに入っていないか（vdd/vss は名指し除外）

> **★ フレームは四隅のうち 3 隅に自前の PTECT を持つ。**
> SCLK_SPI は GND バスバーを右下の (810,−1120)-(1120,−810) に丸ごと入れた。
> **対称性より、そこに実際に何があるかが優先。**

## 7. ボンドパッドの LVS ピン（`add_top_pins.py`）

- 座標と名前は**フレーム GDS の `OSS_PAD` インスタンス**から読む（位置で名前を割り当てない）
- **3.0 × 3.0 µm の M2PIN (49,1) + TXM2 (49,0) のラベル（箱の中心）**
- **★ M2 (20,0) の実体も置く。** ラベルだけではサブサーキットのピンが生えず、
  PDK 公式 LVS だけが `No equivalent pin P<n> … a physical connection is not made` を出す
  （APR_2026 で出力パッド 5 本ちょうどが該当）
- **ピン数は参照ネットリストのトップポート数と厳密一致**

## 8. ロゴ（`place_logo.py`）

`art/opensusi_logo.txt` を **3.0 µm 角の孤立 M2 ドット / 5.0 µm 格子**で置く。
サイズは決め打ちせずビットマップから実測する（`logo_size()`）。
配置エリアはコア高と電源配線から導出できる値なのに、現状ベタ書き
（`AREA = (-795.0, -785.0, 795.0, 453.0)`）。

`place_logo.py` は同時に**未使用セルを刈る**（SCLK_SPI で 17 → 1 トップセル、62 → 44 セル）。
MPW の `pre_check.py` が「トップセルはちょうど 1 つ」を要求するため。

## 9. 検査

| スクリプト | 見るもの |
|---|---|
| `check_top_channels.py` | **配線前**のチャネル容量。1 本 1 トラック・最短の弧で数えた**下限** |
| `verify_chip.py` | 接続の島判定、フレーム電源ピン、RING_OSC のレール |
| `check_chip.py` | DRC 差分 / PTECT 3 分割 / 接続性・短絡 / 電源 / 参照との突き合わせ |
| `drc_pdk.py` | **PDK 公式 DRC。最終判断はこれ** |
| `lvs_pdk.py` | **PDK 公式 LVS。同上** |

> **★ DRC は差分で見る。** パッドリングは元から幅・間隔マーカーを数個持っている
> （`drc_check.py` の M2 width はフレーム自身で 2000 件以上出る）。
> step1（配置だけ）との差を取り、**増えた分だけ**を座標付きで報告する。

> **★ 接続性の probe は層を指定する。** コア左辺の M1 ピンが最左の GND TAP 柱（M2、幅 3.4）と
> 重なる位置にあり、層を省くと左辺 5 本が全部 GND に見える。

> **★ 同名セルの衝突に注意。** `assemble_top.py` が KLayout 既定の `AddToCell` で
> コアとフレーム両方にある `via_1` を重ね、カットが 0.75 µm ずれて**幅 2.15 の V1 が 15 個**できた。
> RING_OSC 取り込みでは旧世代 STDCELL が同名でコア側を上書きし、**DRC 8,449 件**になった。

## 10. MPW エクスポート（`export_mpw.py` → `pre_check.py`）

- トップセル名は **`tr_1um_` で始まり GitHub ユーザ名を含む**
- 提出用コピーの中だけで **`OSS_FRAME_GIO` → `OSS_FRAME` に改名**（GDS とネットリストの両方）。
  `pre_check.py` の `FRAME_CELL_NAMES` に GIO 版が無いため。**上流に PR を出す方針**
- テンプレート同梱の `src/tr_1um_username.*` を削除（残すと間違ったほうを提出する）
- `info.yaml` の `pdk.ref` は**ブランチ名かタグ名のみ**（`git clone --branch` なので SHA 不可）
- ダイ枠 2,500 × 2,500 / dbu 0.001 / トップセルちょうど 1 個

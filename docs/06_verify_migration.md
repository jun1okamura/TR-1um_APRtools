# 移行の検証

実施: 2026-09-15 / 対象: **TR-1um_I2C_2026**（P&R の正本）

> ★ **これは 2026-09-15 の移行検証の記録。** 当時 4 リポジトリが揃ったことの証拠。
> **いまの健全性は `python3 $APRTOOLS/apr/selfcheck.py`** が毎回見る。この記録は更新しない。

| 手順 | 内容 | 結果 |
|---|---|---|
| 1 | import 中立化（素通し） | **31/31 一致** |
| 2 | 環境変数 `APR_*` 統一 | **31/31 一致** |
| 3a | `*_nrow_fm` 剥がし | **31/31 一致**（GDS 15 + JSON 16） |
| 3b | 電源ピン名 `vdd`/`vss`（コア側） | **図形 15/15 一致**、差分はラベル文字列のみ |
| 4 | **チップ組み立て**（step1 → step3） | **全レイヤで幾何 XOR が空。JSON 3 本は完全一致** |

`docs/04_naming.md` §4 の手順どおり、1 段ずつ回して確かめた。

## 1. 何を確かめたか

`apr/` に投入した APR_2026 版のスクリプトが、**import を中立化した後も
提出済みの成果物をそのまま再現する**こと。これが取れて初めて、
改名（`docs/04_naming.md`）やサブディレクトリ分割に進める。

変えたのは import だけ:

| 変更 | 内容 |
|---|---|
| `import i2c_config as cfg` → `import config as cfg` | 50 ファイル |
| `import apr_path` を挿入 | 50 ファイル（設計ルートを `sys.path` に足す） |
| `apr/config_base.py` を新設 | 設計非依存の既定値と導出。設計は `config.py` で上書き |
| `apr/rules.py` を新設 | DRC 値・レイヤ番号・グリッドの単一ソース |
| ライブラリの参照先 | 設計の `lef/` → `stdcell/v59_4/`（**バイト一致を確認済み**） |

**環境変数の `APR_*` 統一と `*` 剥がしはまだやっていない**（手順 2 / 3）。
この検証は「素通しで同じものが出るか」だけを見る。

## 2. 手順

```sh
cd <TR-1um_I2C_2026>
cp <APRtools>/templates/config_i2c_2026_verify.py config.py     # 初回だけ

export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr

python3 $APRTOOLS/apr/selfcheck.py     # 下ごしらえの点検（KLayout 不要）
python3 $APRTOOLS/apr/place.py         # step1〜4
python3 $APRTOOLS/apr/route.py         # step5〜11
```

**引数も、再現に効く環境変数も要らない**（2026-09-15 にそうした）。

| 再現に効くもの | どこにあるか |
|---|---|
| `PYTHONHASHSEED=0` | `place.py` / `route.py` が**自分を起動し直して固定**する |
| `PAD_WEIGHT` / `PLACE_SEED` / `restarts` / `order_passes` | **設計の `config.py`**（`PAD_WEIGHT=16.0` / `PLACE_SEED=4`） |
| 上書きしたいとき（掃引） | `APR_PAD_WEIGHT` / `APR_PLACE_SEED` …（環境変数 > config.py > 既定） |

`place.py` は使った値を毎回 1 行目に印字し、`layout/place_params.json` にも残す。
`selfcheck.py` は回す前にそれを見せ、**環境変数が config.py を上書きしていれば
warn を出す**。

段階を分けたいとき:

```sh
python3 $APRTOOLS/apr/route.py --to 6        # チャネル配線まででいったん止める
python3 $APRTOOLS/apr/route.py --from 7      # 続きから
```

所要は設計機で `place.py` 52 秒 / `route.py` 52 秒。
`route.py` は step ごとに GDS を残すので、途中で落ちてもどこまで進んだか分かる。

> **★ 何と比べるかを決めてから回す。**
> いまの `TR-1um_I2C_2026` は移行後（`vdd`/`vss`・`*_nrow_fm` 剥がし済み）なので、
> **提出当時の md5 表（§4）とは電源ラベルの分だけ一致しない**。
> 再現性を見たいなら比較先は**コミット済みの現物**にする:
>
> ```sh
> git status --short        # 回す前にクリーンであることを確認
> …place/route…
> git status --short        # JSON に差が出なければ配置配線は同一
> python3 $APRTOOLS/apr/cmp_gds.py HEAD:layout/step10/route_step_6_squeezed.gds \
>                                      layout/step10/route_step_6_squeezed.gds
> ```

## 3. 比較の方法

**GDS の生 md5 は使えない。** KLayout は保存のたびに `BGNLIB` / `BGNSTR` に
タイムスタンプを書くので、同じ図形でも毎回違うハッシュになる。
**タイムスタンプのレコードをゼロで潰してから md5 を取る**。

これは `apr/cmp_gds.py` がやる（毎回書き直していたので道具にした）:

```sh
python3 $APRTOOLS/apr/cmp_gds.py <base.gds> <new.gds>
python3 $APRTOOLS/apr/cmp_gds.py HEAD:layout/step10/route_step_6_squeezed.gds \
                                     layout/step10/route_step_6_squeezed.gds
python3 $APRTOOLS/apr/cmp_gds.py --dir <baseDir> <newDir>
```

**不一致のときに「何が違うか」まで出す**のが要点で、正規化 md5 が割れたら
`klayout.db` で層ごとに `Region(base) ^ Region(new)` を取り、テキストは
別に集合の差を出す:

```
[  NG  ] route_step_6_squeezed.gds   正規化 md5 不一致
         → **幾何は完全一致**（Region XOR が全層で空）
         ラベル: base のみ 16 / new のみ 16
           ['GND', 'VDD'] -> ['vdd', 'vss']
```

「md5 が違う」で止めると、**ラベルの改名と本物の配線違いが同じ顔になる**。

中身（`cmp_gds.py` がやっていること）:

```python
import struct, hashlib
def norm(path):
    d = open(path, 'rb').read(); i = 0; out = bytearray()
    while i < len(d) - 4:
        ln, rt = struct.unpack('>HH', d[i:i+4])
        if ln < 4: break
        body = bytes(d[i+4:i+ln])
        if rt in (0x0102, 0x0502):      # BGNLIB / BGNSTR
            body = b'\x00' * len(body)
        out += struct.pack('>HH', ln, rt) + body
        i += ln
    return hashlib.md5(out).hexdigest()
```

JSON は生 md5 でよい。

## 4. 結果

### GDS（正規化 md5）

| ファイル | md5 | サイズ | 判定 |
|---|---|---:|---|
| `step1/place_step1_rows.gds` | `dc37884355b69fd6…` | 162,404 | ✅ |
| `step2/place_step2_ordered.gds` | `f3fed3321ad3a230…` | 162,404 | ✅ |
| `step3/place_step3_tap.gds` | `493ea0e26c162c11…` | 164,640 | ✅ |
| `step4/place_step4_fill.gds` | `9b24e93dc9343235…` | 174,954 | ✅ |
| `step5/route_step_1_placement.gds` | `8db290ce8403c8dc…` | 423,144 | ✅ |
| `step7/route_step_3_ripup_reroute.gds` | `c822b40756d4b63f…` | 529,194 | ✅ |
| `step8/route_step_4_top_pins.gds` | `acaa520f0be4c114…` | 537,330 | ✅ |
| `step9/route_step_5_power_pins.gds` | `d7a378ce33e68e31…` | 538,994 | ✅ |
| **`step10/route_step_6_squeezed.gds`** | **`2b355ba1abfa19cc…`** | **538,994** | **✅** |

step6 の内部チェックポイント 5 本（`route_step_2_*`）は提出リポジトリに残って
いなかったので比較対象外（再実行では生成された）。

### JSON（生 md5）

`placement.json` `pin_map{,_rr,_sq,_tp}.json`
`net_shapes{,_rr,_sq,_tp,_tp2}.json` `channel_usage.json`
`force_jog_events.json` `per_row_spine_events.json`
`compaction_info.json` `row_assignment.json` — **16 本すべて一致**。

### 自己検査の出力（再実行時）

```
Checked 154 nets, 498 pins total.
ALL NETS FULLY CONNECTED, NO SHORTS DETECTED.
ports expected 24 / pin labels 26 / OK
ALL 26 TOP-LEVEL PORTS CONNECTED TO THEIR CELL PINS
```

実行時間: `place.py` 52 秒 / `route.py` 52 秒。

## 5. 副産物として確かめられたこと

| 項目 | 結果 |
|---|---|
| `stdcell/v59_4/` の 5 ファイルが設計の `lef/` と**バイト一致** | ✅（一致していなければ md5 比較に意味が無い） |
| `config_base.tap_columns()` が実績の TAP 列を再現 | ✅ `[0.0, 534.6, 1069.2, 1587.6]`、最大間隔 534.6 |
| `check()` が通る | ✅ コア幅 296 トラック = 1598.4、bbox 1611.0 ≤ 開口 1840.0 |
| PDK の解決（PCell / モデル / デッキ / フレーム） | ✅ |
| `apr/` + `legacy/` 239 ファイルの構文 | ✅ エラー 0 |

## 5-b. 手順 2 / 3 の結果

### 手順 2 — 環境変数 `APR_*` 統一

39 変数 / 23 ファイル。`APR_PAD_WEIGHT=16` で再実行し **31 項目すべて一致**。
副産物として `I2C_TRACK_PITCH`（config 側）と `TD4_TRACK_PITCH`（ルータ側）の
**二重定義が構造的に解消**した（config に設定してもルータに届かなかった）。

### 手順 3a — `*_nrow_fm` 剥がし

モジュール 10 本を改名、23 ファイルから文字列を除去、ハードコードの JSON 名 4 箇所を
config 属性へ。成果物名も新しくなるので**旧名 → 新名の対応で照合**した:

```
GDS  15/15 一致（ファイル名は不変）
JSON 16/16 一致  placement_nrow_fm.json -> placement.json など
```

### 手順 3b — 電源ピン名 `vdd` / `vss`（コア側のみ）

GDS を**テキストレコードを除いて**ハッシュすると **15 本すべて一致** =
図形は 1 つも動いていない。差分はラベル文字列だけ:

| ファイル | 差分 |
|---|---|
| `step9/route_step_5_power_pins.gds` | `GND 8→0` / `VDD 8→0` / `vdd 61→69` / `vss 58→66` |
| `step10/route_step_6_squeezed.gds` | 同上 |

= TAP 列 4 本 × 2 辺 = **8 個ずつが小文字側へ移った**だけ。JSON は全一致。

これで**コアのトップピンとセルピンが同じ名前空間**になり、
「フレームのグランドは `VSS`、コアは `GND`」という食い違い（旧 U11）が消えた。
SPICE は大小を区別しないので LVS 側も `VSS` と同一視される。

**チップ側のレール名は保留**（`docs/04_naming.md` §1-5）。U19 が片付くまで回せない。

## 5-c. 手順 4 — チップ組み立て

```sh
python3 apr/assemble_top.py                     # step1_assembled.gds
python3 macro/ringosc/place_ring_osc.py         # step1b_ringosc.gds
python3 apr/place_logo.py -i …step1b… -o …step1c…
python3 apr/gen_top_routing_plan.py             # gio_connections / signal_routing_plan
python3 apr/route_chip.py                       # step2_routed.gds
python3 apr/add_top_pins.py                     # step3_top_pins.gds
```

フレームは `pdk/pending-upstream/`（`docs/07_frame_issue.md`）。

### 結果

**GDS 5 本すべて、全レイヤで `Region(base) ^ Region(new)` が空**（= 幾何が完全一致）。
トップセル名・セル数（52 / 61 / 62 / 67 / 67）も一致。

| 成果物 | 判定 |
|---|---|
| `step1_assembled.gds` | 幾何 XOR 空 |
| `step1b_ringosc.gds` | 幾何 XOR 空 |
| `step1c_logo.gds` | 幾何 XOR 空 |
| `step2_routed.gds` | 幾何 XOR 空 |
| `step3_top_pins.gds` | 幾何 XOR 空 |
| **`gio_connections.json`** | **md5 一致** |
| **`signal_routing_plan.json`** | **md5 一致** |
| **`step2_routed_net_shapes.json`** | **md5 一致** |

テキストの差は**コアの電源ラベル 16 個だけ**で、**座標は 1 つも動いていない**:

```
base: (49,0,'GND', -796.5, -181.5)   ->   new: (49,0,'vss', -796.5, -181.5)
base: (49,0,'VDD', -791.1, -181.5)   ->   new: (49,0,'vdd', -791.1, -181.5)
                                          … 計 16 個（4 TAP 列 × 2 辺 × 2 ネット）
```

`signal_routing_plan.json` が一致した意味は大きい — **コアのオフセット・ピン座標・
チャネル幅・リング端子の割当が 1 つも変わっていない**ということ。
`step2_routed_net_shapes.json` の一致は**チップレベルのルータが同じ配線を引いた**ということ。

### この段で見つかって直したもの（移行の取りこぼし 3 件）

| # | 症状 | 原因 | 対処 |
|---|---|---|---|
| 1 | `place_logo.py` が `lef/opensusi_logo.txt` を見つけられない | ビットマップのパスが `cfg.ROOT/lef/…` 直書き。ロゴは `art/` へ移動済み | `BITMAP = cfg.LOGO_BITMAP` |
| 2 | `gen_top_routing_plan.py` が「`PAD_MAP` も `UNBONDED` も知らないピン `['vdd','vss']`」で停止 | `POWER_NETS = {"VDD","GND"}` 固定。手順 3b でコアのラベルが小文字になった | `{"VDD","GND","VSS", rules.PWR_NET, rules.GND_NET}` |
| 3 | `route_chip.py` が `KeyError: 'GND'` | `core_power_pins()` の辞書キーだけ小文字化し、呼び出し側は `"VDD"`/`"GND"` のまま | **境界で写像**する（`RAIL_OF`）。チップ側のレール名は据え置き（U21） |

3 は `docs/04_naming.md` §1-5 で「チップ側は保留」と書いた結合がそのまま出たもの。
**コアのラベルを読む 1 箇所で写像する**形にしたので、チップ側を小文字に揃える作業は
独立してできる。

## 5-d. 手順 6 — ngspice（抽出ネットリストで機能回帰）

提出物（GDS / LVS 用ネットリスト）が幾何・接続とも不変であることは 5-c で
確かめた。**動くかどうか**は別なので、移行後のレイアウトから抽出し直して
14 項目回帰を流した。

```sh
python3 $APRTOOLS/apr/gen_chip_sim_ready.py --no-ringosc
python3 scripts/pnr/gen_chip_tb_batch14.py
cd layout/chip/simulation && ngspice -b tb_batch14.spice > batch14.log 2>&1
python3 ../../../scripts/pnr/check_batch14.py batch14.log
```

### 結果

| 見たもの | 結果 |
|---|---|
| `<top>_noosc_sim.spice`（移行前 / 後） | 素の差分 **946 行**、電源名を正規化すると **0 行** |
| `<top>_sim.spice`（RING_OSC 入り） | 同上 |
| `spice_batch14_expected.json` | md5 一致（判定条件は不変） |
| `tb_batch14.spice` | 差は `.include` の絶対パスのみ |
| `ngspice -b tb_batch14.spice` | **All 14 checks PASSED**（解析 164.3 s、x86_64 / ngspice 42） |
| `ngspice -b tb_ringosc.spice` | **6.44992 / 1.79020 MHz** — これまでの記録どおり |

946 行の差は全て `VDD` -> `vdd` / `GND` -> `vss`。**素子は 1 個も動いていない。**
コアの `.SUBCKT` は `i2c_slave_async_nrow_fm vdd … rst_n vss`、チップのパッドは
`VDD` / `VSS` のまま（`rules.PAD_PWR` / `PAD_GND`）で、U21（チップ側のレール名）
が未着手であることがネットリストの上でもそのまま見える。

> DRC / LVS と違って **ngspice は KLayout の CLI を要求しない**ので、
> 移行の検証をどの機械でも回せる。抽出も `pip install klayout` の
> Python API だけで足りる。

### ★ 設計機でも同じ 14/14（§7 の宿題が 1 つ片付いた）

同じ手順を**設計機（macOS / arm64）**で回して、14 項目とも同じ判定・
同じ電圧が出た（`5.000V` / `0.044V` / `0xA5` / `0x3C` …）。

| | クラウド | 設計機 |
|---|---|---|
| 環境 | x86_64 Linux / ngspice 42 | macOS arm64 |
| 結果 | All 14 checks PASSED | **All 14 checks PASSED**（同一の値） |

**アーキテクチャをまたいで数値が一致する**ので、`.tran` の刻みと
`.measure` の時刻がプラットフォーム依存で揺れていないことも同時に分かった。
§7 で挙げた「設計機でも同じ結果になるか」は、**ngspice については確認済み**。
残るのは配置配線の md5（`PYTHONHASHSEED=0` で抑えている非決定性）。

### RING_OSC も移行前と同じ（設計機、2026-09-15）

`tb_ringosc.spice`（`.tran 100p 12u 0 500p`、RING_OSC 入りの `<top>_sim.spice`）:

| | 実測 | これまでの記録 |
|---|---:|---:|
| `OUT`（`INV_X1` × 95） | **6.44992 MHz** | 6.450 MHz |
| `OUTD`（`INV3D` × 95） | **1.79020 MHz** | 1.790 MHz |
| 比 | **3.603** | 3.60 |

**同じ論理・同じ W/L のセルが 3.6 倍違う**のは拡散容量だけの差で、
これが出るのは抽出ネットリストだけ（`docs/31_verify_ngspice.md` §1）。
移行後もその 3.6 倍がそのまま再現したので、**抽出が拾っている
`AS/AD/PS/PD` が移行で壊れていない**ことの裏付けになる。

振幅は `vmax 5.047 V` / `vmin -46 mV`。**電源レール外への行き過ぎ**は
出力パッドの ESD 構造と 10 pF 負荷による普通のリンギングで、
`OSS_ESD_5V_DIO` のダイオードがクランプする範囲内。

解析 180 秒（設計機）。`ENB = P15 = rst_n` なので、**この TB は
RING_OSC 入りの `_sim.spice` を使う**（14 項目回帰の方は `--no-ringosc`）。

### この段で見つかって直したもの（移行の取りこぼし 4・5・6 件目）

| # | 症状 | 原因 | 対処 |
|---|---|---|---|
| 4 | `gen_chip_sim_ready.py` が `apr_root/klayout_extract.py` を探して落ちる | 設計側では `scripts/pnr/` から見た `scripts/klayout_extract.py` だったので `os.path.dirname(HERE)` | `EXTRACT = os.path.join(HERE, "klayout_extract.py")`（APRtools では同じ `apr/` の中） |

| 5 | `route.py` の最終段が `FAIL GND / FAIL VDD  no PIN marker` | ポート名は RTL 由来の `VDD`/`GND`、PIN マーカのラベルは `rules` 由来の `vdd`/`vss`。`verify_port_connectivity.py` がポート名のままマーカを探していた | 境界で写像（`PWR_ALIAS`）。**`step10` の GDS は基準と md5 完全一致だった** |

| 6 | （壊れる前に見つけた）`RING_OSC.spice` の由来コメントが `../../HogeHoge/...` になる | `os.path.relpath(x, cfg.ROOT)` — 設計の外にあるものは機械依存のパスになる | `config_base.disp()`（`$APRTOOLS/...` と書く）。あわせて `mkringoscnet.SIM_DIR` も STDCELL 正本へ |

**この 6 件はいずれも「パスと名前」で、回路の話が 1 つも無い。**
移行で壊れるのはそこだと分かったので、`apr/selfcheck.py` に
「`apr/` 内の相対パス前提が残っていないか」を足す価値がある
（`docs/90_improvement_notes.md`）。

## 6. ★ 次にやること — この検証では触れていないもの

| # | 項目 | 状態 |
|---|---|---|
| 1 | **チップ組み立て（`assemble_top.py` 以降）は未検証。** フレームが要るので、U19（PDK 版とのずれ）を先に片付ける | **その後 完了**（3 設計ともチップまで組み、提出 GDS の正規化 md5 が一致。`apr/cmp_gds.py`） |
| 2 | `APR_*` への環境変数統一 | **完了**（手順 2） |
| 3 | `*_nrow_fm` 剥がし | **完了**（手順 3a） |
| 4 | 電源ピン名の `vdd`/`vss` 統一 | **完了**（手順 3b。コア側のみ。チップ側は U21 で決着） |
| 5 | `apr/from_sclk_spi/` 9 本の統合 | **完了**（U29 の一部） |
| 6 | TD4 / SCLK_SPI でも同じ検証を回す | **完了**（TD4 / SCLK_SPI とも。SPI は再現ではなく作り直し = U32） |
| 7 | `<top>.extracted`（`lvs_pnr.py` の出力）は移行前のまま。**LVS は CI で回す**ので実害は無いが、リポジトリの中では古い | **未確認**（SPI 分は U9） |
| 8 | `tb_*.spice` の `.include` が絶対パス。設計機で作り直さないと読めない（`docs/31_verify_ngspice.md` §0） | **完了**（U24。3 設計とも `models.spice` 経由） |

## 7. 検証環境について

今回は KLayout / gdstk が入る環境で実行した。
**2026-09-15、設計機（macOS / arm64）でも全段が再現した。**

| 段 | クラウド（x86_64 Linux） | 設計機（macOS arm64） |
|---|---|---|
| step1〜4（配置） | 提出時と一致 | **生バイトで提出時と同一**（git に差分が出ない） |
| step5 / 7 / 8 | 正規化 md5 一致 | **同じ値**（`8db290ce…` `c822b407…` `acaa520f…`） |
| step9 / step10 | 幾何 XOR 空・ラベル 16 個 | **同じ**（step10 = `29653a33…`、両環境で一致） |
| ngspice 14 項目 | All PASSED | **All PASSED（電圧まで同一）** |
| RING_OSC | — | 6.44992 / 1.79020 MHz（記録どおり） |

**アーキテクチャをまたいで配置配線が再現する**ので、`PYTHONHASHSEED=0` で
抑えている非決定性が「同じ種と同じ入力なら同じ出力」の範囲に収まっている
ことまで言える（根本原因はなお未特定。`docs/90_improvement_notes.md` §2-6）。

かつてここに書いていた宿題（「設計機でも同じ md5 になることを一度
確認しておくこと」）は、**これで片付いた**。

# フレームの LVS / ngspice ソース（正本）

`OSS_FRAME_GIO` のネットリスト 2 本。**ここが正本**で、設計ごとに作らない。

| ファイル | 用途 | 素子のまとめ |
|---|---|---|
| `OSS_FRAME_GIO_nocombine.spice` | **チップ LVS のソース**（`mkchipnet.py` が読む） | `combine_devices()` を**掛けていない** |
| `OSS_FRAME_GIO.spice` | ngspice（`gen_chip_sim_ready.py` 系） | 掛けてある |

## 出どころ

フレームは PDK から与えられたもので**回路図が無い**。したがってこの 2 本は
**レイアウトから抽出して凍結したもの**であり、これに対する LVS は
「レイアウト vs そのレイアウトから作ったネットリスト」なので**それ自体は何も
証明しない**。意味があるのは、チップ全体の LVS でフレーム部分が既知のネット
リストと一致することを確かめられる点（回帰検査）と、中身が人に読める形で
残る点。

| | |
|---|---|
| 入力 GDS | `pdk/pending-upstream/TR-1um_frame_25x25_GIO.gds` |
| その md5 | `df0d0ec2a88098e572732614c320254c`（**`OSS_DRV` 修正版**。`pdk/PR-TR-1um-OSS_DRV.md`）|
| 抽出 | `apr/klayout_extract.py`（KLayout Python モジュール 0.30.12）|
| 生成日 | 2026-09-19 |
| md5 | `_nocombine` `bb6ef31884c62bc6a868039cf9fd440d` / combine 済み `54990d3381b0a1009a00726d84800b21` |

作り直し:

```sh
python3 $APRTOOLS/apr/mkframespice.py \
        $APRTOOLS/pdk/pending-upstream/TR-1um_frame_25x25_GIO.gds OSS_FRAME_GIO \
        --no-combine -o $APRTOOLS/pdk/frame/OSS_FRAME_GIO_nocombine.spice
python3 $APRTOOLS/apr/mkframespice.py \
        $APRTOOLS/pdk/pending-upstream/TR-1um_frame_25x25_GIO.gds OSS_FRAME_GIO \
        -o $APRTOOLS/pdk/frame/OSS_FRAME_GIO.spice
```

## 確かめたこと（2026-09-19）

- `apr/lvs_check.py` で抽出ネットリストと照合して **2 本とも一致**。
  `circuit 10 / top pin 44 / device 23`（top の pin 44 はリング端子 44 ピン）
- 3 設計に置いてある既存の写し（`TR-1um_I2C_2026` / `TR-1um_TD4` の
  `lef/simulation/`、`TR-1um_SCLK_SPI` の `lef/`）と**本文は完全一致**。
  違うのは由来コメント 3 行だけ（旧世代は `scripts/mkframespice.py` と
  書いており、`OSS_FRAME_GIO.spice` も同じ）

## ★ どのフレーム GDS から作ったかで中身が変わる

上流（`$TR1UM_PDK/libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds`、
md5 `6117a7a0e24ba3616a2abc16ed2200e4`）から作ると **`OSS_DRV` が別物になる**。
`OSS_DRV` は修正で拡散を折り返してあるので、

| | 上流 | 修正版（こちら） |
|---|---:|---:|
| `OSS_DRV` の素子数（`--no-combine`）| 16 | **20** |
| `GN` を駆動する PMOS（combine 後）| W=20.8u 1 個 | **W=19.4u**（14.2 + 5.2）|
| `GP` を駆動する PMOS（combine 後）| W=20.8u | 20.8u（10.4 × 2）|
| `GN` / `GP` の NMOS（combine 後）| W=6.8u | 6.8u（3.4 × 2）|

**折り返しだけではない** — `GN` 側の PMOS は総幅が 20.8 → 19.4 に変わっている。
つまり **combine してもこの 2 つは一致しない**。フレームを取り違えると
チップ LVS がここで落ちる（落ちるのは正しい挙動）。

3 設計の既存の写しはすべて**修正版と一致**する。提出済みの GDS が修正版の
フレームで作られていることの裏づけになっている。

## 使う側

`apr/mkchipnet.py` は `config.py` の `FRAME_LVS_SPICE` を見る。ここを正本に
向けるなら設計の `config.py` に:

```python
FRAME_LVS_SPICE = os.path.join(APRTOOLS_ROOT, "pdk", "frame",
                               "OSS_FRAME_GIO_nocombine.spice")
```

**`config_base.FRAME_LVS_SPICE` の既定はまだ変えていない**（既定は設計の
`lef/simulation/` 以下）。既定を正本に向けると、生成されるチップ .spice の
コメント行が変わって既提出物との差分が出るため、切り替えは別途判断する。

## 上流にマージされたら

`pdk/pending-upstream/` の GDS を消すと `pdk_frame_gds()` は PDK 版を返す。
**そのときはこの 2 本も作り直して md5 を上の表に書き直すこと。**
作り直さないと、入力 GDS と凍結ネットリストの出どころがずれる。

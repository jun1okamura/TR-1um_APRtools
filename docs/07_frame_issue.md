# フレーム GDS の問題（U19）— 整理

作成: 2026-09-15 / 状態: **方針決定済み — TD4 / I2C_2026 版を正とし、PDK へ PR。マージまで Local**

> ★ **これは 2026-09-15 の整理の記録。** いまの状態は台帳の **U19 / U22**
> （`docs/90_improvement_notes.md` §7-1 の索引）。U22 は**上流待ち**で、
> APRtools 側は `_GIO` を明示参照して回避済み。

---

## 1. 問題は 2 つある

### 問題 A — PDK に**同名で中身の違うフレームが 2 つ**ある

`$TR1UM_PDK/libs.tech/klayout/libraries/` に:

| ファイル | サイズ | セル数 | `OSS_FRAME_GIO` | 中身 |
|---|---:|---:|---|---|
| **`TR-1um_frame_25x25.gds`** | 104,994 B | 23 | **無い** | `OSS_FRAME` / `OSS_FRAME_TEG` / `OSS_ESD_5V_ANA`（アナログ 14 パッド）系 |
| **`TR-1um_frame_25x25_GIO.gds`** | 189,858 B | 29 | **ある** | 上記 + `OSS_ESD_5V_DIO` / `OSS_DRV` / `OSS_NCH_DRV` / `OSS_PCH_DRV` |

非 GIO 版のセル一覧（23）:
```
OSS_EDGE_SEAL OSS_EDGE_SEAL0 OSS_ESD_5V_ANA OSS_ESD_5V_ANA_BRK_L OSS_ESD_5V_ANA_BRK_R
OSS_ESD_5V_VDD OSS_ESD_5V_VSS OSS_FRAME OSS_FRAME_CNR OSS_FRAME_CNR0 OSS_FRAME_TEG
OSS_LOGO_TR OSS_MNE_CDNS OSS_MPE_CDNS OSS_NCH_ESD OSS_PAD OSS_PAD16 OSS_PCH_ESD
OSS_VIA_CDNS2 OSS_WLMN_CDNS OSS_WLMP_CDNS via_1 $$$CONTEXT_INFO$$$
```

**ところが設計リポジトリは、GIO 版の中身を `lef/TR-1um_frame_25x25.gds` という
非 GIO 版と同じ名前で置いている。**

```
設計の lef/TR-1um_frame_25x25.gds   = PDK の TR-1um_frame_25x25_GIO.gds を改名したもの
```

→ **ベース名で解決すると違うファイルを掴む。** GIO パッドを使う設計が
非 GIO 版を読めば `OSS_FRAME_GIO` が無くて落ちる（落ちればまだよく、
`OSS_FRAME` は両方にあるので気づかず進む経路もある）。

**対処（実装済み）**: `apr/config_base.pdk_frame_gds()` は
`TR-1um_frame_25x25_GIO.gds` を**明示的に**返す。設計側にコピーは置かない。

### 問題 B — TD4 / I2C_2026 のフレームが PDK のどのリビジョンとも違う

タイムスタンプを潰した正規化 md5:

| 出所 | md5 | 判定 |
|---|---|---|
| PDK `dev@64e40f5`（2026-08-26 `UPDATE: OSS_FRAME_GIO`） | `20f8f9f888c6` | 基準 |
| `TR-1um_Async_I2C/FRAME/` | `20f8f9f888c6` | PDK と一致 |
| `TR-1um_SCLK_SPI/lef/` | `20f8f9f888c6` | PDK と一致 |
| **`TR-1um_TD4/lef/`** | **`08fd3bd6b1a3`** | **不一致** |
| **`TR-1um_I2C_2026/lef/`** | **`08fd3bd6b1a3`** | TD4 から引き継ぎ |

---

## 2. 差分の実体 — セル `OSS_DRV` 1 個だけ

29 セルのうち **28 セルはセル単位ハッシュが完全一致**。違うのは
**`OSS_DRV`（出力ドライバ）だけ**。

セル内の一意な座標集合で数えると:

| レイヤ | 意味 | PDK | TD4 / I2C_2026 | 差 |
|---|---|---:|---:|---:|
| (3, 1) `AP` | P 活性 | 7 | **9** | +2 |
| (3, 2) `AN` | N 活性 | 12 | **14** | +2 |
| (11, 0) `CO` | コンタクト | 96 | **84** | **−12** |
| (13, 0) `M1` | メタル 1 | 25 | 25 | 同数だが 2 個が別座標 |
| (8, 1) `GC` | ゲートポリ | 14 | 14 | 同数だが 2 個が別座標 |
| (140,0) `WN` / (48,1) / (49,1) | ウェル・ピン | 2 / 3 / 3 | 同 | 一致 |

SREF（`cont_g` 3 / `diode_n` 2 / `via_1$1` 8）とラベル 8 個は同じ。

→ **保存し直しによる差ではない。ドライバのトランジスタ・レイアウトそのものが違う。**
活性領域が 2 つずつ増え、コンタクトが 12 個減っている。

## 3. 出所 — PDK 由来ではない

PDK の全ブランチ（`main` / `dev` / `dev_jun1okamura` / `development_jun` と
`origin/*`）で `TR-1um_frame_25x25_GIO.gds` を触った全リビジョンを展開し、
`OSS_DRV` のセル内容ハッシュを取ると **2 種類しか無い**:

| ハッシュ | リビジョン |
|---|---|
| `0ea0db9798` | `e2eaa91` / `7eeee5f`（2026-08-26 `ADD: GPIO style Digital IO …`） |
| `9f1e224b7c` | `146b1ed` / `64e40f5` / `a43feef` / `f6ab900`（2026-08-26 `UPDATE: OSS_FRAME_GIO`） |

**TD4 / I2C_2026 の `3fb5dc3f3f` はどちらでもない。**
さらに、I2C 版と 3 リビジョンすべての一致度が**まったく同じ**
（CO 層: 共通 44 / PDK のみ 52 / I2C のみ 40）＝ どの PDK 版からの派生でもない。

### 混入の経路

```
2026-09-07  SCLK_SPI  lef/ に PDK 版（20f8f9f888c6）を投入   ← 正
2026-09-11  TD4       5d89e5b "lef/simulation: 全セルの LVS ソースネットリストを配置"
                      ↑ このコミットで 08fd3bd6b1a3 が入っている（コミットメッセージは無関係）
2026-09-14  I2C_2026  00d02f0 "TD4 構成へ作り替え: scripts / lef を TD4 の最新版から"
                      ↑ TD4 からそのままコピー
```

**TD4 に投入された時点で既に別物。** 出所の候補（未確認 — このセッションは
アクセス権が無い）:

- `~/HogeHoge/OpenPDK/TR-1um_MPW_template`
- `~/HogeHoge/OpenPDK/OpenSUSI_MPW_TR2026` / `_TEST`
- `~/HogeHoge/OpenPDK/First_Tapeout_2026`
- 手元での修正（PDK に上げていない fix）

## 3-b. ★ 決定（2026-09-15・設計者判断）

**TD4 / I2C_2026 の `OSS_DRV`（`3fb5dc3f3f`）が正しい。**
上流に上げそびれていた修正版で、両設計はこれで DRC / LVS / ngspice を通している。

| | |
|---|---|
| 対応 | `OpenSUSI/TR-1um` に PR（`libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds`） |
| ブランチ | `fix/oss-drv-gio-frame`（ベース `dev` @ `6afbd91`、コミット `4932b5e`） |
| PR 本文 | [`../pdk/PR-TR-1um-OSS_DRV.md`](../pdk/PR-TR-1um-OSS_DRV.md) |
| push | **設計機から**（この環境に SSH 鍵が無い） |
| マージまで | **Local を使う** — `pdk/pending-upstream/TR-1um_frame_25x25_GIO.gds` |

> **PR の対象は `TR-1um_frame_25x25_GIO.gds`。**
> `TR-1um_frame_25x25.gds`（非 GIO・23 セル）は別のフレームで、`OSS_FRAME_GIO` を持たない。
> 設計側のファイル名が非 GIO 版と同じだったための取り違えに注意（§1 問題 A）。

`apr/config_base.pdk_frame_gds()` の解決順:

```
1. APR_FRAME_GDS                            明示指定
2. pdk/pending-upstream/…_GIO.gds           ← いまここ
3. $TR1UM_PDK/…/TR-1um_frame_25x25_GIO.gds  マージ後はここ
```

**マージされたら `pdk/pending-upstream/` のファイルを消すだけ**で 3 に戻る。

## 4. DRC / LVS による裏取り（任意）

方針は決まったが、**PR のレビュー材料として**両方に DRC を当てておく価値はある
（コンタクトが 12 個違うので、上流版が何のルールに引っかかるかを示せる）。

**このセッションでは回せない**: DRC デッキは KLayout の Ruby DSL なので
`klayout` の**コマンドライン実行ファイル**が要る。pip の `klayout` パッケージは
Python API だけで CLI を持たない。**設計機（KLayout 0.28.16）か CI で回すこと。**

```sh
# 設計機で。フレーム単体に当てる
python3 <APRtools>/apr/drc_pdk.py \
        $TR1UM_PDK/libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds OSS_FRAME_GIO
python3 <APRtools>/apr/drc_pdk.py \
        <TR-1um_I2C_2026>/lef/TR-1um_frame_25x25.gds OSS_FRAME_GIO
```

コンタクトが 12 個少ないので、**どちらかが `CO` 関連のルール
（`CO.S1` 1.0 / `M1.CO` 0.8 / `CO.AP` `CO.AN` 0.8 / `V1.CO` 1.0）に引っかかる**可能性が高い。
逆に「PDK 版が違反していて手元で直した」という筋も同じくらいあり得る。
**数だけでは決まらない。**

## 5. 影響範囲

| 対象 | 影響 |
|---|---|
| **コアの P&R（step1〜10）** | **無し。** フレームを読まない。`docs/06_verify_migration.md` の md5 一致はこの件と独立 |
| チップ組み立て（`assemble_top.py` 以降） | **有り。** フレームの図形がそのままチップ GDS に入る |
| チップ DRC / LVS | **有り** |
| **TD4 の提出済み GDS** | **この `OSS_DRV` を含む** |
| **I2C_2026 の提出済み GDS** | **同上** |
| SCLK_SPI | 無し（PDK 版を使っている） |
| Async_I2C（v10） | 無し（PDK 版） |

## 6. 決定と残り

| | 決定 |
|---|---|
| どちらが正か | **TD4 / I2C_2026 版（`3fb5dc3f3f`）** |
| 上流 | `OpenSUSI/TR-1um` に PR（コミット済み・push 待ち） |
| マージまで | `pdk/pending-upstream/` を使う |
| APRtools の参照 | `pdk_frame_gds()` が `_GIO` 付きを明示参照（実装済み） |
| 設計リポジトリ | `lef/TR-1um_frame_25x25.gds` という**紛らわしいコピーは廃止**。APRtools 参照に一本化 |

### 残り

1. **設計機から push → PR を開く**
2. （任意）レビュー材料として両版に `drc_pdk.py` を当てる
3. マージ後: PDK を pull / `info.yaml` の `pdk.ref` を新タグに固定 /
   `pdk/pending-upstream/` を削除 / U19・U22 を解決済みに
4. **提出済みの TD4・I2C_2026 は作り直し不要**（もともとこのフレームで作られている）

## 8. 再現に使ったコード

```python
# セル単位の内容ハッシュ（BGNSTR/ENDSTR の中身だけを md5）
import struct, hashlib
def cells(path):
    d = open(path, 'rb').read(); i = 0; cur = None; buf = bytearray(); out = {}
    while i < len(d) - 4:
        ln, rt = struct.unpack('>HH', d[i:i+4]); body = d[i+4:i+ln]
        if ln < 4: break
        if rt == 0x0502: buf = bytearray()                    # BGNSTR
        elif rt == 0x0606: cur = body.rstrip(b'\x00').decode()  # STRNAME
        elif rt == 0x0700: out[cur] = hashlib.md5(bytes(buf)).hexdigest()[:10]
        elif cur is not None: buf += struct.pack('>HH', ln, rt) + body
        i += ln
    return out
```

レイヤ別の座標集合を取る版は `docs/06_verify_migration.md` §3 と同じ要領
（`XY` レコード 0x1003 を種別・レイヤごとに集合にする）。

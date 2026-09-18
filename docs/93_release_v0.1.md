# v0.1 — 4 世代ぶんの写しを 1 箇所にまとめた最初のリリース

TR-1um（OpenSUSI / IP62、1 µm CMOS・**M1/M2 の 2 層配線**）向けの自作 P&R ツール群、
標準セル・マクロの共通データ、設計知見の集約。**4 世代ぶんの写しを 1 箇所にまとめた最初のリリース。**

## 何ができるか

**3 設計（`TR-1um_I2C_2026` / `TR-1um_TD4` / `TR-1um_SCLK_SPI`）が、合成からチップの提出物まで
全段このリポジトリで回る。** 道具は引数も再現用の環境変数も取らない — 設計ごとの値は
すべて設計の `config.py` にある。

| | |
|---|---|
| 合成・STA | `syn/syn.sh`（9 段。段は `config.py` が決める）|
| 配置・配線 | `apr/place.py` → `apr/route.py`（step1〜11）|
| チップ | `apr/assemble_top.py` → `apr/route_chip.py` → `apr/export_mpw.py` |
| 検証 | PDK 公式 DRC / LVS、ngspice、IRSIM、OpenSTA |
| セル特性化 | `char/`（36 セルの Liberty を GDS から作る）|

移行時に**提出済みの GDS と幾何一致まで**突き合わせてある（I2C / TD4）。
SCLK_SPI は行高が違うため合成からの作り直しで、DRC 0 / LVS 一致 / ngspice 12 項目 PASS。

## このリリースに入っている主なもの

- **セルライブラリを GDS から作り直した** — 特性化が「並列 MOS をまとめたネットリスト」で
  回っていたのを直し、36 セル全部を測り直した。`AS`/`AD` が逆の端子に付いていた別の不具合も同時に。
  標準セルの遅延は中央値 −6 〜 +12 %、マクロとパッドは約 +10 % 動いた（どれも**遅くなる向き**）
- **写した数字をやめた** — `set_load` と `min_pulse_width` は `.lib` から引く。
  `BUFTH` のしきい値は `char/schmitt.json` から読む。パッド面積は GDS を測る
- **検査を道具にした** — `lint.py` / `check_ledger.py` / `check_copies.py` /
  `check_no_home_paths.py` / `verify_lib.py` / `regress_limits.py`。
  どれも「0 件」を**数えて**言う
- **台帳 99 項目のうち 96 件が決着**。経緯は `docs/92_closed.md`、
  繰り返し出た教訓は `docs/90_improvement_notes.md` §8

## 既知の積み残し

| | 内容 |
|---|---|
| U6 | `info.yaml` の `pdk.ref` が `dev`。**上流でタグが切られたら**固定タグに戻す |
| U22 | PDK に同名で中身の違うフレームが 2 つある。APRtools 側は `_GIO` 明示参照で回避済み。**上流へ改名を提案中** |
| U94 | 設計側に同名の写しが 62 本残る。**危ない「古いだけ」は 0 本**で、`apr/check_copies.py` が毎回数える |

## 使い方

`README.md` の「使い方」。要点は 3 行:

```sh
export APRTOOLS=<置いた場所>/TR-1um_APRtools
export PYTHONPATH=$APRTOOLS/apr
cd <設計>; python3 $APRTOOLS/apr/selfcheck.py
```

#!/usr/bin/env python3
"""mk_drc_probe.py -- DRC チェッカの「空振り」を見つけるための違反セルを合成する。

**検査が通ったことは、検査が動いた証拠にならない。** この道具は、規則ごとに
わざと 1 つだけ違反するセルを作る。`drc_check_cells.py` と `drc_pdk.py`（PDK の
本物のデッキ）の**両方に同じ GDS を通して、同じものを指すか**を見るために使う。

    python3 apr/mk_drc_probe.py -o /tmp/drc_probe.gds
    python3 apr/drc_check_cells.py --gds /tmp/drc_probe.gds
    python3 apr/drc_pdk.py /tmp/drc_probe.gds T_M1SW        # セルごとに

作るセル（`T_OK` 以外はどれも**狙った 1 規則だけ**違反する）:

    T_M1SW   幅 12 µm の M1 の隣 1.5 µm に M1。M1.S1(1.4) は通るが M1.SW(2.0) 違反
    T_M1W3   幅 50 µm の M1（最大幅 45 超）
    T_M2W3   幅 50 µm の M2
    T_V1W1   2.0 角の V1 カット（1.4 ちょうどでない）
    T_V1GA   V1 が GC に重なる
    T_ENC    V1 を M1 が 0.5 しか囲んでいない（要 1.0）
    T_OK     ★ 否定対照。幅 6 µm の M1 の隣 1.5 µm — **M1(W) ではないので合法**

  境界そのものを試す 3 つ（U18、2026-09-17 に追加）:

    T_SW_10   幅 **ちょうど 10.000** の M1 の隣 1.8 µm — **合法**（否定対照）
    T_SW_10p  幅 **10.001**（1 dbu だけ太い）の M1 の隣 1.8 µm — **M1.SW 違反**
    T_SW_TEE  幅ちょうど 10.000 の M1 が直交して刺さる T 字 — **合法**

★ 上の 3 つが U18 の答えそのもの。デッキの `M1W = M1.sized(-5.0)…sized(5.0)` は
  **幅 10.000 を落とす**（-5.0 で幅 0 になり、面積 0 の図形は消える）ので、
  **「10.0 以上が M1(W)」ではなく「10.0 を超えると M1(W)」**。電源バー
  （`CHIP_BUS_W` / `POWER_BAR_W` / `RO_VSS_BAR_W` の 10.0）は
  **境界の 1 dbu 内側**にいる。

★ `T_OK` が肝。`M1.SW` は「同じ隙間でも、隣が太いときだけ違反」という規則
  なので、**違反セルだけ見ても実装が正しいことにはならない**。

★ **突き合わせは規則ごとに見る。件数の総和ではない。** ここのセルは狙った規則
  以外を満たしていないので、本物のデッキは**こちらが実装していない規則も**
  出す。実測（KLayout 0.30.9）: `T_V1GA` でデッキは 3 件 —
  `V1.GA:V1 overlap GA`（これが一致を見たいもの）に加えて
  `GA.CO:GA without CO`（ポリにコンタクトが無い）と
  `GC.ANT:GC must electrically connect to Substrate`。どちらも
  「探針セルが実デバイスとして不完全」なだけで、食い違いではない。

2026-09-15 の突き合わせ結果（`drc_check_cells.py` vs `drc_pdk.py`）:

    T_M1SW   M1.SW      1 / 1   場所も一致（ポリゴン 12.0-13.7、中心 12.85）
    T_M1W3   M1.W3      1 / 1
    T_M2W3   M2.W3      1 / 1
    T_V1W1   V1.W1      1 / 1   bbox_max
    T_V1GA   V1.GA      1 / 1   （デッキは別途 GA.CO / GC.ANT も出す。上記）
    T_ENC    V1.M1      4 / 4   ★ 辺の対で数える。領域の引き算だと 1 件だった
    T_OK     -          0 / 0   ★ 否定対照
"""
import argparse
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ
import rules  # noqa: E402  レイヤ番号の単一ソース


def build():
    ly = db.Layout()
    ly.dbu = rules.DBU

    def cell(name, *shapes):
        c = ly.create_cell(name)
        for lay, x0, y0, x1, y1 in shapes:
            c.shapes(ly.layer(*lay)).insert(db.DBox(x0, y0, x1, y1).to_itype(ly.dbu))
        return c

    wide = rules.M1_WIDE_MIN + 2.0            # 12.0 = 確実に M1(W)
    gap = (rules.M1_SPACE_MIN + rules.M1_WIDE_SPACE_MIN) / 2.0   # 1.7: S1 は通り SW は違反
    over = rules.METAL_WIDTH_MAX + 5.0        # 50.0
    cut = rules.V1_CUT
    cell("T_M1SW", (rules.M1, 0, 0, wide, 20), (rules.M1, wide + gap, 0, wide + gap + 3, 20))
    cell("T_M1W3", (rules.M1, 0, 0, over, 60))
    cell("T_M2W3", (rules.M2, 0, 0, over, 60))
    cell("T_V1W1", (rules.V1, 5, 5, 5 + cut + 0.6, 5 + cut + 0.6),
         (rules.M1, 3, 3, 9, 9), (rules.M2, 3, 3, 9, 9))
    cell("T_V1GA", (rules.V1, 5, 5, 5 + cut, 5 + cut), (rules.GC, 5.5, 5.5, 9, 9),
         (rules.M1, 3, 3, 9, 9), (rules.M2, 3, 3, 9, 9))
    cell("T_ENC", (rules.V1, 5, 5, 5 + cut, 5 + cut), (rules.M1, 4.5, 4.5, 6.9, 6.9),
         (rules.M2, 4, 4, 7.4, 7.4))
    # ★ 否定対照: 同じ隙間でも、隣が M1(W) でなければ合法
    cell("T_OK", (rules.M1, 0, 0, rules.M1_WIDE_MIN - 4.0, 20),
         (rules.M1, rules.M1_WIDE_MIN - 4.0 + gap, 0, rules.M1_WIDE_MIN + gap, 20))

    # ---- U18: 判定境界そのもの ------------------------------------------
    # 隙間 1.8 は M1.S1(1.4) を通り M1.SW(2.0) を破る。実設計（TD4 の電源バーと
    # その 1.8 µm 上を走る幅 3.4 の M1 トランク）と同じ隙間に合わせてある。
    edge = 1.8
    w0 = rules.M1_WIDE_MIN                  # 10.000 ちょうど
    w1 = rules.M1_WIDE_MIN + rules.DBU      # 10.001 = 1 dbu だけ太い
    cell("T_SW_10",  (rules.M1, 0, 0, w0, 40), (rules.M1, w0 + edge, 0, w0 + edge + 3.4, 40))
    cell("T_SW_10p", (rules.M1, 0, 0, w1, 40), (rules.M1, w1 + edge, 0, w1 + edge + 3.4, 40))
    # T 字: 同じ幅のバーが直交して刺さっても、角は 10x10 で -5.0 すると点になる
    cell("T_SW_TEE", (rules.M1, 0, 0, w0, 40), (rules.M1, -20, 15, 0, 15 + w0),
         (rules.M1, w0 + edge, 0, w0 + edge + 3.4, 40))
    return ly


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="/tmp/drc_probe.gds")
    a = ap.parse_args()
    build().write(a.out)
    print(f"書いた: {a.out}")
    print("  T_OK / T_SW_10 / T_SW_TEE 以外の 7 セルがそれぞれ 1 規則だけ違反する。"
          "\n  否定対照は T_OK / T_SW_10 / T_SW_TEE の 3 つ（何も出てはいけない）。")

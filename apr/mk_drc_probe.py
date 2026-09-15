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

★ `T_OK` が肝。`M1.SW` は「同じ 1.5 µm の隙間が、隣が太いときだけ違反」という
  規則なので、**違反セルだけ見ても実装が正しいことにはならない**。
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
    return ly


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default="/tmp/drc_probe.gds")
    a = ap.parse_args()
    build().write(a.out)
    print(f"書いた: {a.out}")
    print("  T_OK 以外の 6 セルがそれぞれ 1 規則だけ違反する。"
          "T_OK は否定対照（何も出てはいけない）。")

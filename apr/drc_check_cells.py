#!/usr/bin/env python3
"""drc_check_cells.py -- run the project's DRC rules on each standard cell.

The chip-level checker only sees whatever geometry the placement actually
instantiated, so a broken library cell stays invisible until something places
it -- which is exactly how BUF_X2's internal M1 spacing violation survived: a
stale `FOREIGN BUF_X1` in the LEF meant the layout carried BUF_X1's geometry
while the netlist said BUF_X2.

**値もレイヤも `rules.py` から取る**（M1/M2 の幅と間隔、V1 の間隔と囲み）。
STDCELL の GDS を触ったら必ず回す。

★ `rules.py` に**あるのにここが実装していない**規則がある: `M1.SW`（幅 10 µm
  以上の M1 に接する M1 は間隔 2.0）/ `M1.W3`・`M2.W3`（最大幅 45）/ `V1.W1`
  （カット寸法）/ `V1.GA`。サインオフは `drc_pdk.py` で行うこと。

  usage:  apr/drc_check_cells.py [--gds lef/TR-1um_STDCELL.gds] [CELL ...]
"""
import argparse
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401  設計ルートを sys.path へ
import config as cfg  # noqa: E402
import rules  # noqa: E402  プロセス定数の単一ソース

M1, M2, V1 = rules.M1, rules.M2, rules.V1
# ★ 以前ここだけ値が違っていた（U4）。M1 幅 1.4 / M2 幅 1.8 / V1 間隔 1.4 と
#   書いてあり、**3 つとも正しい値より緩かった**。しかも
#   「Rules match drc_check.py」と docstring に書いてあるのに一致していない。
#   緩い値の出どころは**隣の値**だった — M1 幅に M1 の*間隔* 1.4、M2 幅に
#   M1 の*幅* 1.8、V1 間隔に V1 の*カット寸法* 1.4。表を 1 列ずらして写した形。
#   正しい値に直して 3 つの GDS（v59_4 の PNR / STDCELL、v64_8 の STDCELL）で
#   回し直し、**結果は全部 DRC クリーンのまま**だった（潜在バグで、実害は無かった）。
M1_W, M1_S = rules.M1_WIDTH_MIN, rules.M1_SPACE_MIN
M2_W, M2_S = rules.M2_WIDTH_MIN, rules.M2_SPACE_MIN
V1_S, V1_ENC = rules.V1_SPACE_MIN, rules.V1_ENC_M1


def check_cell(ly, cell, dbu):
    def reg(lay):
        return db.Region(cell.begin_shapes_rec(ly.layer(*lay))).merged()

    m1, m2, v1 = reg(M1), reg(M2), reg(V1)
    out = []

    def add(name, edges, limit):
        for e in edges:
            a, b = e.first, e.second
            cx = (a.p1.x + a.p2.x + b.p1.x + b.p2.x) / 4 * dbu
            cy = (a.p1.y + a.p2.y + b.p1.y + b.p2.y) / 4 * dbu
            out.append((name, e.distance() * dbu, limit, cx, cy))

    add("M1 width", m1.width_check(int(round(M1_W / dbu))), M1_W)
    add("M1 space", m1.space_check(int(round(M1_S / dbu))), M1_S)
    add("M2 width", m2.width_check(int(round(M2_W / dbu))), M2_W)
    add("M2 space", m2.space_check(int(round(M2_S / dbu))), M2_S)
    add("V1 space", v1.space_check(int(round(V1_S / dbu))), V1_S)
    for tag, metal in (("V1 in M1", m1), ("V1 in M2", m2)):
        not_enc = v1 - metal.sized(-int(round(V1_ENC / dbu)))
        for p in not_enc.each():
            b = p.bbox()
            out.append((tag + " enclosure", 0.0, V1_ENC,
                        (b.left + b.right) / 2 * dbu, (b.bottom + b.top) / 2 * dbu))
    return out


def main(gds=cfg.CELL_GDS, only=()):
    ly = db.Layout()
    ly.read(gds)
    dbu = ly.dbu
    names = sorted(c.name for c in ly.each_cell()
                   if not only or c.name in only)
    bad = 0
    print(f"=== {cfg.disp(gds)} : {len(names)} cell(s) ===")
    for n in names:
        v = check_cell(ly, ly.cell(n), dbu)
        if not v:
            continue
        bad += 1
        print(f"\n  {n}: {len(v)} violation(s)")
        for rule, d, lim, x, y in v:
            print(f"      {rule:20} {d:.3f} um < {lim:.3f} um  at "
                  f"(x={x:.2f}, y={y:.2f}) cell-local")
    print()
    if bad:
        print(f"*** {bad} CELL(S) WITH DRC VIOLATIONS ***")
        return 1
    print(f"ALL {len(names)} CELLS DRC CLEAN")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cells", nargs="*")
    ap.add_argument("--gds", default=cfg.CELL_GDS)
    a = ap.parse_args()
    sys.exit(main(a.gds, set(a.cells)))

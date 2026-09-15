#!/usr/bin/env python3
"""gate_count.py -- cell / transistor / area / equivalent-gate report.

Reads a gate-level netlist plus stdcell/<世代>/cell_char.json (areas measured from
lef/TR-1um_STDCELL.gds, transistor counts from the cells' extracted SPICE)
and prints the size of the design in the units this project quotes:

    1 equivalent gate = NAND2 = 4 transistors = 1981 um2

Also estimates the placed core area from a logic-cell density figure; the
default 0.278 is the measured density of the TR-1um_Async_I2C chip
(0.2985 mm2 of logic cells inside a 1.533 mm2 core, LEF footprints), i.e. what this
project's own nrow placement + channel routing actually achieves.

  usage:  apr/gate_count.py NETLIST.v [NETLIST2.v ...] [--density 0.278]
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ
import config as cfg  # noqa: E402
import netlist_util as nu  # noqa: E402

# ★ 読むのは **cell_char.json**（`transistors` が入っているのはこちら）。
#   以前は `<APRtools>/lef/cell_info.json` を見ていた — 移行前の置き場で、
#   **そこにファイルは無い**ので実行すると必ず FileNotFoundError になっていた。
#   `syn_report.py` の `cell_area.json` と同じ壊れ方（U37 / 決定 21）。
DEFAULT_INFO = cfg.stdcell_file("cell_char.json")
NAND2_TR = 4        # NAND2 = 16.2 x 64.8 = 1049.8 um2 = 1 equivalent gate


def report(path, info, density, extra=None):
    counts = Counter(i.cell for i in nu.parse(open(path).read()))
    if extra:
        counts.update(extra)
    rows, tot_tr, tot_area, seq = [], 0, 0, 0
    unknown = []
    for cell, n in counts.most_common():
        c = info.get(cell)
        if c is None:
            unknown.append(cell)
            continue
        tr, ar = (c["transistors"] or 0) * n, c["area_um2"] * n
        tot_tr += tr
        tot_area += ar
        if c["kind"] in ("ff", "muxff", "latch"):
            seq += n
        rows.append((cell, n, tr, ar))

    print(f"\n=== {cfg.disp(path)} ===")
    print(f"{'cell':12} {'count':>6} {'Tr':>7} {'area(um2)':>11}")
    print("-" * 39)
    for cell, n, tr, ar in rows:
        print(f"{cell:12} {n:6d} {tr:7d} {ar:11.0f}")
    print("-" * 39)
    print(f"{'TOTAL':12} {sum(n for _, n, _, _ in rows):6d} {tot_tr:7d} {tot_area:11.0f}")
    if unknown:
        print(f"  !! not in cell_info.json: {', '.join(sorted(set(unknown)))}")
    print(f"\n  sequential cells      : {seq}")
    print(f"  equivalent gates      : {tot_tr / NAND2_TR:.0f}"
          f"   (NAND2 = {NAND2_TR} Tr = 1 gate)")
    print(f"  logic cell area       : {tot_area / 1e6:.4f} mm2")
    print(f"  placed core estimate  : {tot_area / density / 1e6:.3f} mm2"
          f"   (at {density * 100:.1f}% logic density)")
    return dict(cells=sum(n for _, n, _, _ in rows), tr=tot_tr,
                area=tot_area, seq=seq)


def main(paths, info_path=DEFAULT_INFO, density=0.195, extra=None):
    info = json.load(open(info_path))
    return [report(p, info, density, extra) for p in paths]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("netlists", nargs="+")
    ap.add_argument("--cell-info", default=DEFAULT_INFO)
    ap.add_argument("--density", type=float, default=0.195,
                    help="logic-cell area / placed core area (default: the "
                         "0.278 measured on TR-1um_Async_I2C)")
    ap.add_argument("--add", action="append", default=[], metavar="CELL=N",
                    help="add N instances of CELL to the tally (e.g. the "
                         "top-level BUFTH cells, or planned row buffers)")
    a = ap.parse_args()
    extra = Counter()
    for s in a.add:
        c, _, n = s.partition("=")
        extra[c] += int(n or 1)
    main(a.netlists, a.cell_info, a.density, extra or None)

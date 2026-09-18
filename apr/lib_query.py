#!/usr/bin/env python3
"""Liberty から値を読む。**写さずに引くための道具**（U99）。

  usage: python3 $APRTOOLS/apr/lib_query.py cap <lib> <セル> <ピン>
         python3 $APRTOOLS/apr/lib_query.py cap <lib> OSS_ESD_5V_DIO OUT   -> 45.923
         python3 $APRTOOLS/apr/lib_query.py mpw <lib> REG8x16 WEB          -> 10

  `cap` はピンの `capacitance`、`mpw` は `timing_type : min_pulse_width` の
  拘束値（既定は `fall_constraint` = 低の幅。`--rise` で高の幅）。

なぜ要るか:
  合成（ABC）と STA が出力ポートに掛ける負荷 `set_load` は、**パッドセル
  `OSS_ESD_5V_DIO` の `OUT` ピンの入力容量**という意味の数字。ところが
  `syn/abc.constr` と `syn/sta/setup.tcl` に **`36.2` と直書き**してあった。
  同じことが `syn/sta/report_macro.tcl` の `min_pulse_width` でも起きていた
  （`11 ns` と直書き。U96 で実測は 10.0 ns になった）ので、そちらもここから引く。
  U96 で `.lib` を作り直したら実測は **45.923 fF** になり、**写した側だけが
  古いまま**になった（U65 と同じ「正本が 1 箇所に無い」）。
  → **`.lib` から引く。** 写さない。

  `.lib` は `mklib.py` が `char/char/*.json` から生成する。つまり
  特性化 → `.lib` → 合成 / STA が 1 本に繋がる。

読み方:
  Liberty の入れ子を数えるだけの素朴な走査。`cell (X) {` の中の
  `pin (Y) {` の中の `capacitance : <数> ;` を返す。**バスピン
  （`bus (Q) { pin (Q[0]) ...`）の中も見る**ので、`Q[0]` のような名前でも引ける。
"""
from __future__ import annotations

import argparse
import re
import sys

RE_CELL = re.compile(r'^\s*cell\s*\(\s*"?([^")]+)"?\s*\)\s*\{')
RE_PIN = re.compile(r'^\s*(?:pin|bus)\s*\(\s*"?([^")]+)"?\s*\)\s*\{')
RE_CAP = re.compile(r'^\s*capacitance\s*:\s*([-\d.eE+]+)\s*;')


def pin_cap(path, cell, pin):
    """`<cell>` の `<pin>` の `capacitance` を返す。見つからなければ None。"""
    depth = 0
    cur_cell = cur_pin = None
    cell_depth = pin_depth = None
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = RE_CELL.match(ln)
        if m:
            cur_cell, cell_depth = m.group(1), depth
        else:
            m = RE_PIN.match(ln)
            if m and cur_cell == cell:
                cur_pin, pin_depth = m.group(1), depth
            elif cur_cell == cell and cur_pin == pin:
                m = RE_CAP.match(ln)
                if m:
                    return float(m.group(1))
        depth += ln.count("{") - ln.count("}")
        if cell_depth is not None and depth <= cell_depth:
            cur_cell = cur_pin = None
            cell_depth = pin_depth = None
        elif pin_depth is not None and depth <= pin_depth:
            cur_pin = pin_depth = None
    return None


RE_TTYPE = re.compile(r'^\s*timing_type\s*:\s*"?([A-Za-z_]+)"?\s*;')
RE_RELPIN = re.compile(r'^\s*related_pin\s*:\s*"?([^";]+)"?\s*;')
RE_CONSTR = re.compile(r'^\s*(rise|fall)_constraint\s*\(')
RE_VALUES = re.compile(r'^\s*values\s*\(\s*"?([-\d.eE+]+)')


def min_pulse_width(path, cell, related, edge="fall"):
    """`<cell>` の `min_pulse_width`（`related_pin` が `<related>`）の拘束値。

    Liberty では `pin (X) { timing () { related_pin : "WEB";
    timing_type : min_pulse_width; fall_constraint (scalar) { values("10.0") } } }`
    の形。**どのピンに書いてあるかは設計次第**なので `related_pin` で探す。
    """
    in_cell = False
    depth = 0
    cell_depth = None
    ttype = relpin = None
    want = None
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = RE_CELL.match(ln)
        if m:
            in_cell, cell_depth = (m.group(1) == cell), depth
        elif in_cell:
            m = RE_TTYPE.match(ln)
            if m:
                ttype = m.group(1)
            else:
                m = RE_RELPIN.match(ln)
                if m:
                    relpin = m.group(1)
                else:
                    m = RE_CONSTR.match(ln)
                    if m:
                        want = (m.group(1) == edge and ttype == "min_pulse_width"
                                and relpin == related)
                    elif want:
                        m = RE_VALUES.match(ln)
                        if m:
                            return float(m.group(1))
        depth += ln.count("{") - ln.count("}")
        if cell_depth is not None and depth <= cell_depth:
            in_cell = False
            cell_depth = None
            ttype = relpin = want = None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["cap", "mpw"],
                    help="cap=ピンの入力容量 / mpw=min_pulse_width の拘束値")
    ap.add_argument("lib")
    ap.add_argument("cell")
    ap.add_argument("pin", help="cap ならそのピン、mpw なら related_pin")
    ap.add_argument("--rise", action="store_true",
                    help="mpw: 高の幅（既定は低の幅 = fall_constraint）")
    ap.add_argument("-f", "--format", default="{:.6g}",
                    help="出し方（既定 {:.6g}）")
    a = ap.parse_args()
    if a.what == "cap":
        v, what = pin_cap(a.lib, a.cell, a.pin), "capacitance"
    else:
        v = min_pulse_width(a.lib, a.cell, a.pin, "rise" if a.rise else "fall")
        what = f"min_pulse_width（related_pin {a.pin}）"
    if v is None:
        sys.exit(f"** {a.lib} に {a.cell} の {a.pin} の {what} が無い")
    print(a.format.format(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

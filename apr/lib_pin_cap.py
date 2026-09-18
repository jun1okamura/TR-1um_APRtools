#!/usr/bin/env python3
"""Liberty からピンの入力容量を読む。**写さずに引くための道具**（U99）。

  usage: python3 $APRTOOLS/apr/lib_pin_cap.py <lib> <セル> <ピン>
         python3 $APRTOOLS/apr/lib_pin_cap.py <lib> OSS_ESD_5V_DIO OUT

なぜ要るか:
  合成（ABC）と STA が出力ポートに掛ける負荷 `set_load` は、**パッドセル
  `OSS_ESD_5V_DIO` の `OUT` ピンの入力容量**という意味の数字。ところが
  `syn/abc.constr` と `syn/sta/setup.tcl` に **`36.2` と直書き**してあった。
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lib")
    ap.add_argument("cell")
    ap.add_argument("pin")
    ap.add_argument("-f", "--format", default="{:.6g}",
                    help="出し方（既定 {:.6g}）")
    a = ap.parse_args()
    v = pin_cap(a.lib, a.cell, a.pin)
    if v is None:
        sys.exit(f"** {a.lib} に {a.cell} の {a.pin} の capacitance が無い")
    print(a.format.format(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

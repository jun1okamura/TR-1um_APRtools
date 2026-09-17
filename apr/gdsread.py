# -*- coding: utf-8 -*-
"""GDSII を**素の Python で**読む（依存なし）。

  usage: python3 apr/gdsread.py <古い.gds> <新しい.gds>     セルごとの差分

★ **`gdstk` も `klayout` も要らない。** セルごとに「層 -> 図形数」「ラベル」
  「参照」「bbox」を数えるだけなので、幾何の照合には足りる。
  正確な面積や DRC が要るときは `drc_check_cells.py` / `drc_pdk.py`（KLayout）へ。

なぜ要るか: **セルの GDS を直したのに、そこから作る `TR-1um_PNR.gds` が
古いまま**だと、フローは古いセルで回って**落ちずに古いチップが出る**
（`config.CELL_GDS` が読むのは `PNR.gds` の方）。`selfcheck.py` が
正本の 2 つを突き合わせて気づけるように、読み手をここに置いた。
"""
import struct, sys, collections

BGNSTR, STRNAME, ENDSTR = 0x05, 0x06, 0x07
BOUNDARY, PATH, SREF, AREF, TEXT, NODE, BOX = 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x15, 0x2d
ENDEL, XY, LAYER, DATATYPE, TEXTTYPE, STRING, SNAME, WIDTH = 0x11, 0x10, 0x0d, 0x0e, 0x16, 0x19, 0x12, 0x0f

def read(path):
    d = open(path, "rb").read()
    i = 0
    cells, cur, name, el = {}, None, None, None
    while i + 4 <= len(d):
        ln, rt = struct.unpack(">HH", d[i:i+4])
        if ln < 4: break
        rec, body = rt >> 8, d[i+4:i+ln]
        if rec == BGNSTR:
            cur = {"shapes": collections.Counter(), "labels": collections.Counter(),
                   "refs": collections.Counter(), "pts": []}
        elif rec == STRNAME:
            name = body.rstrip(b"\0").decode("ascii", "replace"); cells[name] = cur
        elif rec == ENDSTR:
            cur = name = None
        elif rec in (BOUNDARY, PATH, SREF, AREF, TEXT, NODE, BOX):
            el = {BOUNDARY:"boundary", PATH:"path", SREF:"sref", AREF:"aref",
                  TEXT:"text", NODE:"node", BOX:"box"}[rec]
            L = {"kind": el, "layer": None, "dt": None, "xy": [], "s": None, "ref": None}
        elif rec == LAYER and el: L["layer"] = struct.unpack(">h", body[:2])[0]
        elif rec in (DATATYPE, TEXTTYPE) and el: L["dt"] = struct.unpack(">h", body[:2])[0]
        elif rec == STRING and el: L["s"] = body.rstrip(b"\0").decode("ascii", "replace")
        elif rec == SNAME and el: L["ref"] = body.rstrip(b"\0").decode("ascii", "replace")
        elif rec == XY and el:
            L["xy"] = [struct.unpack(">ii", body[k*8:k*8+8]) for k in range(len(body)//8)]
        elif rec == ENDEL and el and cur is not None:
            if L["kind"] in ("sref", "aref"):
                cur["refs"][L["ref"]] += 1
            elif L["kind"] == "text":
                cur["labels"][(L["layer"], L["dt"], L["s"])] += 1
            else:
                cur["shapes"][(L["kind"], L["layer"], L["dt"])] += 1
            if L["kind"] != "text":
                cur["pts"].extend(L["xy"])
            el = None
        i += ln
    for c in cells.values():
        if c is None: continue
        if c["pts"]:
            xs=[p[0] for p in c["pts"]]; ys=[p[1] for p in c["pts"]]
            c["bbox"]=(min(xs),min(ys),max(xs),max(ys))
        else: c["bbox"]=None
    return cells

def top_cells(path):
    """**そのファイル自身の**トップセル（どこからも参照されていないセル）。

    KLayout の内部セル（`$$$…`）は除く。0 個や 2 個以上のこともある
    （中間の GDS には未参照のセルが山ほど残っている）ので、**呼び手は
    「ちょうど 1 個のときだけ信じる」**こと。
    """
    cells = read(path)
    ref = set()
    for c in cells.values():
        ref |= set(c["refs"])
    return sorted(n for n in cells if n not in ref and not n.startswith("$$$"))


if __name__ == "__main__":
    a, b = read(sys.argv[1]), read(sys.argv[2])
    only = sorted(set(a) ^ set(b))
    print(f"セル数 {len(a)} -> {len(b)}" + (f" / 片側だけ {only}" if only else ""))
    for n in sorted(set(a) & set(b)):
        ca, cb = a[n], b[n]
        if (ca["shapes"], ca["labels"], ca["refs"], ca["bbox"]) == \
           (cb["shapes"], cb["labels"], cb["refs"], cb["bbox"]): continue
        print(f"\n=== {n}   bbox {ca['bbox']} -> {cb['bbox']}"
              + ("  ★ **bbox が変わった**" if ca['bbox'] != cb['bbox'] else ""))
        for k in sorted(set(ca["shapes"]) | set(cb["shapes"]), key=str):
            if ca["shapes"][k] != cb["shapes"][k]:
                print(f"    図形 {k[0]:<8} 層 {k[1]}/{k[2]}: {ca['shapes'][k]} -> {cb['shapes'][k]}")
        for k in sorted(set(ca["labels"]) | set(cb["labels"]), key=str):
            if ca["labels"][k] != cb["labels"][k]:
                print(f"    ラベル 層 {k[0]}/{k[1]} \"{k[2]}\": {ca['labels'][k]} -> {cb['labels'][k]}")
        if ca["refs"] != cb["refs"]:
            print(f"    参照 {dict(ca['refs'])} -> {dict(cb['refs'])}")

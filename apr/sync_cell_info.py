#!/usr/bin/env python3
"""sync_cell_info.py -- re-measure the standard cells and update cell_info.json.

Run this after ANY change to lef/TR-1um_STDCELL.gds (a new cell, a resized
cell, a fixed abutment).  It re-measures every cell's bounding box from the
GDS, refreshes transistor counts from the cells' extracted SPICE when those
are reachable, and merges the result into stdcell/<世代>/cell_char.json -- which is what
apr/gen_liberty.py and apr/gate_count.py both read, so one run keeps
synthesis and the area report in step with the library.

Logic functions cannot be measured, so they come from the table below; a new
combinational cell that is not in it is reported and left without a function
(harmless for gate_count.py, but gen_liberty.py will not offer it to ABC
until a function is added here).

  usage:
    apr/sync_cell_info.py
    apr/sync_cell_info.py --gds lef/TR-1um_STDCELL.gds \
        --extracted-dir ../TR-1um_Async_I2C/LEF
    apr/sync_cell_info.py --set BUF_X2:transistors=6      # manual override
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ
import config as cfg  # noqa: E402

# ★ 出力は **cell_char.json**。`cell_info.json` とは別物で、同じ名前を
#   使っていたのが混乱のもとだった（2026-09-15）:
#     layout/cell_info.json          `mkcellinfo.py` が作る**幾何だけ**（設計ごと）
#     stdcell/<世代>/cell_char.json  こちらが作る**特性化の台帳**
#       （area_um2 / transistors / kind / in_pins / out_pin / function）
#   `gen_liberty.py` が要るのは後者。前者を渡すと KeyError: 'kind' になる。
GDS = cfg.stdcell_file("TR-1um_STDCELL.gds")
LEF = cfg.stdcell_file("TR-1um_STDCELL.lef")
INFO = cfg.stdcell_file("cell_char.json")
EXTRACTED = cfg.stdcell_file("extracted")

# (output pin, liberty function, input pins) -- extend when a cell is added
FUNCS = {
    "INV_X1": ("Y", "A'", ["A"]),
    "BUF_X1": ("Y", "A", ["A"]),
    "BUF_X2": ("Y", "A", ["A"]),
    "BUF_X4": ("Y", "A", ["A"]),
    "INV_X2": ("Y", "A'", ["A"]),
    "INV_X4": ("Y", "A'", ["A"]),
    "BUFTH":  ("Y", "A", ["A"]),
    "NAND2": ("Y", "!(A*B)", ["A", "B"]),
    "NAND3": ("Y", "!(A*B*C)", ["A", "B", "C"]),
    "NAND4": ("Y", "!(A*B*C*D)", ["A", "B", "C", "D"]),
    "NOR2": ("Y", "!(A+B)", ["A", "B"]),
    "NOR3": ("Y", "!(A+B+C)", ["A", "B", "C"]),
    "NOR4": ("Y", "!(A+B+C+D)", ["A", "B", "C", "D"]),
    "AND2_X1": ("Y", "A*B", ["A", "B"]),
    "AND3_X1": ("Y", "A*B*C", ["A", "B", "C"]),
    "AND4_X1": ("Y", "A*B*C*D", ["A", "B", "C", "D"]),
    "OR2": ("Y", "A+B", ["A", "B"]),
    "OR3": ("Y", "A+B+C", ["A", "B", "C"]),
    "OR4": ("Y", "A+B+C+D", ["A", "B", "C", "D"]),
    "XOR2": ("Y", "A^B", ["A", "B"]),
    "XNOR2": ("Y", "!(A^B)", ["A", "B"]),
    "MUX2": ("Y", "(A*!S)+(B*S)", ["A", "B", "S"]),
    "NAND2B": ("Y", "!(!A*B)", ["A", "B"]),
    "NOR2B": ("Y", "!(!A+B)", ["A", "B"]),
    "AOI21": ("Y", "!((A*B)+C)", ["A", "B", "C"]),
    "OAI21": ("Y", "!((A+B)*C)", ["A", "B", "C"]),
}
SEQ = {"DFFRB", "DFFS", "DFF"}
MUXFF = {"MUXDFFRB"}
LATCH = {"RSLATCH"}

# ★ **ABC に渡さないセル**と、その理由（U34）。
#   以前はこれらが「論理関数が無い」として毎回 17 件並び、
#   「FUNCS に足せば ABC が使える」と案内していた。**足してはいけない**
#   ものばかりで、案内の方が間違っていた。
NO_FUNC = {
    "REG4x16":  "レジスタファイル本体。手でインスタンスする",
    "REG8x16":  "同上",
    "MEMPORT":  "REG8x16 を R90 して帯にしたもの。手で置く",
    "DEC0":     "レジスタファイル内部のデコーダ",
    "DEC2":     "同上",
    "DEC16":    "同上",
    "REGBUF":   "レジスタファイル内部のバッファ",
    "REGBUF4":  "同上",
    "REGBUF8":  "同上",
    "TLAT":     "レジスタファイル内部の伝送ラッチ",
    "TLAT4":    "同上", "TLAT8": "同上", "TLAT64": "同上", "TLAT128": "同上",
    "TLAT4B":   "同上", "TLAT8B": "同上",
    "ADDBUF":   "行の電源を継ぐ構造セル。論理は持たない",
    "DEL1":     "**わざと遅らせる**セル。Y=A と書くと ABC が最適化で消す",
}


def measure_lef(lef_path):
    """MACRO SIZE from the LEF -- the authoritative placement footprint.

    NOTE: a cell's GDS bounding box is NOT its footprint.  Every TR-1um cell
    overhangs its prBoundary by exactly 12.6 um in x and 4.0 um in y (well /
    implant enclosure that abuts with the neighbouring cell), so measuring the
    GDS makes INV_X1 look like 1610 um2 when the LEF says 700 um2.  Always
    prefer the LEF; the GDS measurement below is only a fallback.
    """
    import re
    out, cur = {}, None
    for ln in open(lef_path):
        m = re.match(r"\s*MACRO\s+(\S+)", ln)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", ln)
        if m and cur:
            w, h = float(m.group(1)), float(m.group(2))
            out[cur] = dict(width_um=w, height_um=h, area_um2=round(w * h, 1))
    return out


def measure(gds_path, min_w=5.0, min_h=20.0):
    import gdstk
    out = {}
    for c in gdstk.read_gds(gds_path).cells:
        b = c.bounding_box()
        if not b:
            continue
        (x0, y0), (x1, y1) = b
        w, h = x1 - x0, y1 - y0
        if w < min_w or h < min_h:
            continue                       # vias and sub-shapes
        out[c.name] = dict(width_um=round(w, 2), height_um=round(h, 2),
                           area_um2=round(w * h))
    return out


def transistors(dirpath):
    out = {}
    if not dirpath or not os.path.isdir(dirpath):
        return out
    for f in glob.glob(os.path.join(dirpath, "*.extracted")):
        n = sum(1 for l in open(f)
                if l.strip().upper().startswith(("XM", "M"))
                and ("PMOS" in l.upper() or "NMOS" in l.upper()))
        out[os.path.splitext(os.path.basename(f))[0]] = n
    return out


def transistors_from_gds(gds_path, names):
    """**GDS から数える。台帳のトランジスタ数はここが唯一の出所**（U49）。

    ★ ここは 2 回間違えた。どちらも「数え方の定義」の問題で、GDS も
      `.extracted` も嘘は書いていなかった。

    (1) **`combine_devices()` を呼ばないと折り返しを二重に数える。**
        `BUFTH` は w=10.2u の PMOS を 10.2u × 2 フィンガーで描くので、
        生の抽出ではゲート図形が 10 枚に見える。`.extracted` を書く側
        （`klayout_extract.main`）は `combine_devices()` を通してから
        書いているので 8。**8 が正しい。**

    (2) **`each_circuit()` を足すと、階層セルは「1 回だけ」数えてしまう。**
        `REG4x16` は `TLAT` を 64 個並べているのに、`TLAT` という回路が
        1 つあるだけなので 12 しか数えない。**平坦化してから数える。**
        `REG4x16` は 66 ではなく **1076**、`DEC16` は 26 ではなく **256**。

    だから `.extracted` の値はもう使わない: 平坦なセルでは
    `combine_devices()` 後と 1 個も違わず、階層セルでは同じ理由で
    間違っている（`REG4x16.extracted` の 72 も「回路ごとに 1 回」）。

    `FILL*` / `TAP*` は素子が本当に 0（拡散とコンタクトだけ）なので、
    **0 と書く**。`None` のままだと「測れていない」と区別が付かない。
    """
    out = {}
    if not os.path.exists(gds_path):
        return out
    import klayout_extract
    for name in names:
        try:
            # ★ `l2n` を変数に持つこと。`build(...).netlist()` と書くと
            #   `l2n` がその場で解放され、netlist が
            #   「Object has been destroyed already」になる。
            l2n = klayout_extract.build(gds_path, name)
            nl = l2n.netlist()
            # `.extracted` を書く側と**同じ正規化**を通す（(1)）
            nl.make_top_level_pins()
            nl.combine_devices()
            nl.purge()
            nl.purge_nets()
            nl.flatten()                      # インスタンスを展開する（(2)）
            out[name] = sum(sum(1 for _ in c.each_device())
                            for c in nl.each_circuit())
            del l2n
        except Exception as e:
            print(f"  !! {name} を GDS から数えられない: {type(e).__name__} {e}")
    return out


def kind_of(name):
    if name in FUNCS:  return "comb"
    if name in SEQ:    return "ff"
    if name in MUXFF:  return "muxff"
    if name in LATCH:  return "latch"
    if name.startswith(("FILL", "TAP")): return "physical"
    return "other"


def main(gds_path=GDS, info_path=INFO, extracted_dir=EXTRACTED, overrides=None,
         lef_path=LEF):
    if lef_path and os.path.exists(lef_path):
        geo = measure_lef(lef_path)
        src = cfg.disp(lef_path) + " MACRO SIZE"
        if os.path.exists(gds_path):                 # cross-check
            gg = measure(gds_path)
            missing = sorted(set(gg) - set(geo))
            if missing:
                print(f"  !! in GDS but not in LEF (regenerate the LEF with "
                      f"gen_lef.py): {', '.join(missing)}")
                for n in missing:
                    geo[n] = dict(gg[n], area_um2=round(
                        (gg[n]['width_um'] - 12.6) * (gg[n]['height_um'] - 4.0), 1))
    else:
        geo = measure(gds_path)
        src = cfg.disp(gds_path) + " bounding boxes (NOT the footprint)"
    # ★ トランジスタ数は **GDS だけ**から数える（U49）。`.extracted` は
    #   平坦なセルでは一致し、階層セルでは同じ数え方の間違いをしている。
    tr = transistors_from_gds(gds_path, sorted(geo))
    # `.extracted` があるものは突き合わせて、**ずれたら黙らずに出す**。
    _ext = transistors(extracted_dir)
    _both = sorted(n for n in tr if n in _ext)
    _bad = [(n, _ext[n], tr[n]) for n in _both if _ext[n] != tr[n]]
    if _bad:
        print(f"  !! .extracted と GDS でトランジスタ数が違う {len(_bad)} セル"
              "（台帳は GDS を使う。U49）:")
        for n, a, b in _bad:
            print(f"       {n:<10} .extracted={a:<5} GDS(平坦化)={b}")
        print("     階層セルは .extracted も『回路ごとに 1 回』しか数えていない。")
    elif _both:
        print(f"  {len(_both)} セルで .extracted と GDS が一致")

    old = json.load(open(info_path)) if os.path.exists(info_path) else {}
    meta = {k: v for k, v in old.items() if k.startswith("_")}

    new, added, changed, no_func, no_tr = {}, [], [], [], []
    for name in sorted(geo):
        prev = old.get(name, {})
        e = dict(geo[name])
        e["transistors"] = tr.get(name, prev.get("transistors"))
        e["kind"] = kind_of(name)
        if name in FUNCS:
            e["out_pin"], e["function"], e["in_pins"] = FUNCS[name]
        new[name] = e
        if name not in old:
            added.append(name)
        elif any(prev.get(k) != e.get(k) for k in ("area_um2", "transistors")):
            changed.append(name)
        if e["kind"] == "other" and name not in NO_FUNC:
            no_func.append(name)
        if name in NO_FUNC:
            e["no_func_reason"] = NO_FUNC[name]
        if e["transistors"] is None:
            no_tr.append(name)

    removed = [n for n in old if not n.startswith("_") and n not in new]

    # LEF/GDS consistency: a MACRO's FOREIGN names the physical cell the
    # placement GDS builder instantiates.  A stale FOREIGN (e.g. a MACRO
    # added by copying another one) silently swaps the geometry -- the
    # netlist says BUF_X2, the layout gets BUF_X1, and only LVS notices.
    bad_foreign, no_geom = [], []
    if lef_path and os.path.exists(lef_path) and os.path.exists(gds_path):
        import re
        gds_cells = set(measure(gds_path))
        text = open(lef_path).read()
        for m in re.finditer(r"^MACRO (\S+)\n(.*?)\n\s*END\s+\1\s*$",
                             text, re.M | re.S):
            macro, body = m.group(1), m.group(2)
            fm = re.search(r"FOREIGN\s+(\S+)", body)
            foreign = fm.group(1) if fm else macro
            if macro not in gds_cells:
                no_geom.append((macro, foreign))
            elif foreign != macro:
                bad_foreign.append((macro, foreign))

    meta.setdefault("_source", {}).update({
        "areas": src,
        "transistors": "counted from the GDS (combine_devices + flatten)",
        "gate_equivalent_ref": "NAND2 = 4 transistors = 1981 um2 = 1 equivalent gate"})
    for spec in overrides or []:
        cell, _, kv = spec.partition(":")
        k, _, v = kv.partition("=")
        if cell in new:
            new[cell][k] = int(v) if v.lstrip("-").isdigit() else v
            print(f"  override {cell}.{k} = {new[cell][k]}")

    meta.update(new)
    json.dump(meta, open(info_path, "w"), indent=1)

    print(f"{info_path}: {len(new)} cells")
    if added:    print(f"  ADDED   : {', '.join(added)}")
    if changed:  print(f"  CHANGED : {', '.join(changed)}")
    if removed:  print(f"  REMOVED : {', '.join(removed)}")
    _skip = sorted(n for n in new if n in NO_FUNC)
    if _skip:
        print(f"  ABC に渡さないセル {len(_skip)} 個（理由は cell_char.json の "
              f"no_func_reason）: {', '.join(_skip)}")
    if no_func:  print(f"  !! no logic function (add to FUNCS in this script "
                       f"to let ABC use them): {', '.join(no_func)}")
    if no_tr:    print(f"  !! no transistor count (pass --extracted-dir, or "
                       f"--set CELL:transistors=N): {', '.join(no_tr)}")
    if bad_foreign:
        print("  !! LEF FOREIGN points at a DIFFERENT cell than the MACRO, "
              "so the placed geometry will not match the netlist:")
        for macro, foreign in bad_foreign:
            print(f"       MACRO {macro} -> FOREIGN {foreign}")
    if no_geom:
        print("  !! MACRO with no cell of that name in the GDS (any use "
              "silently becomes its FOREIGN target):")
        for macro, foreign in no_geom:
            print(f"       MACRO {macro} -> FOREIGN {foreign}")
    if added or changed:
        print("\n  next: apr/gen_liberty.py && scripts/build.sh && "
              "scripts/run_tests.sh")
    return new


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gds", default=GDS)
    ap.add_argument("--lef", default=LEF,
                    help="LEF whose MACRO SIZE is the authoritative footprint")
    ap.add_argument("--cell-info", default=INFO)
    ap.add_argument("--extracted-dir", default=EXTRACTED)
    ap.add_argument("--set", action="append", default=[], metavar="CELL:key=value")
    a = ap.parse_args()
    main(a.gds, a.cell_info, a.extracted_dir, a.set, a.lef)

#!/usr/bin/env python3
"""Yosys の `stat` 出力を TR-1um STDCELL の実測セル面積に換算する。

usage:
  yowasp-yosys -p "read_verilog *.v; hierarchy -check -top TOP; synth -top TOP -flatten; \
                   abc -g simple; opt_clean; tee -o stat.txt stat"
  python3 $APRTOOLS/apr/area_estimate.py stat.txt --top TOP

**面積は自前の表を持たない。** 正本 `stdcell/<版>/cell_area.json`
（`apr/cellinfo.py --areas` が GDS の (235,0) abutment box から書き出したもの）を読む。
ライブラリを直したら

  python3 $APRTOOLS/apr/cellinfo.py <APRtools>/stdcell/<版>/TR-1um_STDCELL.gds \
          --genlib <APRtools>/syn/tr1um.genlib \
          --areas <APRtools>/stdcell/<版>/cell_area.json

を流し直すだけで、この見積りも自動で追従する。
（行高 64.8→59.4 の変更でこのファイルの表だけが取り残され、
  組合せセルの面積を 8.3% 過大に見積もっていたのを直したときの反省。）

★ **面積表はスクリプトの隣ではない**（U37、2026-09-17）。`{HERE}/cell_area.json`
  を既定にしていたが、`apr/` にそんなファイルは無い（`syn_report.py` /
  `cmp_cells.py` と同じ壊れ方。U29 で `scripts/` から `apr/` へ移したときの
  取り残し）。`cfg.stdcell_file()` を通す。行高の直書き 59.4 も
  `cfg.ROW_HEIGHT_UM` へ。
"""
from __future__ import annotations
import argparse, collections, json, os, re, sys
import os as _os_r, sys as _sys_r  # noqa: E402
_sys_r.path.insert(0, _os_r.path.dirname(_os_r.path.abspath(__file__)))
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ
import rules  # noqa: E402  プロセス定数の単一ソース

# ★ 入力は全部引数でもらえるので、設計の config.py が無くても動く（U57）。
cfg = apr_path.soft_config()  # noqa: E402

# OSS_FRAME_GIO のコア。パッドの内側は 1840 x 1840 だが、四隅の OSS_FRAME_CNR が
# 120 x 120 um ずつ食うので実際に置けるのは 3.33 mm2（内接する最大の正方形は
# 1600 x 1600 = 2.56 mm2）。数字の出どころは $APRTOOLS/apr/mkleffrm.py が実形状から出したもの。
CORE_W = CORE_H = rules.FRAME_OPENING_UM
CORE_AREA = CORE_W * CORE_H - 4 * 120.0 * 120.0      # = 3,328,000 um2
HERE = os.path.dirname(os.path.abspath(__file__))

# Yosys の内部セル名 -> 実セル名（複数なら合計面積）
MAP = {
    "$_NOT_":    ["INV_X1"],
    "$_BUF_":    ["BUF_X1"],
    "$_NAND_":   ["NAND2"],
    "$_NOR_":    ["NOR2"],
    "$_AND_":    ["AND2_X1"],
    "$_OR_":     ["OR2"],
    "$_XOR_":    ["XOR2"],
    "$_XNOR_":   ["XNOR2"],
    "$_MUX_":    ["MUX2"],
    "$_ANDNOT_": ["INV_X1", "AND2_X1"],
    "$_ORNOT_":  ["INV_X1", "OR2"],
    "$_AOI3_":   ["AND2_X1", "NAND2"],
    "$_OAI3_":   ["OR2", "NAND2"],
    "$_AOI4_":   ["AND2_X1", "NAND2"],
    "$_OAI4_":   ["OR2", "NAND2"],
}
FALLBACK = "AND2_X1"        # 表に無い組合せセルはこれで代用
FF_PLAIN = "DFFRB"          # リセット付き FF
FF_EN = "MUXDFFRB"          # イネーブル付き FF（単一セルで存在する）


def load_areas(path):
    if not os.path.exists(path):
        sys.exit(f"{cfg.show(path)} が無い。正本は stdcell/<版>/cell_area.json。\n"
                 f"  作り直すなら apr/cellinfo.py --areas（docstring の usage）。")
    doc = json.load(open(path))
    return ({k: v["area"] for k, v in doc["cells"].items()},
            doc.get("row_height", cfg.ROW_HEIGHT_UM), doc.get("source", path))


# yosys の `stat` は版によって 1 行の列数が違う。**3 通りとも読む**:
#   "$_NAND_   30"            … 古い版（名前 → 個数）
#   "     30   $_NAND_"       … 新しい版（個数 → 名前）
#   "     30   28869  NAND2"  … `-liberty` 付き（個数 → 面積 → 名前）
# ★ 3 つめが読めず **黙って 0 と報告していた**（U37 の洗い出しで踏んだ、
#   2026-09-17）。`=== <top> ===` は見つかるので「top が無い」とも言わず、
#   「FF 0 / combinational 0 / 0 gates」という**それらしい表**が出ていた。
_SKIP = ("wires", "bits", "ports", "cells", "memories")
_RE_NAME_FIRST = re.compile(r"^\s+(\$\S+)\s+(\d+)\s*$", re.M)
_RE_COUNT_NAME = re.compile(r"^\s+(\d+)\s+(\$?[A-Za-z_]\S*)\s*$", re.M)
_RE_COUNT_AREA_NAME = re.compile(r"^\s+(\d+)\s+[\d.eE+-]+\s+(\$?[A-Za-z_]\S*)\s*$", re.M)


def parse(path: str) -> dict[str, dict[str, int]]:
    txt = open(path).read()
    mods = {}
    for name, body in re.findall(r"=== (\S+) ===\n(.*?)(?=\n===|\Z)", txt, re.S):
        d = {k: int(v) for k, v in _RE_NAME_FIRST.findall(body)}
        for rx in (_RE_COUNT_NAME, _RE_COUNT_AREA_NAME):
            d.update({k: int(v) for v, k in rx.findall(body)
                      if not k.endswith(_SKIP)})
        mods[name] = d
    return mods


def expand(mods, name, mult=1, acc=None):
    acc = collections.Counter() if acc is None else acc
    for k, v in mods.get(name, {}).items():
        if k in mods:
            expand(mods, k, mult * v, acc)
        else:
            acc[k] += mult * v
    return acc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("statfile")
    ap.add_argument("--top", required=True)
    # ★ 面積表は **STDCELL 正本**の中。スクリプトの隣ではない（U37）
    ap.add_argument("--areas", default=cfg.stdcell_file("cell_area.json"))
    a = ap.parse_args()

    A, row_h, src = load_areas(a.areas)
    need = {n for v in MAP.values() for n in v} | {FALLBACK, FF_PLAIN, FF_EN}
    missing = sorted(need - set(A))
    if missing:
        print(f"** {a.areas} に無いセル: {', '.join(missing)}", file=sys.stderr)

    def area_of(names):
        return sum(A.get(n, A[FALLBACK]) for n in names)

    mods = parse(a.statfile)
    if a.top not in mods:
        sys.exit(f"top module '{a.top}' not found in {a.statfile}")
    cells = expand(mods, a.top)

    # ★ **数えられなかったものを 0 と報告しない**（U37、2026-09-17）。
    #   `=== <top> ===` が在るだけでは「読めた」ことにならない。
    real = [k for k in cells if not k.startswith("$")]
    if not cells:
        body = re.search(rf"=== {re.escape(a.top)} ===\n(.*?)(?=\n===|\Z)",
                         open(a.statfile).read(), re.S)
        head = [l for l in (body.group(1).splitlines() if body else []) if l.strip()][:6]
        sys.exit(f"{a.top} の中にセルが 1 つも読めなかった: {cfg.show(a.statfile)}\n"
                 f"  読むのは yosys の `stat`。列の並びは 3 通りに対応している。\n"
                 f"  実際に見た行:\n    " + "\n    ".join(head))
    if real and not [k for k in cells if k.startswith("$")]:
        print(f"** 実セル名しか無い（{', '.join(sorted(real)[:4])} …）＝"
              f"**マッピング後の stat**。表にある名前は**そのままの面積**で数える。\n"
              f"   この道具の本来の入力は `abc -g simple` までの見積り用 stat。"
              f"マッピング後はネットリストを直接読む apr/syn_report.py の方が確か。",
              file=sys.stderr)

    ff = comb = 0
    area = 0.0
    detail = collections.Counter()
    for k, n in cells.items():
        if k == "$scopeinfo":
            continue
        # ★ 実セル名がそのまま面積表にあるなら**代用しない**（U37、2026-09-17）。
        #   マッピング後の stat を食わせたとき、NAND2 も MUX2 も INV_X1 も
        #   FALLBACK（AND2_X1）の面積で数えていた。表に本当の値がある。
        if not k.startswith("$") and k in A:
            names = [k]
            if "DFF" in k or "LATCH" in k:
                ff += n
            else:
                comb += n
        elif "DFF" in k or "LATCH" in k:
            ff += n
            names = [FF_EN] if ("DFFE" in k or "CE_" in k) else [FF_PLAIN]
        else:
            comb += n
            names = MAP.get(k, [FALLBACK])
        area += n * area_of(names)
        for nm in names:
            detail[nm] += n

    nand2 = A.get("NAND2", 1.0)
    print(f"--- 面積の出どころ: {a.areas}  (GDS {os.path.basename(src)}, 行高 {row_h} um) ---")
    print(f"--- cell mix ({a.top}) ---")
    for k, n in sorted(cells.items(), key=lambda x: -x[1]):
        if k == "$scopeinfo":
            continue
        nm = "+".join(MAP.get(k, [FALLBACK])) if not ("DFF" in k or "LATCH" in k) else \
             (FF_EN if ("DFFE" in k or "CE_" in k) else FF_PLAIN)
        print(f"  {k:18} {n:6d}  -> {nm}")
    print(f"\n実セル内訳      : " + ", ".join(f"{k} x{v}" for k, v in sorted(detail.items())))
    print(f"FF              : {ff}")
    print(f"combinational   : {comb}")
    print(f"raw cell area   : {area:,.0f} um2 = {area/1e6:.3f} mm2")
    print(f"NAND2 equiv     : {area/nand2:,.0f} gates  (NAND2 = {nand2:.1f} um2)")
    print(f"total cell width: {area/row_h:,.0f} um (row h={row_h} um)")
    core = CORE_AREA
    print(f"\ncore available  : {CORE_W:.0f} x {CORE_H:.0f} um から四隅を欠いて "
          f"{core/1e6:.3f} mm2")
    for u in (0.5, 0.6, 0.7, 0.8):
        need = area / u
        print(f"  util {u:.0%}: {need/1e6:6.3f} mm2  {'OK' if need <= core else 'NG'}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""drc_check_cells.py -- run the project's DRC rules on each standard cell.

The chip-level checker only sees whatever geometry the placement actually
instantiated, so a broken library cell stays invisible until something places
it -- which is exactly how BUF_X2's internal M1 spacing violation survived: a
stale `FOREIGN BUF_X1` in the LEF meant the layout carried BUF_X1's geometry
while the netlist said BUF_X2.

**値もレイヤも `rules.py` から取る**（M1/M2 の幅と間隔、V1 の間隔と囲み）。
STDCELL の GDS を触ったら必ず回す。

見る規則（**綴りはデッキと同じ**。出典 `$TR1UM_PDK/.../drc/run.drc` Cat-6）:

    M1.W1 / M1.S1 / M2.W1 / M2.S1 / V1.S1 / V1.M1 / M2.V1
    ERR01   製造グリッド 0.050（12 層すべての頂点。`01_Basics.drc`）
    M1.SW   M1(W) に接する M1 は間隔 2.0（1.4 ではない）
    M1.W3 / M2.W3   最大幅 45.0（パッドと AC は除外）
    V1.W1   カットは 1.4 ちょうど（幅・bbox_min・bbox_max）
    V1.GA   ポリとの間隔 1.2。**重なりは即違反**

★ **セル用の道具**。スクライブ認識層 (80,0) を見つけたら断る。デッキは全層を
  `input(...).not(MASK + SCRB)` で読むが、`SCRB` の導出（`TEMP.holes` の
  switch）はここでは再現していないので、フレームに当てるとスクライブ構造を
  違反として報告してしまう。`MASK` は引いている。
★ それでもここは**近似**。サインオフは `drc_pdk.py`（PDK の本物のデッキ）。
  この道具の役目は「ライブラリを触った直後に、KLayout アプリ無しで気づく」こと。

  usage:  apr/drc_check_cells.py [--gds lef/TR-1um_STDCELL.gds] [CELL ...]
"""
import argparse
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: E402  設計ルートを sys.path へ
# ★ `--gds` で入力を全部もらえるので、設計の config.py は**無くても動く**（U57）
cfg = apr_path.soft_config()  # noqa: E402
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


# `01_Basics.drc` が `ongrid( 0.050 )` を掛ける 12 層（綴りと順もデッキのまま）
ERR01_LAYERS = (("WN", rules.WN), ("AP", rules.AP), ("AN", rules.AN),
                ("AR", rules.AR), ("AC", rules.AC), ("GC", rules.GC),
                ("GR", rules.GR), ("CO", rules.CO), ("M1", rules.M1),
                ("V1", rules.V1), ("M2", rules.M2), ("PO", rules.PO))


def check_cell(ly, cell, dbu):
    """1 セルぶんの違反を `(規則名, 実測, 限界, x, y)` のリストで返す。

    規則名は **PDK のデッキと同じ綴り**（`M1.W1` など）にしてある。
    `drc_pdk.py` の出力と突き合わせるときに対応が取れるように。
    """
    def raw(lay):
        return db.Region(cell.begin_shapes_rec(ly.layer(*lay))).merged()

    # ★ デッキは**全層を `input(...).not(MASK + SCRB)` で読む**
    #   （`00_Layers.drc`）。生の層で見ると、除外されているはずの
    #   図形まで拾って偽陽性になる。`MASK` はここで引く。
    #   `SCRB` はセルには無い層なので `main()` 側で入力ごと弾く。
    mask = raw(rules.MASK)

    def reg(lay):
        r = raw(lay)
        return (r - mask).merged() if not mask.is_empty() else r

    def um(v):                      # µm -> dbu
        return int(round(v / dbu))

    m1, m2, v1 = reg(M1), reg(M2), reg(V1)
    ga = (reg(rules.GC) + reg(rules.GR)).merged()   # GA = GC + GR（02_Device.drc）
    ac, po = reg(rules.AC), reg(rules.PO)
    out = []

    def add(name, edges, limit):
        for e in edges:
            a, b = e.first, e.second
            cx = (a.p1.x + a.p2.x + b.p1.x + b.p2.x) / 4 * dbu
            cy = (a.p1.y + a.p2.y + b.p1.y + b.p2.y) / 4 * dbu
            out.append((name, e.distance() * dbu, limit, cx, cy, "<"))

    def add_polys(name, region, limit, measured=0.0, how="<"):
        for pg in region.each():
            b = pg.bbox()
            out.append((name, measured, limit,
                        (b.left + b.right) / 2 * dbu, (b.bottom + b.top) / 2 * dbu, how))

    add("M1.W1 width", m1.width_check(um(M1_W)), M1_W)
    add("M1.S1 space", m1.space_check(um(M1_S)), M1_S)
    add("M2.W1 width", m2.width_check(um(M2_W)), M2_W)
    add("M2.S1 space", m2.space_check(um(M2_S)), M2_S)
    add("V1.S1 space", v1.space_check(um(V1_S)), V1_S)
    # ★ 囲みは **`enclosed_check`（辺の対）** で見る。デッキの
    #   `V1.drc(enclosed(M1) < 1.0)` と同じ粒度になる（U56）。
    #   以前は `v1 - m1.sized(-1.0)` の**領域の引き算**で、見落としはしないが
    #   「1 つの via につき 1 件」になり、4 辺とも足りない via を
    #   デッキが 4 件と数えるのに対してこちらは 1 件だった。**同じものを
    #   見ていても数え方が違うと突き合わせられない。**（`drc_check.py` は
    #   最初からこちらの API を使っていた）
    for tag, metal in (("V1.M1 enclosure", m1), ("M2.V1 enclosure", m2)):
        add(tag, v1.enclosed_check(metal, um(V1_ENC)), V1_ENC)

    # --- ERR01: 製造グリッド（U84） --------------------------------------
    # `01_Basics.drc` は **12 層すべて**に `(<層>).ongrid( 0.050 )` を掛ける。
    # 層は `00_Layers.drc` の `input(...).not(MASK + SCRB)` で読むので、
    # **ここも `reg()` を通す**（= `MASK` を引いた形）。`SCRB` はセルに無い
    # 層なので `main()` が入力ごと弾いている。
    # ★ **数字だけ写すと誤報が出る**（U84）。`grid_check` を生の層に当てると、
    #   パッドリングの角の 45° が 3 設計とも 31 頂点ぶん「グリッド外れ」に
    #   出たが、デッキは同じ GDS を clean と言う。デッキ側はそこを `SCRB` で
    #   落としているため。**層の導出ごと写して初めて一致する。**
    gg = um(rules.MFG_GRID)
    for tag, lay in ERR01_LAYERS:
        r = reg(lay)
        if r.is_empty():
            continue
        for e in r.grid_check(gg, gg).each():
            px, py = e.first.p1.x * dbu, e.first.p1.y * dbu
            out.append((f"ERR01 offgrid {tag}", 0.0, rules.MFG_GRID, px, py, "grid"))

    # ---- U55: PDK デッキにあって自作側に無かった 4 規則 -------------------
    # 出典は `$TR1UM_PDK/libs.tech/klayout/tech/drc/run.drc`（Cat-6）と
    # `02_Device.drc`（派生レイヤ）。**綴りも判定もデッキに合わせる。**

    # M1.SW: M1(W) に接する M1 は間隔 2.0（1.4 ではない）
    #   M1W = M1.sized(-5.0).merged.sized(5.0).merged
    m1w = m1.sized(-um(rules.M1_WIDE_MIN / 2.0)).merged()
    m1w = m1w.sized(um(rules.M1_WIDE_MIN / 2.0)).merged()
    if not m1w.is_empty():
        sw = m1.space_check(um(rules.M1_WIDE_SPACE_MIN)).polygons()
        sw.merged_semantics = False                    # デッキの `.raw`
        add_polys("M1.SW M1(W)-M1", sw.interacting(m1w), rules.M1_WIDE_SPACE_MIN)

    # M1.W3 / M2.W3: 最大幅 45.0（パッドと AC は除外）
    #   (M1 - M1P - AC).sized(-22.5).sized(22.5)
    half = um(rules.METAL_WIDTH_MAX / 2.0)
    m1p = (m1 & po).sized(um(5.0))
    m2p = (m2 & po).sized(um(5.0))
    for tag, wide in (("M1.W3 M1(I) Wmax", ((m1 - m1p) - ac).sized(-half).sized(half)),
                      ("M2.W3 M2(I) Wmax", (m2 - m2p).sized(-half).sized(half))):
        add_polys(tag, wide, rules.METAL_WIDTH_MAX, how=">")

    # V1.W1: カットは 1.4 ちょうど（幅・bbox_min・bbox_max すべて）
    v1s = v1 - v1.interacting(po)                      # V1P = V1.interacting(PO)
    add("V1.W1 Wfix", v1s.width_check(um(rules.V1_CUT)), rules.V1_CUT)
    for pg in v1s.each():
        b = pg.bbox()
        w, h = b.width() * dbu, b.height() * dbu
        lo, hi = min(w, h), max(w, h)
        cx, cy = (b.left + b.right) / 2 * dbu, (b.bottom + b.top) / 2 * dbu
        if lo < rules.V1_CUT - 1e-4:
            out.append(("V1.W1 bbox_min", lo, rules.V1_CUT, cx, cy, "<"))
        if hi > rules.V1_CUT + 1e-4:
            out.append(("V1.W1 bbox_max", hi, rules.V1_CUT, cx, cy, ">"))

    # V1.GA: 間隔 1.2、**重なりは即違反**
    add("V1.GA sep", v1.separation_check(ga, um(rules.V1_GA_SPACE_MIN)),
        rules.V1_GA_SPACE_MIN)
    add_polys("V1.GA overlap", v1 & ga, 0.0, how="hit")
    return out


def main(gds=None, only=()):
    gds = gds or cfg.CELL_GDS
    ly = db.Layout()
    ly.read(gds)
    dbu = ly.dbu
    # ★ **セル用の道具**。スクライブ認識層 (80,0) がある入力＝フレームや
    #   チップなので断る。デッキは `SCRB` を全層から引くが、その導出
    #   （`TEMP.holes` の switch）はここでは再現していないので、当てると
    #   スクライブ構造を違反として報告してしまう（実測: フレームに当てると
    #   M2.W1 / M2.S1 が 6 件と、ガードリング状の V1 の bbox が 1 件出る）。
    _scrb = ly.layer(*rules.SCRB_MARK)
    if any(not c.shapes(_scrb).is_empty() for c in ly.each_cell()):
        sys.exit(f"{cfg.show(gds)} にはスクライブ認識層 {rules.SCRB_MARK} がある。"
                 "\nこれはセルライブラリではない（フレーム / チップ）。"
                 "\nサインオフは apr/drc_pdk.py（PDK の本物のデッキ）で行う。")
    names = sorted(c.name for c in ly.each_cell()
                   if not only or c.name in only)
    bad = 0
    print(f"=== {cfg.show(gds)} : {len(names)} cell(s) ===")
    for n in names:
        v = check_cell(ly, ly.cell(n), dbu)
        if not v:
            continue
        bad += 1
        print(f"\n  {n}: {len(v)} violation(s)")
        for rule, d, lim, x, y, how in v:
            if how == "hit":
                what = "重なり"
            elif how == "grid":
                what = f"格子 {lim:.3f} um の外"
            elif how == ">":
                what = f"{d:.3f} um > {lim:.3f} um" if d else f"> {lim:.3f} um"
            else:
                what = f"{d:.3f} um < {lim:.3f} um" if d else f"< {lim:.3f} um"
            print(f"      {rule:20} {what:24} at "
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
    ap.add_argument("--gds", default=None)
    a = ap.parse_args()
    sys.exit(main(a.gds, set(a.cells)))

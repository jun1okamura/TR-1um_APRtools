#!/usr/bin/env python3
"""生成した .lib を検算する。

  usage: python3 verify_lib.py [tr1um_typ_5v0_25c.lib]

5 段構え:

  1. **表そのものの健全性** — 欠損が無いか、値が正か、
     負荷を増やすと遅延が増えるか、入力遷移を鈍らせると遅延が増えるか。
     単調でない = 測り損ねているということなので、ここで落とす。

  2. **格子の外での照合** — 格子点そのものではなく、**格子の間**
     （入力遷移 1.0ns / 負荷 150fF）で ngspice を回し、.lib を線形補間した
     値と突き合わせる。格子点で合うのは当たり前なので、間で合うかを見る。

  3. **入力容量の照合** — INV_X1 で INV_X1 を N 個駆動したときの実測遅延が、
     .lib を「負荷 = N x capacitance(A)」で引いた値と合うか。
     合えば、.lib に書いた capacitance が遅延計算に使える量だと言える。

  4. **マクロの書込みパス** — `char/REG8x16.json` の `webq` と `limits` が
     .lib に**値まで含めて**出ているか。表の形が template と合っているか。
     測っていない制約（setup）が紛れ込んでいないか。

  5. **.lib の構文** — 括弧の対応と必須項目。

★ **検算する .lib が無いときは「OK」ではなく「要確認」。**
  既定の場所が `char/` 固定（= `mklib.py` の既定の出力先）だったせいで、
  正本を `stdcell/<版>/` に置いたあと引数無しで流すと **4-5 段目が丸ごと
  飛んだまま「判定: OK」**と出ていた（2026-09-16 に発覚）。
  回らなかった検査は OK ではない。
"""
from __future__ import annotations
import json, os, re, subprocess, sys
import cellspec
from charlib import (HERE, VDD, SLEWS, LOADS, run_ngspice, header, ports_of,
                     all_ports_of, full_ramp, stdcell_file)

SLEW_V = 0.6        # 検算に使う入力遷移（20-80%）
import char_comb

TOL = 0.15          # 補間との許容ずれ

# collect.py が置いていく実測値。**これがあれば ngspice は回さない**。
# 特性化を手元の機械（18 コア）で流した場合、検算だけこちらで回すと
# 測定条件がずれるので、同じ実行の結果を使う。
VFY = None
_vp = f"{HERE}/char/_verify.json"
if os.path.exists(_vp):
    VFY = json.load(open(_vp))


def interp2(x_idx, y_idx, table, x, y):
    """2 次元線形補間（格子外は端の傾きで外挿しない=クランプ）"""
    def pos(idx, v):
        if v <= idx[0]: return 0, 0.0
        if v >= idx[-1]: return len(idx) - 2, 1.0
        for i in range(len(idx) - 1):
            if idx[i] <= v <= idx[i + 1]:
                return i, (v - idx[i]) / (idx[i + 1] - idx[i])
        return len(idx) - 2, 1.0
    i, a = pos(x_idx, x)
    j, b = pos(y_idx, y)
    v00, v01 = table[i][j], table[i][j + 1]
    v10, v11 = table[i + 1][j], table[i + 1][j + 1]
    return (v00 * (1 - a) * (1 - b) + v01 * (1 - a) * b +
            v10 * a * (1 - b) + v11 * a * b)


def check_tables():
    print("--- 1. 表の健全性 ---")
    ng = 0
    for f in sorted(os.listdir(f"{HERE}/char")):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        d = json.load(open(f"{HERE}/char/{f}"))
        name = d["cell"]
        groups = []
        sl = d.get("slews", SLEWS)          # パッドセルは格子が違う
        if d.get("pad"):
            for k, t in d["arc"].items():
                groups.append((f"OUT->PAD {k}", t))
            for mode in ("enable", "disable"):
                for k, t in d[mode].items():
                    groups.append((f"HIZ {mode} {k}", t))
        elif d.get("seq"):
            for k, t in d["ckq"].items():
                groups.append((f"CK->Q {k}", t))
        elif d.get("latch"):
            # SR ラッチはアクティブ端にしかアークが立たない（S↓ / R↓ では出力が
            # 動かない）。存在する向きの表だけを見る。
            for a in d["arcs"]:
                for k in ("cell_rise", "cell_fall", "rise_transition", "fall_transition"):
                    if a.get(k) is not None:
                        groups.append((f"{a['related_pin']}->{a['pin']} {k}", a[k]))
        elif d.get("macro"):
            # REG8x16 のようなマクロ。読出しアークは read[<ADD ピン>] の下、
            # 書込みアーク（WEB -> Q）は webq の下にある。
            # ★ **生成側（mklib.emit_macro）が出す表は全部ここに載せる。**
            #   載せ忘れると「検算 OK」が「検算していない」を意味してしまう。
            for ad, arc in sorted(d.get("read", {}).items()):
                for k, t in arc.items():
                    groups.append((f"{ad}->Q {k}", t))
            wq = d.get("webq")
            if wq:
                if wq.get("slews") != sl:
                    print(f"  ! {name} webq: 入力遷移の格子が読出し側と違う "
                          f"({wq.get('slews')} vs {sl})"); ng += 1
                for k in ("cell_rise", "rise_transition",
                          "cell_fall", "fall_transition"):
                    groups.append((f"WEB->Q {k}", wq.get(k)))
        else:
            for a in d["arcs"]:
                for k in ("cell_rise", "cell_fall", "rise_transition", "fall_transition"):
                    groups.append((f"{a['related_pin']}->{a['pin']} {k}", a[k]))
        for label, tbl in groups:
            if tbl is None or any(r is None for r in tbl):
                print(f"  ! {name} {label}: 行が欠けている"); ng += 1; continue
            flat = [v for r in tbl for v in r]
            if any(v is None for v in flat):
                n = sum(1 for v in flat if v is None)
                print(f"  ! {name} {label}: 測定できていない点が {n} 個"); ng += 1
            # **遅延が負になるのは異常ではない。**
            # 入力を鈍らせて負荷を軽くすると、入力が 50% を通る前に
            # 出力が 50% を通ることがある（NAND3/NAND4 の 16ns/10fF で実際に起きる）。
            # 出力は入力が動き出す前には動けないので、物理的な下限は
            # 「入力の 50% 通過時刻 - 傾斜の開始時刻」= フルスイング傾斜の半分。
            # 遷移時間（*_transition）は常に正。
            neg = []
            for ri, r in enumerate(tbl):
                idx1 = sl if len(sl) == len(tbl) else d.get("slews_t", sl)
                lim = 0.0 if "transition" in label else -full_ramp(idx1[ri]) * 1e-9 / 2
                for v in r:
                    if v is None or v > 0:
                        continue
                    if v <= lim:
                        print(f"  ! {name} {label}: 物理的にあり得ない値 {v*1e9:.3f}ns "
                              f"(入力遷移 {idx1[ri]}ns 行, 下限 {lim*1e9:.1f}ns)"); ng += 1
                    else:
                        neg.append((SLEWS[ri], v))
            if neg:
                w = min(v for _, v in neg)
                print(f"    {name} {label}: 負の遅延 {len(neg)} 点（最小 {w*1e9:.3f}ns / "
                      f"入力遷移 {max(s for s, _ in neg)}ns 側）— 鈍い入力・軽負荷では正常")
            # 負荷を増やすと必ず遅くなるはず
            for ri, r in enumerate(tbl):
                vv = [v for v in r if v is not None]
                if len(vv) > 1 and any(b < a * 0.98 for a, b in zip(vv, vv[1:])):
                    idx1 = sl if len(sl) == len(tbl) else d.get("slews_t", sl)
                    print(f"  ! {name} {label}: 負荷に対して単調でない "
                          f"(入力遷移 {idx1[ri]}ns 行)"); ng += 1
    print("  逸脱なし" if ng == 0 else f"  ** {ng} 件")
    return ng


def check_offgrid(cells=("INV_X1", "NAND2", "NOR2", "MUX2", "XOR2", "AND2_X1")):
    """格子の間で ngspice と .lib 補間を突き合わせる"""
    slew, cl = (VFY["slew"], VFY["cl"]) if VFY else (1.0, 150.0)
    src = "collect.py が回収した実測値" if VFY else "この場で ngspice を実行"
    print(f"\n--- 2. 格子の外（入力遷移 {slew}ns / 負荷 {cl:g}fF）で照合 ---")
    print(f"  ({src})")
    print(f"  {'cell':<10}{'arc':<10}{'向き':<5}{'ngspice':>9}{'.lib 補間':>10}{'ずれ':>8}")
    ng = 0
    for cell in cells:
        p = f"{HERE}/char/{cell}.json"
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        a = d["arcs"][0]
        opin, ipin, sense = a["pin"], a["related_pin"], a["sense"]
        outs = cellspec.COMB[cell]
        side = next(s for o, i, s, _ in
                    __import__("charlib").arcs_of(cell, outs) if o == opin and i == ipin)
        for out_rise in (True, False):
            rise_in = (not out_rise) if sense == "negative_unate" else out_rise
            # 負荷 7 点のうち 1 点を格子外の値に差し替える（先頭を使う）
            if VFY is not None:
                got = VFY["offgrid"].get(cell, {}).get("r" if out_rise else "f")
            else:
                deck = char_comb.build_delay(cell, opin, ipin, side, slew,
                                             rise_in, set(outs))
                deck = deck.replace(f"C0 o0_{opin} 0 {LOADS[0]}f",
                                    f"C0 o0_{opin} 0 {cl:g}f")
                vals, _ = run_ngspice(deck, f"vfy_{cell}_{'r' if out_rise else 'f'}")
                got = vals.get(("dr0" if out_rise else "df0"))
            tbl = a["cell_rise"] if out_rise else a["cell_fall"]
            exp = interp2(SLEWS, LOADS, tbl, slew, cl)
            if got is None or exp is None:
                print(f"  ! {cell} 測定できず"); ng += 1; continue
            err = abs(got - exp) / exp
            mark = "" if err < TOL else "  ** ずれが大きい"
            if err >= TOL: ng += 1
            print(f"  {cell:<10}{ipin+'->'+opin:<10}{'rise' if out_rise else 'fall':<5}"
                  f"{got*1e9:8.3f}ns{exp*1e9:9.3f}ns{err:7.1%}{mark}")
    print("  " + ("全点が許容内" if ng == 0 else f"** {ng} 件が {TOL:.0%} を超えた"))
    return ng


def check_cap():
    """INV_X1 が INV_X1 を N 個駆動したときの遅延が、
    .lib の capacitance を使った引き当てと合うか"""
    print("\n--- 3. 入力容量 capacitance の妥当性（INV_X1 -> INV_X1 x N）---")
    d = json.load(open(f"{HERE}/char/INV_X1.json"))
    # .lib に書くのは較正済みの等価容量（cap_cal）。電荷から出した cap ではない。
    cin = (d.get("cap_cal") or d["cap"])["A"]
    tbl = d["arcs"][0]["cell_fall"]        # 入力立上り -> 出力立下り
    print(f"  .lib の capacitance(A) = {cin:.1f} fF")
    print(f"  {'ファンアウト':>10}{'ngspice':>10}{'.lib(N x Cin)':>14}{'ずれ':>8}")
    ng = 0
    for n in (1, 2, 4, 8):
        if VFY is not None:
            got = VFY["fanout"].get(str(n))
            exp = interp2(SLEWS, LOADS, tbl, SLEW_V, cin * n)
            if got is None:
                print(f"  ! ファンアウト {n}: 測定できず"); ng += 1; continue
            err = abs(got - exp) / exp
            if err >= 0.20: ng += 1
            print(f"  {n:>10}{got*1e9:9.3f}ns{exp*1e9:13.3f}ns{err:7.1%}"
                  f"{'  ** ずれが大きい' if err >= 0.20 else ''}")
            continue
        L = [f"* INV_X1 -> INV_X1 x{n} 実負荷での遅延"]
        L += header("INV_X1")
        # 入力は 20-80% が SLEW_V になる傾斜（表の index_1 と同じ定義）
        L.append(f"Vin src 0 PWL(0 0 100n 0 {100+full_ramp(SLEW_V):g}n 5)")
        L.append("Rin src A 0.001")
        # ポート順はネットリストの宣言順に従う（KLayout の抽出は ... vss vdd）
        pp = all_ports_of("INV_X1")
        L.append("XU " + " ".join("A" if p == "A" else ("Y" if p == "Y" else p)
                                  for p in pp) + " INV_X1")
        for k in range(n):
            L.append(f"XL{k} " + " ".join("Y" if p == "A" else
                                          (f"nc{k}" if p == "Y" else p)
                                          for p in pp) + " INV_X1")
            L.append(f"Cn{k} nc{k} 0 20f")   # 次段の出力にも軽い負荷
        L.append(".tran 0.02n 260n")
        L.append(".meas tran d TRIG v(A) VAL=2.5 RISE=1 TARG v(Y) VAL=2.5 FALL=1")
        L += ["", ".end", ""]
        vals, _ = run_ngspice("\n".join(L), f"vfy_fo{n}")
        got = vals.get("d")
        exp = interp2(SLEWS, LOADS, tbl, SLEW_V, cin * n)
        if got is None:
            print(f"  ! ファンアウト {n}: 測定できず"); ng += 1; continue
        err = abs(got - exp) / exp
        if err >= 0.20: ng += 1
        print(f"  {n:>10}{got*1e9:9.3f}ns{exp*1e9:13.3f}ns{err:7.1%}"
              f"{'  ** ずれが大きい' if err >= 0.20 else ''}")
    print("  " + ("capacitance は遅延計算に使える値" if ng == 0
                  else f"** {ng} 点でずれが大きい"))
    return ng


def lib_default():
    """検算する .lib を探す。`mklib.py` の既定の出力先 → 正本の順。

    見つからなければ `None` を返し、**呼び手は NG として数える**。
    """
    return stdcell_file("tr1um_typ_5v0_25c.lib",
                        first=(f"{HERE}/tr1um_typ_5v0_25c.lib",),
                        missing_ok=True)


def _block(txt, start):
    """txt[start] 以降の最初の `{` から、対応する `}` までを返す"""
    i = txt.index("{", start)
    depth = 0
    for j in range(i, len(txt)):
        if txt[j] == "{":
            depth += 1
        elif txt[j] == "}":
            depth -= 1
            if depth == 0:
                return txt[start:j + 1]
    return None


def lib_cell_block(txt, cell):
    m = re.search(r"^\s*cell \(%s\)\s*\{" % re.escape(cell), txt, re.M)
    return None if not m else _block(txt, m.start())


def timing_groups(blk):
    """`timing () { ... }` を括弧の対応で切り出す（入れ子の values も込み）"""
    for m in re.finditer(r"timing \(\)\s*\{", blk):
        g = _block(blk, m.start())
        if g:
            yield g


# scalar 制約の値だけを拾う。表（`values("a, b, ...", \ ...)`）は
# 数字の直後に `"` が来ないので、この正規表現には掛からない。
SCALAR_V = re.compile(r'values\(\s*"(-?[\d.]+(?:[eE][-+]?\d+)?)"\s*\)')


def check_macro(path):
    """マクロが **測った通りに .lib へ出ているか**（json ⇔ .lib）。

    U73 の教訓は「Liberty に書いた」で終わりにしないこと。ここでは
    **書いたはずの値が .lib の中に本当にあるか**を突き合わせる。
    （その制約を STA が見るかどうかは別の話で、`syn/sta/check_macro_arcs.tcl`
    の担当。見ないと分かっている `min_pulse_width` も、.lib には
    記録として出ている必要がある。）
    """
    print("\n--- 4. マクロの書込みパス（json ⇔ .lib）---")
    if not path:
        print("  ! 検算する .lib が見つからない"); return 1
    txt = open(path).read()
    ng, seen_any = 0, False
    for f in sorted(os.listdir(f"{HERE}/char")):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        d = json.load(open(f"{HERE}/char/{f}"))
        if not d.get("macro"):
            continue
        seen_any = True
        name = d["cell"]
        blk = lib_cell_block(txt, name)
        if blk is None:
            print(f"  ! {name}: .lib に cell ({name}) が無い"); ng += 1; continue
        ns, nl = len(d["slews"]), len(d["loads"])

        # (a) 表の形が template と合っているか
        tabs = [(f"{ad}->Q", arc) for ad, arc in sorted(d.get("read", {}).items())]
        if d.get("webq"):
            tabs.append(("WEB->Q", d["webq"]))
        for label, arc in tabs:
            for k in ("cell_rise", "rise_transition", "cell_fall", "fall_transition"):
                t = arc.get(k)
                if not t or len(t) != ns or any(len(r) != nl for r in t):
                    shape = "無し" if not t else f"{len(t)}x{len(t[0])}"
                    print(f"  ! {name} {label} {k}: 表が {ns}x{nl} でない（{shape}）")
                    ng += 1

        # (b) limits そのものの筋
        lim = d.get("limits", {})
        for knob, x in sorted(lim.items()):
            if not (x["pass"] > x["fail"] > 0):
                print(f"  ! {name} limits.{knob}: "
                      f"pass {x['pass']} > fail {x['fail']} > 0 になっていない"); ng += 1
            if x.get("netlist") != d.get("netlist"):
                print(f"  ! {name} limits.{knob}: 表と違うネットリストで測っている"
                      f"（{x.get('netlist')} vs {d.get('netlist')}）"); ng += 1

        # (c) .lib に出ているか — 値まで突き合わせる
        got = {}
        for g in timing_groups(blk):
            m = re.search(r"timing_type\s*:\s*(\w+)\s*;", g)
            tt = m.group(1) if m else "(無指定)"
            got.setdefault(tt, []).extend(float(v) for v in SCALAR_V.findall(g))
        exp = {}
        if "weblow" in lim:
            exp["min_pulse_width"] = [lim["weblow"]["pass"]]
        h = [lim[k]["pass"] for k in ("webpre", "dhold") if k in lim]
        if h:
            exp["hold_rising"] = sorted(h * 2)    # rise/fall で 2 本ずつ
        exp["combinational"] = None               # 本数だけ見る（表は (a) で見た）
        for tt, want in exp.items():
            have = got.get(tt)
            if have is None:
                print(f"  ! {name}: .lib に {tt} が無い（json には測定値がある）")
                ng += 1; continue
            if want is None:
                continue
            if len(have) != len(want) or any(
                    abs(a - b) > 1e-4 for a, b in zip(sorted(have), want)):
                print(f"  ! {name} {tt}: .lib の値 {sorted(have)} が "
                      f"json の {want} と違う"); ng += 1
        narc = len(got.get("combinational", [])) or \
            sum(1 for g in timing_groups(blk) if "combinational" in g)
        nwant = len(d.get("read", {})) + (1 if d.get("webq") else 0)
        if narc != nwant:
            print(f"  ! {name}: 組合せアークが {narc} 本（json からは {nwant} 本）")
            ng += 1

        # (d) 測っていない制約が紛れていないか
        for tt in sorted(got):
            if tt.startswith("setup") or tt.startswith("recovery") \
                    or tt.startswith("removal"):
                print(f"  ! {name}: 測っていない {tt} が .lib にある"); ng += 1

        print(f"  {name}: 組合せアーク {narc} 本 / "
              f"{' / '.join(f'{k} {sorted(v)}' for k, v in sorted(got.items()) if v)}")
    if not seen_any:
        print("  マクロの json が無い（検査するものが無い）")
    print("  逸脱なし" if ng == 0 else f"  ** {ng} 件")
    return ng


def check_lib_syntax(path):
    print(f"\n--- 5. .lib の構文（括弧の対応・必須項目）---")
    if not path:
        print("  ! 検算する .lib が見つからない"); return 1
    txt = open(path).read()
    depth, ng = 0, 0
    for i, ch in enumerate(txt):
        if ch == "{": depth += 1
        elif ch == "}": depth -= 1
        if depth < 0:
            print("  ! 閉じ括弧が多い"); ng += 1; break
    if depth != 0:
        print(f"  ! 括弧が閉じていない (depth={depth})"); ng += 1
    for need in ("delay_model : table_lookup", "lu_table_template",
                 "nom_voltage", "operating_conditions"):
        if need not in txt:
            print(f"  ! 必須項目が無い: {need}"); ng += 1
    ncell = len(re.findall(r"^\s*cell \(", txt, re.M))
    nff = len(re.findall(r"^\s*ff \(", txt, re.M))
    ntim = len(re.findall(r"^\s*timing \(\)", txt, re.M))
    print(f"  cell {ncell} / ff {nff} / timing アーク {ntim} / {len(txt.splitlines())} 行")
    print("  逸脱なし" if ng == 0 else f"  ** {ng} 件")
    return ng


if __name__ == "__main__":
    lib = sys.argv[1] if len(sys.argv) > 1 else lib_default()
    print("=" * 72)
    print(" Liberty 検算")
    print("=" * 72)
    # ★ 機械依存のパスをログに焼き付けない（U24）。char/ からの相対で出す。
    shown = os.path.relpath(lib, HERE) if lib else "** 見つからない **"
    print(f" 検算する .lib: {shown}")
    n = check_tables() + check_offgrid() + check_cap()
    n += check_macro(lib) + check_lib_syntax(lib)
    print("\n" + "=" * 72)
    print("判定: OK" if n == 0 else f"判定: 要確認 {n} 件")
    sys.exit(1 if n else 0)

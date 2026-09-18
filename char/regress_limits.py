#!/usr/bin/env python3
"""`REG8x16` の書込みパスの境界を **ngspice で測り直して守る**回帰（U73）。

  usage: python3 $APRTOOLS/char/regress_limits.py
         python3 $APRTOOLS/char/regress_limits.py --only weblow
         python3 $APRTOOLS/char/regress_limits.py --lib <別の .lib>

なぜ要るか:
  **`min_pulse_width` を OpenSTA は見ない**（U73 で否定対照まで取って確認:
  低の幅を要求より狭い 5ns にしても違反が出ない。`clock : true` を足しても
  `set_min_pulse_width` を当てても変わらない）。`hold_rising` も `WEB` を
  クロックとして宣言した設計でしか効かない。
  つまり **`.lib` に書いてあるのに、STA が守ってくれない制約がある。**
  担保は ngspice 側にしか無いのに、**回帰になっていなかった**（U73 の残り）。

  実際、2026-09-18 に 2 つ起きた:
    * U96 で `min_pulse_width` が **11 -> 10.0 ns** に動いた
    * その掃引の判定に穴があり、**2 ns でも「保持する」**と出ていた
      （`char_mem.sweep_edge()`。何も書かれなかった場合を通していた）
  どちらも**回していれば気づけた**類の話。

何を守るか — `char/char/REG8x16.json` の `limits` の 3 つ:

  webpre  アドレス保持  `WEB↑` -> ADD 変更
  weblow  `WEB` の最小低幅   （= `.lib` の `min_pulse_width`）
  dhold   データ保持    `WEB↑` -> D 変更

  それぞれ **pass 側と fail 側の 2 点だけ**回し直して、境界が動いていない
  ことを見る（1 つ 2 デッキ、3 つで 6 デッキ）。**掃引ではなく回帰**なので
  範囲は振らない。動いていたら「どちらへ動いたか」を出して落ちる。

  あわせて **`.lib` の `min_pulse_width` が `limits.weblow.pass` と一致するか**も
  見る（写しになっていないことの確認。U99 と同じ形）。

  ★ **表と同じネットリストで測る。** `limits[*].netlist` が `json` の
    `netlist` と食い違っていたら、測る前に落とす（U71 の取り違え対策）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = "REG8x16"
JSON = os.path.join(HERE, "char", f"{CELL}.json")
# lint: ok char/ から APRtools の根を取る（apr/ の道具を呼ぶため。mkcells_gds.py と同じ）
APR_LIB_QUERY = os.path.join(os.path.dirname(HERE), "apr", "lib_query.py")
FLAG = {"webpre": "--web-pre", "weblow": "--web-low", "dhold": "--d-hold"}
LABEL = {"webpre": "アドレス保持（WEB↑ -> ADD 変更）",
         "weblow": "WEB の最小低幅",
         "dhold": "データ保持（WEB↑ -> D 変更）"}


def stdcell_lib():
    """既定の `.lib`。`char/verify_lib.py` と同じ探し方。"""
    # lint: ok char/ から APRtools の根を取る（正本の .lib を読むため。mkcells_gds.py と同じ）
    root = os.path.dirname(HERE)
    ver = os.environ.get("TR1UM_STDCELL", "v59_4")
    p = os.path.join(root, "stdcell", ver, "tr1um_typ_5v0_25c.lib")
    return p if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=JSON, help=f"守る値の出どころ（既定 {JSON}）")
    ap.add_argument("--netlist", "-n", default=None,
                    help="測るネットリスト（既定は json の netlist から決める）")
    ap.add_argument("--lib", default=None, help="min_pulse_width を突き合わせる .lib")
    ap.add_argument("--only", choices=sorted(FLAG), help="1 つだけ回す")
    a = ap.parse_args()

    if not os.path.exists(a.json):
        raise SystemExit(f"** {a.json} が無い。先に char_mem.py を回すこと")
    d = json.load(open(a.json))
    lim = d.get("limits") or {}
    if not lim:
        raise SystemExit(f"** {a.json} に limits が無い。"
                         f"`char_mem.py --web-pre/--web-low/--d-hold` の掃引が要る")

    # ★ 表と limits が同じネットリストで測られているか（U71）
    for k, v in sorted(lim.items()):
        if v.get("netlist") != d.get("netlist"):
            raise SystemExit(
                f"** limits.{k} と表のネットリストが違う"
                f"（{v.get('netlist')} vs {d.get('netlist')}）。\n"
                f"   混ざった値では回帰にならない。掃引を回し直すこと")

    netlist = a.netlist or os.path.join(HERE, d["netlist"])
    if not os.path.exists(netlist):
        raise SystemExit(f"** ネットリストが無い: {netlist}\n"
                         f"   `-n` で明示するか、`mkcells_gds.py` を回すこと")

    # ★ **回せるかを先に確かめる**（決定 23）。ngspice が無いのを
    #   「境界が動いた」と報告したら、回帰として嘘をつくことになる。
    sys.path.insert(0, HERE)
    from check_comb import need_ngspice          # noqa: E402
    need_ngspice()

    print(f"守る値 : {a.json}")
    print(f"測る網 : {os.path.relpath(netlist, HERE)}")
    print()

    ng = []
    knobs = [a.only] if a.only else sorted(lim)
    with tempfile.TemporaryDirectory() as tmp:
        for k in knobs:
            if k not in FLAG:
                print(f"  {k}: 回し方を知らないつまみ。飛ばす")
                continue
            want_pass, want_fail = lim[k]["pass"], lim[k]["fail"]
            out = os.path.join(tmp, f"{k}.json")
            cmd = [sys.executable, os.path.join(HERE, "char_mem.py"),
                   "-n", netlist, "-o", out, FLAG[k],
                   f"{want_fail:g},{want_pass:g}"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            got = {}
            if os.path.exists(out):
                got = (json.load(open(out)).get("limits") or {}).get(k, {})
            print(f"=== {k}  {LABEL[k]}")
            print(f"    期待 : {want_fail:g} ns で保持せず / {want_pass:g} ns で保持する")
            if r.returncode != 0:
                # ★ **回らなかったことを「動いた」と言わない。**
                print(f"    ** char_mem.py が落ちた（exit {r.returncode}）。回帰の判定はできない")
                print("\n".join("      " + x for x in
                                 (r.stderr or r.stdout).strip().splitlines()[-4:]))
                ng.append(f"{k}（回らなかった）")
            elif not got:
                # 境界を跨がなかった = **両方とも同じ側**。どちら側かを言う
                tail = "\n".join(r.stdout.strip().splitlines()[-4:])
                print(f"    実測 : **境界が動いた**（この 2 点では跨がない）")
                print("\n".join("      " + x for x in tail.splitlines()))
                ng.append(k)
            elif (got["pass"], got["fail"]) != (want_pass, want_fail):
                print(f"    実測 : pass {got['pass']:g} / fail {got['fail']:g}  **食い違う**")
                ng.append(k)
            else:
                print(f"    実測 : 同じ（pass {got['pass']:g} / fail {got['fail']:g}）  OK")
            print()

    # `.lib` の min_pulse_width が weblow と一致するか（写しになっていないか）
    lib = a.lib or stdcell_lib()
    if lib and "weblow" in lim:
        q = subprocess.run(
            [sys.executable, APR_LIB_QUERY, "mpw", lib, CELL, "WEB"],
            capture_output=True, text=True)
        got = q.stdout.strip()
        want = f"{lim['weblow']['pass']:g}"
        ok = got == want
        print(f"=== .lib の min_pulse_width")
        print(f"    {os.path.basename(lib)}: {got or '（読めない）'}  / json の weblow.pass: {want}"
              f"  {'OK' if ok else '**食い違う**'}")
        if not ok:
            print("    -> `mklib.py` を回し直す（json が正、.lib は生成物）")
            ng.append("lib")
        print()
    elif not lib:
        print("=== .lib が見つからないので min_pulse_width の突き合わせは飛ばした")
        print()

    print("=" * 60)
    if ng:
        print(f"判定: **{len(ng)} 件 食い違う** — {', '.join(ng)}")
        print("  ★ OpenSTA は min_pulse_width も（宣言の無い）hold_rising も見ない（U73）。")
        print("    ここが唯一の担保なので、直すまで数字を外に出さないこと。")
        return 1
    print("判定: OK — 書込みパスの境界は動いていない")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

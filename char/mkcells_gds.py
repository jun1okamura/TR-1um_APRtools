#!/usr/bin/env python3
"""特性化用のセルネットリストを **GDS から、並列をまとめずに**作る（U96）。

  usage: python3 mkcells_gds.py                       # -> char/cells_gds/
         python3 mkcells_gds.py --gds <別の GDS> -o <別の置き場>
         python3 mkcells_gds.py --check               # 既存と数だけ突き合わせる

なぜ要るか:
  `char/cells_ext/` は `loadext.py` が `<設計>/lef/extracted`（**PDK の LVS
  ランセット出力**）から起こしたもの。ランセットは**並列 MOS をまとめる**ので、
  マルチフィンガで描いたセルは**フィンガが 1 個に潰れた姿**になっている。

  この BSIM3 カードは狭幅のしきい値項を持つ（PMOS `k3 19.94` / `w0 3.12e-6`、
  NMOS `k3 86.28` / `w0 5e-5`、`wint` も 0 でない）ので、**W=5.1 の 2 並列と
  W=10.2 の 1 個は同じ Vth にならない**。`BUFTH` のトリップ点で実測 0.15 V
  動いた（U95）。**LVS が通るネットリストと、ngspice に持っていってよいネットリストは別物。**

  GDS と素子数が食い違っていたのは 7 セル:
    BUFTH 10/8 ・ BUF_X2 6/4 ・ DEL1 10/8 ・ DFFRB 29/26 ・ DFFS 29/28 ・
    MUXDFFRB 41/38 ・ DEC2 20/28（これだけ逆向き＝写しが古い）

作り方は `cells_ext` と同じ道を通す。違うのは 1 つだけ:
  `klayout_extract.py --no-combine`（まとめない）で GDS から直接起こす。
  そのあとは `loadext.convert()` と同じ整形を掛けるので、**形式は完全に同じ**。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# lint: ok char/ から APRtools の根を取る（隣の apr/ の道具を呼ぶため）
APR = os.path.join(os.path.dirname(HERE), "apr")
sys.path.insert(0, HERE)
import loadext  # noqa: E402

# lint: ok char/ から APRtools の根を取る（正本のセル GDS を読むため）
GDS = os.path.join(os.path.dirname(HERE), "stdcell", "v59_4",
                   "TR-1um_STDCELL.gds")
OUT = os.path.join(HERE, "cells_gds")
REF = os.path.join(HERE, "cells_ext")

# --- フレーム（パッドセル）------------------------------------------------
# `char_pad.py` は `cells_pad/OSS_FRAME_GIO_sim.spi` を読む。これも
# `frame2sim.py` が **PDK の LVS ランセット出力**から起こしていたので、
# 標準セルと同じ 2 つの不具合を持つ（U96）。GDS から起こし直す。
from charlib import FRAME_GDS, FRAME_TOP  # noqa: E402  正本は charlib（決定 21）
FRAME_OUT = os.path.join(HERE, "cells_pad", "OSS_FRAME_GIO_sim.spi")


def build_frame(gds, top, out):
    """フレームを GDS から起こして `frame2sim.py` に通す。"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ext = os.path.join(tmp, f"{top}.extracted")
        r = subprocess.run(
            [sys.executable, os.path.join(APR, "klayout_extract.py"),
             gds, top, "--no-combine", "-o", ext],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(ext):
            raise SystemExit(f"** フレームを抽出できない: {gds} ({top})\n"
                             + (r.stderr or "")[-800:])
        r = subprocess.run(
            [sys.executable, os.path.join(APR, "frame2sim.py"), ext, "-o", out],
            capture_output=True, text=True)
        print(r.stdout.rstrip() or r.stderr.rstrip())
        if r.returncode != 0:
            raise SystemExit("** frame2sim に失敗")
    print(f"  -> char/{os.path.relpath(out, HERE)}"
          f"（char_pad.py はここを読む）")


def cells_of(ref):
    """どのセルを起こすか。既存の置き場にあるものと同じ顔ぶれにする。"""
    if not os.path.isdir(ref):
        raise SystemExit(f"{ref} が無い。--cells で明示するか、先に loadext.py を回すこと")
    return sorted(f[:-len(".spi")] for f in os.listdir(ref) if f.endswith(".spi"))


def ntr(path):
    """素子数。**階層セルは平らにして数える**（トップの `XM` だけでは足りない）。

    ★ 2026-09-18 まで `^XM` の本数を数えていた。`cells_ext/REG8x16.spi` は
      下位回路を持つので **72**（トップの直下だけ）になり、`--flat` で
      起こした 1876 と並べて「+1804」という意味の無い差が出ていた。
    """
    # ★ 継続行（`+`）をつないでから読む。つながないと、サブサーキット
    #   呼び出しの**行末にある回路名**を取り損ねて、その下の素子が丸ごと
    #   数から落ちる（`cells_ext/REG8x16.spi` が 1876 ではなく 1600 に出た）。
    src = []
    for ln in open(path, encoding="utf-8"):
        t = ln.rstrip("\n").strip()
        if t.startswith("+") and src:
            src[-1] += " " + t[1:].strip()
        else:
            src.append(t)
    subs, cur = {}, None
    for t in src:
        u = t.upper()
        if u.startswith(".SUBCKT"):
            cur = t.split()[1]
            subs[cur] = {"n": 0, "kids": []}
        elif u.startswith(".ENDS"):
            cur = None
        elif cur and re.match(r"^XM", t):
            subs[cur]["n"] += 1
        elif cur and re.match(r"^X(?!M)", t):
            subs[cur]["kids"].append(t.split()[-1])
    if not subs:
        return 0
    top = next(iter(subs))                      # 先頭の `.SUBCKT` がそのセル

    def walk(name, depth=0):
        if depth > 20 or name not in subs:      # 循環よけ
            return 0
        d = subs[name]
        return d["n"] + sum(walk(k, depth + 1) for k in d["kids"])
    return walk(top)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", default=GDS)
    ap.add_argument("-o", "--out", default=OUT)
    ap.add_argument("--ref", default=REF, help="顔ぶれと突き合わせ先（既定 cells_ext）")
    ap.add_argument("--cells", nargs="*", help="セルを明示する")
    ap.add_argument("--check", action="store_true", help="書かずに数だけ見る")
    ap.add_argument("--frame", action="store_true",
                    help="フレーム（パッドセル）も GDS から起こす -> cells_pad/")
    ap.add_argument("--frame-gds", default=FRAME_GDS)
    a = ap.parse_args()

    if a.frame:
        print(f"フレーム: {a.frame_gds} ({FRAME_TOP})")
        build_frame(a.frame_gds, FRAME_TOP, FRAME_OUT)
        print()

    cells = a.cells or cells_of(a.ref)
    if not a.check:
        os.makedirs(a.out, exist_ok=True)

    print(f"GDS : {a.gds}")
    print(f"出力 : {a.out}" + ("  （--check なので書かない）" if a.check else ""))
    print()
    print(f"{'cell':<12}{'GDS(未combine)':>16}{'cells_ext':>12}{'差':>5}  ports")
    diff, flattened = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for cell in cells:
            ext = os.path.join(tmp, f"{cell}.extracted")
            r = subprocess.run(
                [sys.executable, os.path.join(APR, "klayout_extract.py"),
                 a.gds, cell, "--no-combine", "-o", ext],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(ext):
                print(f"{cell:<12}  ** 抽出できない: {r.stderr.strip().splitlines()[-1:]}")
                continue
            lines = loadext.convert(ext)
            # ★ 階層セル（マクロ）も**起こす**。2026-09-18 まで飛ばして
            #   `cells_ext` の写しを置いていたが、`char/char/REG8x16.json` の
            #   `netlist` を見たら **`REG8x16.spi`（= 抽出版）**で測ってあり、
            #   まさに直したい方だった。
            #
            # ★ **階層のまま起こしてはいけない**（2026-09-18、U96）。
            #   下位回路の内部ノードに名前が無いと、KLayout は
            #   `.SUBCKT OSS_DRV OUT HIZ vdd n17 n18 gnd` のように**番号で**
            #   ポートに昇格させる。**どれがどれかは意味を持たない**ので、
            #   読む側（`char_mem.py` の `--probe` など）が名前で当てにいくと
            #   黙って外れる。パッドで踏み、`REG8x16` では `webq`（書込みの
            #   アーク）が空になった。
            #   → **下位回路を持つセルは `--flat` で 1 つに落とす。**
            #     トップのポート名は GDS のラベルから来るので消えない。
            if any(re.match(r"^X(?!M)", s) for s in lines):
                flat = os.path.join(tmp, f"{cell}.flat.extracted")
                r = subprocess.run(
                    [sys.executable, os.path.join(APR, "klayout_extract.py"),
                     a.gds, cell, "--flat", "--no-combine", "-o", flat],
                    capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(flat):
                    print(f"{cell:<12}  ** --flat で抽出できない: "
                          f"{r.stderr.strip().splitlines()[-1:]}")
                    continue
                lines = loadext.convert(flat)
                if any(re.match(r"^X(?!M)", s) for s in lines):
                    raise SystemExit(f"** {cell}: --flat でも階層が残っている")
                flattened.append(cell)
            n_new = sum(1 for s in lines if re.match(r"^XM", s))
            refp = os.path.join(a.ref, f"{cell}.spi")
            n_ref = ntr(refp) if os.path.exists(refp) else None
            if not a.check:
                open(os.path.join(a.out, f"{cell}.spi"), "w").write("\n".join(lines) + "\n")
            d = "" if n_ref is None else f"{n_new - n_ref:+d}"
            if n_ref is not None and n_new != n_ref:
                diff.append((cell, n_new, n_ref))
            print(f"{cell:<12}{n_new:>16}{'-' if n_ref is None else n_ref:>12}{d:>5}  "
                  f"{' '.join(loadext.ports_of_lines(lines))}")

    print()
    if flattened:
        print(f"階層セル {len(flattened)} は `--flat` で 1 つに落とした: "
              f"{', '.join(flattened)}")
        print("  無名ネットが番号でポートに昇格するのを避けるため（U96）。")
        print("  `cells_ext` 側は階層のままなので、**素子数の比較は"
              "平らにした総数どうし**になる。")
        print()
    print(f"{len(cells)} セル。**素子数が変わるのは {len(diff)} セル**"
          f"（残りは元から並列が無いので同じネットリスト）:")
    for cell, n, r in diff:
        print(f"  {cell:<12} {r} -> {n}")
    if not a.check:
        print()
        print("使うには TR1UM_CELLDIR をこちらに向ける:")
        print(f"  TR1UM_CELLDIR={a.out} python3 char_comb.py ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

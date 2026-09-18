#!/usr/bin/env python3
"""設計側に残っている**同名の写し**を数えて、状態を分ける（U94）。

  usage: python3 $APRTOOLS/apr/check_copies.py <設計> [<設計> ...]
         python3 $APRTOOLS/apr/check_copies.py ../TR-1um_TD4 ../TR-1um_I2C_2026 \
                                               ../TR-1um_SCLK_SPI
         python3 $APRTOOLS/apr/check_copies.py --list stale ../TR-1um_TD4

なぜ要るか:
  U94 で**呼ばれていない 88 本**と**古いだけの 23 本**を消したが、まだ残る。
  残す理由があるもの（CI が呼ぶ上流テンプレート、移植の監査証跡、本当に
  設計固有）と、**ただ古いだけのもの**が混ざっている。
  ★ **危ないのは「古いだけ」だけ。** `U89` / `U14` で 2 度踏んだのは
    「APRtools で直したのに、設計側の古い写しを呼んでいた」という形で、
    **写しがあること自体ではなく、写しが古いこと**が事故になった。

  消す判断は設計ごとに要るが、**数えるのはいつでもできる**。
  数えていないと「たぶん大丈夫」で止まる（U35 / U93 で 3 度踏んだ形）。

分け方:

  同一      md5 が APRtools と一致。**今は無害**だが、APRtools を直した日に
            「古いだけ」へ落ちる。見張る対象。
  古いだけ  設計側にしか無い行が**設計固有の手掛かりを持たない**
            （`*_config` を読む / `reference/` を指す / 設計名を含む、が無い）。
            ★ **これが事故の形。**
  設計固有  設計側にしか無い行が上のどれかを持つ。移植の監査証跡（`spi_config`
            の薄皮など）もここ。
  CI        `.github/workflows/` が呼ぶもの。CI は**その設計だけ**を
            チェックアウトするので `$APRTOOLS` が無い。**残すのが正しい。**

  ★ **差分の行数では分けない。** 30 行以下でも設計固有のものが半分以上あった
    （2026-09-18 に実際に早合点した）。**設計側にしか無い行を読んで決める。**

  ★ **見分けは当て推量なので、逃がし方を用意する。** 写しの中に

      # copy: ok <残す理由>

  と 1 行書けば「設計固有（理由あり）」として数える（`lint.py` の
  `# lint: ok` と同じ形）。**理由が書いていない写しだけが「古いだけ」に残る。**
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# lint: ok 正本のリポジトリの根。設計側と突き合わせるのが仕事なので、ここは外を見る
APR_ROOT = os.path.dirname(HERE)

# 設計固有の手掛かり。設計側にしか無い行がこれを含めば「設計固有」。
MARKS = ("_config", "reference/", "cfg.", "ROOT", "CHIP",
         "td4", "TD4", "i2c", "I2C", "spi_", "SPI_", "portrait")
KINDS = ("同一", "古いだけ", "設計固有", "CI")


def md5(p):
    try:
        with open(p, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def tracked(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"** git リポジトリではない: {root}")
    return [f for f in out.stdout.split("\0") if f]


def ci_called(root, files):
    """`.github/workflows/` が名指しで呼んでいるものを集める。"""
    names = set()
    wf = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(wf):
        return names
    for dirpath, _dirs, fs in os.walk(wf):
        for f in fs:
            try:
                s = open(os.path.join(dirpath, f), encoding="utf-8",
                         errors="replace").read()
            except OSError:
                continue
            for g in files:
                if os.path.basename(g) in s:
                    names.add(g)
    return names


RE_OK = re.compile(r"#\s*copy:\s*ok\s*(.*)")


def classify(design_path, apr_path):
    """(種別, 設計側にしか無いコード行) を返す。"""
    if md5(design_path) == md5(apr_path):
        return "同一", []
    # ★ 理由が書いてあれば、それを尊重する（当て推量より書いた人が正しい）
    try:
        head = open(design_path, encoding="utf-8", errors="replace").read(4000)
    except OSError:
        head = ""
    m = RE_OK.search(head)
    if m:
        return "設計固有", [f"copy: ok {m.group(1).strip()}"]
    d = subprocess.run(["diff", "-u", apr_path, design_path],
                       capture_output=True, text=True).stdout.splitlines()
    add = [l[1:] for l in d if l.startswith("+") and not l.startswith("+++")]
    code = [l for l in add
            if l.strip() and not l.strip().startswith(("#", "*", '"""', "'''"))]
    body = "\n".join(code)
    return ("設計固有" if any(m in body for m in MARKS) else "古いだけ"), code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="+")
    ap.add_argument("--list", choices=KINDS, help="その種別だけ一覧する")
    ap.add_argument("--strict", action="store_true",
                    help="「古いだけ」が 1 本でもあれば 1 で終わる")
    a = ap.parse_args()

    apr = {os.path.basename(f): os.path.join(APR_ROOT, f)
           for f in tracked(APR_ROOT) if f.startswith("apr/") and f.endswith(".py")}
    print(f"正本: {APR_ROOT}/apr（{len(apr)} 本）")
    print()
    total = {k: 0 for k in KINDS}
    stale_all = []
    for root in a.designs:
        files = [f for f in tracked(root)
                 if f.startswith("scripts/") and f.endswith(".py")
                 and os.path.basename(f) in apr]
        ci = ci_called(root, files)
        rows = []
        for f in sorted(files):
            kind, code = ("CI", []) if f in ci else classify(
                os.path.join(root, f), apr[os.path.basename(f)])
            rows.append((kind, f, code))
            total[kind] += 1
            if kind == "古いだけ":
                stale_all.append((root, f))
        name = os.path.basename(os.path.abspath(root))
        cnt = {k: sum(1 for r in rows if r[0] == k) for k in KINDS}
        print(f"{name:<20} 同名 {len(files):>3} 本  "
              + "  ".join(f"{k} {cnt[k]}" for k in KINDS))
        for kind, f, code in rows:
            if a.list and kind != a.list:
                continue
            if a.list:
                print(f"    {f}")
                for l in code[:6]:
                    print(f"        + {l}")
        print()

    print("=" * 66)
    print("合計  " + "  ".join(f"{k} {total[k]}" for k in KINDS))
    print()
    if stale_all:
        print(f"★ **「古いだけ」が {len(stale_all)} 本ある。** これが事故の形"
              "（U89 / U14 で 2 度: APRtools で直したのに古い写しを呼んだ）:")
        for root, f in stale_all:
            print(f"    {os.path.basename(os.path.abspath(root))}/{f}")
        print("  -> 呼び先を `$APRTOOLS/apr/` に向けて消す。"
              "`--list 古いだけ` で設計側にしか無い行を見る")
    else:
        print("★ **「古いだけ」は 0 本。** 残っているのは残す理由があるもの"
              "（CI / 移植の監査証跡 / 本当に設計固有）。")
    print()
    print("  同一 … いまは無害だが、APRtools を直した日に「古いだけ」へ落ちる。見張る対象")
    print("  CI   … `.github/workflows/` が呼ぶ。CI にはその設計しか無いので残すのが正しい")
    return 1 if (a.strict and stale_all) else 0


if __name__ == "__main__":
    raise SystemExit(main())

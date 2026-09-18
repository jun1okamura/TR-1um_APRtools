#!/usr/bin/env python3
"""台帳（`docs/90_improvement_notes.md` + `docs/92_closed.md`）の整合を見る。

  usage: python3 $APRTOOLS/apr/check_ledger.py

なぜ要るか:
  台帳は**状態を 2 箇所に書いていた** — §7-1 の索引と、各項目の本文の
  `**状態**:` 行。表だけ直して本文を直し忘れ、**2026-09-18 に 8 件
  食い違っていた**（U32 / U43 / U73 / U93 / U94 / U96 / U97 / U99）。
  `set_load 36.2`（U99）や `min_pulse_width`（U99）と**同じ形**が、
  道具ではなく文書の側に残っていた。

  ★ **正本は索引ひとつ。** 本文（決着分は `92_closed.md`）は
  「何が起きて、どう直して、何を学んだか」だけを持つ。
  この道具はその決まりを機械で守る。

見るもの:
  1. 索引の行と本文の節が**1 対 1**か（片方にしか無い U 番号が無いか）
  2. 索引に**同じ U 番号が 2 行**無いか
  3. 本文に `**状態**:` が**残っていない**か（状態は索引にしか書かない）
  4. 取り消し線（`~~`）が無いか（機械で数えられない状態表現。2026-09-16 の決着）
  5. 決着した項目の本文が `92_closed.md` に、開いている項目が
     `90_improvement_notes.md` にあるか（置き場が状態と合っているか）
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# lint: ok docs/ は apr/ の外。台帳を見るのがこの道具の仕事
DOCS = os.path.join(os.path.dirname(HERE), "docs")
OPEN_DOC = "90_improvement_notes.md"
CLOSED_DOC = "92_closed.md"

RE_ROW = re.compile(r"^\|\s*(U\d+)\s*\|([^|]*)\|([^|]*)\|")
RE_SEC = re.compile(r"^#### (U\d+)")
RE_STATE = re.compile(r"^\*\*状態\*\*\s*:")


def read(name):
    p = os.path.join(DOCS, name)
    if not os.path.exists(p):
        raise SystemExit(f"** {p} が無い")
    return open(p, encoding="utf-8").read().split("\n")


def closed(status):
    s = status.replace("*", "").strip()
    return s.startswith("決着") or s.startswith("取り下げ")


def main():
    op, cl = read(OPEN_DOC), read(CLOSED_DOC)
    ng = []

    index, dup = {}, []
    for l in op:
        m = RE_ROW.match(l)
        if m:
            u = m.group(1)
            if u in index:
                dup.append(u)
            index.setdefault(u, m.group(3).strip())

    sec_open = [m.group(1) for m in (RE_SEC.match(l) for l in op) if m]
    sec_closed = [m.group(1) for m in (RE_SEC.match(l) for l in cl) if m]
    secs = set(sec_open) | set(sec_closed)

    print(f"索引 {len(index)} 行 / 本文 {len(secs)} 節"
          f"（開 {len(set(sec_open))} + 決着 {len(set(sec_closed))}）")

    if dup:
        ng.append(f"索引に同じ番号が 2 行以上: {sorted(set(dup))}")
    only_idx = sorted(set(index) - secs, key=lambda x: int(x[1:]))
    only_sec = sorted(secs - set(index), key=lambda x: int(x[1:]))
    if only_idx:
        ng.append(f"索引にあるが本文が無い: {only_idx}")
    if only_sec:
        ng.append(f"本文にあるが索引に無い: {only_sec}")

    for name, lines in ((OPEN_DOC, op), (CLOSED_DOC, cl)):
        n = sum(1 for l in lines if RE_STATE.match(l))
        if n:
            ng.append(f"{name} に `**状態**:` が {n} 行ある"
                      "（状態は索引にしか書かない。2 箇所に書くと必ずずれる）")
        n = sum(l.count("~~") for l in lines)
        if n:
            ng.append(f"{name} に取り消し線が {n} 個ある"
                      "（機械で数えられない。状態は索引の文字で表す）")

    # 置き場と状態が合っているか
    for u, st in sorted(index.items(), key=lambda kv: int(kv[0][1:])):
        want = CLOSED_DOC if closed(st) else OPEN_DOC
        where = CLOSED_DOC if u in sec_closed else OPEN_DOC
        if u in secs and want != where:
            ng.append(f"{u} は「{st}」なのに本文が {where} にある（{want} が正しい）")

    print()
    if ng:
        print(f"判定: **要確認 {len(ng)} 件**")
        for x in ng:
            print(f"  ** {x}")
        return 1
    print("判定: OK — 索引と本文が 1 対 1、状態は索引だけにある")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

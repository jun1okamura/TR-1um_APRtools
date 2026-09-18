#!/usr/bin/env python3
"""追跡ファイルに**個人のホームパス**が入っていないかを数える（U35 / U93）。

  usage: python3 apr/check_no_home_paths.py [<リポジトリ> ...]
         python3 apr/check_no_home_paths.py --pattern 98_LSI_Design ...

引数を省くと**カレントのリポジトリ**を見る。

なぜ要るか:
  U35 で「4 リポジトリとも追跡ファイル 0 件」と書いたが、**数えたのが
  ドキュメントとスクリプトだけ**で、特性化デッキ（TD4 14,248 / I2C 140）を
  見ていなかった（U93）。**「0 件になった」と書くなら、何を数えたかも
  言えるようにしておく。** この道具がその「何を」を固定する。

数えるもの:
  `git ls-files` が返す**追跡ファイル全部**（テキストのみ。バイナリは飛ばす）。
  既定の網は次の 3 つで、`--pattern` で足せる:

    /Users/<誰か>/   … macOS のホーム
    /home/<誰か>/    … Linux のホーム（`/home/runner` のような CI は除く）
    /sessions/       … このクラウドの作業場（この行は path-ok）

  ★ **凍結物は対象外**（`legacy/` と `reference/`）。当時の記録なので
    書き換えない（U35 の決着）。

  ★ **`path-ok` と書いた行は数えない。** 「この問題そのものを説明している
    文書やコード」— 検査の網の定義、台帳の経緯、`docs` の注意書き — は
    パスを**引用**する必要がある。`lint.py` の `lint: ok` と同じ逃がし方。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# 既定の網。**ユーザ名を含む**ホーム配下と、機械固有の作業場。
# lint: ok この道具の検査対象そのもの。`foreign-path` の網の定義と同じ理由
DEFAULT = (r"/Users/[A-Za-z0-9._-]+/", r"/home/(?!runner/)[A-Za-z0-9._-]+/",  # path-ok
           # lint: ok この道具の検査対象そのもの
           r"/sessions/")  # path-ok
FROZEN = ("legacy/", "reference/")


def tracked(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"** git リポジトリではない: {root}\n{out.stderr.strip()}")
    return [f for f in out.stdout.split("\0") if f]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*", default=["."])
    ap.add_argument("--pattern", action="append", default=[],
                    help="足したい正規表現（既定に加える）")
    ap.add_argument("--all", action="store_true",
                    help="凍結物（legacy/ reference/）も見る")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    rx = re.compile("|".join(DEFAULT + tuple(a.pattern)))
    print("見る網:", " / ".join(DEFAULT + tuple(a.pattern)))
    print("対象外:", "（なし）" if a.all else " ".join(FROZEN))
    print()
    ng = 0
    for root in (a.repos or ["."]):
        files = tracked(root)
        skipped = hit = 0
        rows = []
        for f in files:
            if not a.all and f.startswith(FROZEN):
                skipped += 1
                continue
            p = os.path.join(root, f)
            try:
                with open(p, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            if b"\0" in raw[:8000]:            # バイナリ
                continue
            s = raw.decode("utf-8", "replace")
            # `path-ok` の行は「問題そのものを説明している」行なので数えない。
            n = sum(len(rx.findall(ln)) for ln in s.splitlines()
                    if "path-ok" not in ln)
            if n:
                hit += 1
                rows.append((n, f))
        name = os.path.basename(os.path.abspath(root))
        print(f"{name:<22} 追跡 {len(files):>6} 本 "
              f"（凍結 {skipped} 本を除く）  -> **{hit} 件**")
        for n, f in sorted(rows, reverse=True)[:20 if a.verbose else 5]:
            print(f"    {n:>5} 箇所  {f}")
        if len(rows) > (20 if a.verbose else 5):
            print(f"    … 他 {len(rows) - (20 if a.verbose else 5)} 本")
        ng += hit
    print()
    print("結果: 個人のホームパスを含む追跡ファイルは **0 件**" if ng == 0
          else f"結果: **{ng} 件**。生成物なら追跡をやめる、記録なら凍結物へ移す")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())

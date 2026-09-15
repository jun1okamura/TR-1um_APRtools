#!/usr/bin/env python3
"""lint.py -- APRtools の「パスと名前」を静的に検査する。

  usage: python3 apr/lint.py [ディレクトリ...] [--warn-only] [-v]

## なぜこれが要るか

`TR-1um_I2C_2026` を APRtools へ移す作業で壊れたのは **7 件、全部
「パスと名前」**だった（`docs/06_verify_migration.md` §5-d）。回路の話は
1 件も無い:

| 壊れ方 | 例 |
|---|---|
| `apr/` の外を見る相対パス | `gen_chip_sim_ready.py` が `../klayout_extract.py` |
| 移動したディレクトリの直書き | `place_logo.py` が `cfg.ROOT/lef/opensusi_logo.txt` |
| 電源名の写像漏れ | `POWER_NETS = {"VDD","GND"}` にコアの `vdd`/`vss` が無い |
| 生成物に機械依存のパス | `セル定義 : ../apr_root/stdcell/...` |
| 既定値が誰も読まない場所 | `mklvsnet` は landscape/、`mkchipnet` は chip/ |

**どれも実行して初めて分かった。** TD4 / SCLK_SPI でも同じ場所を踏むので、
先に機械で洗う。

## 方針 — 「ノイズを出すリンタは 2 回目に誰も回さない」

検査を**具体的に**する。「電源名の文字列」を全部挙げると 121 件出て、その
大半は正しい（チップ側のレール名は意図して大文字。`docs/04_naming.md`
§1-5 / U21）。だから**壊れ方そのものの形**だけを見る。

例外は行末の `# lint: ok <理由>` で消す（**理由を書かせる**。複数行の
リテラルは先頭行か直前行に書く）。

## 検査

| id | 重さ | 何を見るか |
|---|---|---|
| `escape-apr` | NG | `apr/` の外を見ている。(a) `os.path.dirname(HERE)` (b) **APRtools のルート + 設計側にしか無いディレクトリ**（`out/` `layout/` `src/` `lef/` …）|
| `moved-dir` | NG | `cfg.ROOT` + APRtools へ移したディレクトリ名 |
| `baked-path` | NG | `os.path.relpath(x, cfg.ROOT)` が `print` の外（生成物に焼き付く）→ `cfg.disp()` |
| `env-direct` | NG | `os.environ` で**外部ツール以外**を読む |
| `env-knob` | warn | `os.environ` で `APR_*` を直読み → `config_base.getenv()` へ |
| `rail-map` | warn | `VDD` と `GND`/`VSS` を鍵にする辞書で `rules.` を参照していない |
| `file-table` | NG | `apr/*.py` と `apr/README.md` の分類表が食い違っている |
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys

# APRtools 側に移したディレクトリ。設計の `cfg.ROOT` の下を指していたら移行漏れ。
# `lef` は設計にも残る（フレームは PDK 由来でコピーしない）ので warn 扱いの
# 対象にはするが、STDCELL の写しを指していたら本当の漏れ。
MOVED = ("stdcell", "art", "macro", "syn", "char")
MOVED_SOFT = ("lef",)

# ★ **APRtools のルートの下には無い**ディレクトリ。設計リポジトリ側にしかない。
#   `ROOT = os.path.dirname(os.path.dirname(__file__))` で APRtools の根を取って
#   その下を指すコードが 3 本あり、**どれも実行すれば必ず落ちていた**:
#     gate_count.py           <APRtools>/lef/cell_info.json  （U52。履歴に一度も無い）
#     dedup_gates.py          <APRtools>/out/*.v
#     merge_muxdffrb_rslatch  <APRtools>/out/*.v
#   読み手が居ないので誰も気づかない（決定 21）。設計側は `cfg.*` で取る。
DESIGN_ONLY_DIRS = ("out", "layout", "src", "lef", "hdl", "ngspice", "reference")

# 外部ツールの環境変数。これは `getenv()`（`APR_` 前置）の対象ではない。
EXTERNAL_ENV = {
    "KLAYOUT", "TR1UM_PDK", "YOSYS", "XSCHEM", "NGSPICE", "IRSIM",
    "PYTHONHASHSEED", "GITHUB_OUTPUT", "GITHUB_ENV", "PATH", "HOME",
    "APR_DESIGN_ROOT",          # apr_path.py が読む。config より前に要る
}

PWR_HI = {"VDD", "VCC"}
PWR_LO = {"GND", "VSS"}

SKIP_DIRS = {"__pycache__", "legacy", ".git"}
# 自分自身と、規約そのものを定義している側は対象外
SKIP_FILES = {"lint.py", "config_base.py"}


class Finding:
    def __init__(self, sev, cid, path, line, text, hint):
        self.sev, self.cid, self.path = sev, cid, path
        self.line, self.text, self.hint = line, text, hint


def waived(lines, lineno):
    """その行、または直前の行に `# lint: ok` があるか。"""
    for i in (lineno - 1, lineno - 2):
        if 0 <= i < len(lines) and "# lint: ok" in lines[i]:
            return True
    return False


def seg(src, node):
    try:
        return (ast.get_source_segment(src, node) or "").strip()
    except Exception:
        return ""


def _is_environ(node):
    """`os.environ` / `_os.environ` か。"""
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def env_key(node):
    """`os.environ.get("X", …)` / `os.environ["X"]` の "X" を返す。

    環境そのものを渡すだけの `{**os.environ, …}` は None（指摘しない）。
    名前が定数で書かれていない場合も None。"""
    # os.environ.get("X")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and _is_environ(node.func.value):
        a = node.args[0] if node.args else None
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            return a.value
        # `os.environ.get("APR_" + k)` のような組み立ては前置だけ見る
        if isinstance(a, ast.BinOp) and isinstance(a.left, ast.Constant) \
                and isinstance(a.left.value, str):
            return a.left.value
        return None
    # os.environ["X"]
    if isinstance(node, ast.Subscript) and _is_environ(node.value):
        s = node.slice
        if isinstance(s, ast.Constant) and isinstance(s.value, str):
            return s.value
    return None


def enclosing_src(src, tree, node):
    """node を含む関数（無ければモジュール）のソース。"""
    best = None
    for f in ast.walk(tree):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if getattr(f, "lineno", 0) <= node.lineno <= getattr(f, "end_lineno", 0):
                if best is None or f.lineno > best.lineno:
                    best = f
    return seg(src, best) if best else src


def check_file(path):
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Finding("NG", "syntax", path, e.lineno or 1, str(e), "構文エラー")]
    out = []

    def add(sev, cid, node, text, hint):
        ln = getattr(node, "lineno", 1)
        if waived(lines, ln):
            return
        out.append(Finding(sev, cid, path, ln, text, hint))

    # print(...) の中に入っているノードを覚えておく（ログは焼き付かない）
    in_print = set()
    for nd in ast.walk(tree):
        if isinstance(nd, ast.Call) and isinstance(nd.func, ast.Name) \
                and nd.func.id == "print":
            for sub in ast.walk(nd):
                in_print.add(id(sub))

    # `X = os.path.dirname(os.path.dirname(...__file__...))` は APRtools の根。
    # ★ `os.path` 形と `pathlib` 形の両方を拾う。`dedup_gates.py` は
    #   `pathlib.Path(__file__).resolve().parent.parent` を 2 段の代入で
    #   書いていたので、`os.path.join` だけ見ていた版では素通りした。
    apr_dir_names, apr_root_names = set(), set()
    for nd in ast.walk(tree):
        if not (isinstance(nd, ast.Assign) and len(nd.targets) == 1
                and isinstance(nd.targets[0], ast.Name)):
            continue
        name = nd.targets[0].id
        v = seg(src, nd.value).replace(" ", "")
        if "__file__" in v:
            if v.startswith("os.path.dirname(os.path.dirname("):
                apr_root_names.add(name)          # APRtools の根
            elif v.endswith(".parent") or v.startswith("os.path.dirname("):
                apr_dir_names.add(name)           # apr/ 自身
        else:
            base = v[:-len(".parent")] if v.endswith(".parent") else None
            if base in apr_dir_names:
                apr_root_names.add(name)          # apr/ の親 = APRtools の根

    _inner_div = set()
    for nd in ast.walk(tree):
        # --- escape-apr / moved-dir / baked-path / env-* ---
        # (b') pathlib 形: <APRtools の根> / "out" / ...
        #   `a / "out" / "x.v"` は BinOp が入れ子になるので、**外側 1 つだけ**
        #   報告する（内側も拾うと 1 行が 2 件になる）。
        if isinstance(nd, ast.BinOp) and isinstance(nd.op, ast.Div) \
                and id(nd) not in _inner_div:
            for _sub in ast.walk(nd):
                if _sub is not nd and isinstance(_sub, ast.BinOp) \
                        and isinstance(_sub.op, ast.Div):
                    _inner_div.add(id(_sub))
            root = nd
            while isinstance(root, ast.BinOp) and isinstance(root.op, ast.Div):
                root = root.left
            if isinstance(root, ast.Name) and root.id in apr_root_names:
                t = seg(src, nd)
                for d in DESIGN_ONLY_DIRS:
                    if f'"{d}"' in t or f"'{d}'" in t:
                        add("NG", "escape-apr", nd, t,
                            f"`{d}/` は APRtools のルートの下には無い（設計側にある）。"
                            f"cfg の導出値を使う。ここは実行すれば必ず落ちる")
                        break
        if isinstance(nd, ast.Call):
            s = seg(src, nd)
            if s.startswith("os.path.dirname(HERE)"):
                add("NG", "escape-apr", nd, s,
                    "apr/ の外を見ている。同じ apr/ の中なら os.path.join(HERE, …)")
            # (b) APRtools の根 + 設計側にしか無いディレクトリ（os.path 形）
            if s.startswith("os.path.join") and nd.args:
                first = seg(src, nd.args[0])
                if first in apr_root_names:
                    for d in DESIGN_ONLY_DIRS:
                        if f'"{d}"' in s or f"'{d}'" in s or f'"{d}/' in s or f"'{d}/" in s:
                            add("NG", "escape-apr", nd, s,
                                f"`{d}/` は APRtools のルートの下には無い（設計側にある）。"
                                f"cfg の導出値を使う。ここは実行すれば必ず落ちる")
                            break
            if s.startswith("os.path.join") and "cfg.ROOT" in s:
                for d in MOVED:
                    if f'"{d}"' in s or f"'{d}'" in s:
                        add("NG", "moved-dir", nd, s,
                            f"`{d}/` は APRtools 側。cfg の導出値"
                            f"（LIB_LEF / LOGO_BITMAP / stdcell_dir() …）を使う")
                        break
                else:
                    for d in MOVED_SOFT:
                        if f'"{d}"' in s or f"'{d}'" in s:
                            add("warn", "moved-dir", nd, s,
                                f"`{d}/` は設計にも残るが、STDCELL の写しを"
                                f"指していないか確認する")
                            break
            if s.startswith("os.path.relpath") and "cfg.ROOT" in s \
                    and id(nd) not in in_print:
                add("NG", "baked-path", nd, s,
                    "生成物に実行した機械の置き方が焼き付く。cfg.disp() を使う")

        # --- os.environ の直読み ---
        # ★ 変数名は **AST から取る**。行を引用符で split すると、同じ行の
        #   別の文字列（`ap.add_argument("--ys", default=os.environ.get("YOSYS"))`
        #   の `--ys`）を掴んで嘘の指摘になる。最初に書いたときそうなった。
        name = env_key(nd)
        if name is not None:
            parent = (lines[nd.lineno - 1] if nd.lineno - 1 < len(lines) else "").strip()
            if name in EXTERNAL_ENV or name.startswith("XSCHEM"):
                continue
            if name.startswith("APR_"):
                add("warn", "env-knob", nd, parent,
                    "config_base.getenv() 経由にする（変数名の一覧が 1 箇所に集まる）")
            else:
                add("NG", "env-direct", nd, parent,
                    f"外部ツール以外の環境変数 {name!r} を直読みしている")

        # --- rail-map: VDD と GND/VSS を鍵にする辞書 ---
        if isinstance(nd, (ast.Dict, ast.Set, ast.List, ast.Tuple)):
            keys = nd.keys if isinstance(nd, ast.Dict) else nd.elts
            vals = {k.value for k in keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if (vals & PWR_HI) and (vals & PWR_LO) and not (vals & {"vdd", "vss"}):
                if "rules." not in enclosing_src(src, tree, nd):
                    add("warn", "rail-map", nd, seg(src, nd).replace("\n", " ")[:88],
                        "コアのラベルは rules.PWR_NET / GND_NET（小文字）。"
                        "境界で写像しているか確認する（U21）")
    return out


# ---- file-table -----------------------------------------------------------
# `apr/README.md` の分類表が `apr/*.py` の実体と一致しているか。
# 決定 20「表・台帳は 1 箇所」。**表に載っていないファイルは地図から消える**ので、
# 足したら 1 行足させる。`ENV_KNOBS` を台帳にしたのと同じ形（U29）。
TABLE_ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)\.py`\s*\|")


def check_file_table(apr_dir):
    """apr/README.md の分類表と apr/*.py を突き合わせる。"""
    readme = os.path.join(apr_dir, "README.md")
    if not os.path.exists(readme):
        return [Finding("NG", "file-table", readme, 1, "apr/README.md が無い",
                        "`apr/` の地図。91 本の分類表を置く場所")]
    listed, dup, out = {}, [], []
    for i, line in enumerate(io.open(readme, encoding="utf-8"), 1):
        m = TABLE_ROW.match(line)
        if not m:
            continue
        if m.group(1) in listed:
            dup.append((m.group(1), i))
        else:
            listed[m.group(1)] = i
    actual = {f[:-3] for f in os.listdir(apr_dir)
              if f.endswith(".py") and f not in SKIP_FILES} | {"lint", "config_base"}
    for name in sorted(actual - set(listed)):
        out.append(Finding(
            "NG", "file-table", os.path.join(apr_dir, name + ".py"), 1,
            f"{name}.py が apr/README.md の分類表に無い",
            "README の A〜K のどれかに 1 行足す（どの群か分からないなら K）"))
    for name in sorted(set(listed) - actual):
        out.append(Finding(
            "NG", "file-table", readme, listed[name],
            f"表に `{name}.py` があるが実体が無い",
            "消したのなら表からも消す"))
    for name, i in dup:
        out.append(Finding("NG", "file-table", readme, i,
                           f"`{name}.py` が表に 2 回出ている", "1 本は 1 行だけ"))
    return out


def walk(roots):
    for r in roots:
        if os.path.isfile(r):
            yield r
            continue
        for dp, dn, fn in os.walk(r):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in sorted(fn):
                if f.endswith(".py") and f not in SKIP_FILES:
                    yield os.path.join(dp, f)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*",
                    default=[here, os.path.join(os.path.dirname(here), "macro")],
                    help="既定: apr/ と macro/")
    ap.add_argument("--warn-only", action="store_true",
                    help="NG があっても 0 で終わる")
    ap.add_argument("-v", "--verbose", action="store_true", help="warn も全部出す")
    a = ap.parse_args()

    found, n_files = [], 0
    for p in walk(a.roots):
        n_files += 1
        found += check_file(p)
    # 台帳の検査は 1 回だけ（ファイルごとではない）
    if any(os.path.abspath(r) == here for r in a.roots):
        found += check_file_table(here)

    ng = [f for f in found if f.sev == "NG"]
    warn = [f for f in found if f.sev == "warn"]
    base = os.path.dirname(here)

    def show(items):
        for f in sorted(items, key=lambda x: (x.cid, x.path, x.line)):
            rel = os.path.relpath(f.path, base)
            print(f"  [{f.sev:4}] {f.cid:<11} {rel}:{f.line}")
            print(f"           {f.text[:96]}")
            print(f"           -> {f.hint}")

    print(f"lint: {n_files} ファイル")
    if ng:
        print(f"\n--- NG {len(ng)} 件 ---")
        show(ng)
    if warn and (a.verbose or not ng):
        print(f"\n--- warn {len(warn)} 件（要確認。直すか `# lint: ok 理由` を書く）---")
        show(warn)
    elif warn:
        cats = sorted({f.cid for f in warn})
        print(f"\nwarn {len(warn)} 件（{', '.join(cats)}）。-v で出す。")
    if not ng and not warn:
        print("  ok  指摘なし")
    elif not ng:
        print("\n  ok  NG なし")
    # 機械が読む 1 行（selfcheck.py がこれを拾う）
    print(f"SUMMARY NG={len(ng)} warn={len(warn)} files={n_files}")
    return 1 if (ng and not a.warn_only) else 0


if __name__ == "__main__":
    sys.exit(main())

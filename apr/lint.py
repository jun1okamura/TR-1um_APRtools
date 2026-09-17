#!/usr/bin/env python3
"""lint.py -- APRtools の「パスと名前」を静的に検査する。

  usage: python3 apr/lint.py [ディレクトリ...] [--warn-only] [-v]

既定で見るのは `apr/` `macro/` `char/`。`legacy/` は凍結なので対象外、
`templates/` は**設計側の `config.py` の見本**（`ROOT` が設計の根を指す）
なので対象外。

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
| `baked-path` | NG | `os.path.relpath(x, cfg.ROOT)` — **場所を問わず**。生成物なら `cfg.disp()`、画面なら `cfg.show()` |
| `env-direct` | NG | `os.environ` で**外部ツール以外**を読む |
| `env-knob` | warn | `os.environ` で `APR_*` を直読み → `config_base.getenv()` へ |
| `rail-map` | warn | `VDD` と `GND`/`VSS` を鍵にする辞書で `rules.` を参照していない |
| `file-table` | NG | `apr/*.py` と `apr/README.md` の分類表が食い違っている |
| `design-knob` | NG | **設計が上書きできる値**（`ENV_KNOBS` ∩ `rules`）を `rules.` から直読み → `cfg.` から取る |
| `drc-const` | NG | プロセス定数の写し。(a) `M1_*` / `M2_*` / `V1_*` … への**数値リテラル代入** (b) **argparse の既定**に書かれた同じもの |
| `foreign-path` | NG | **別の機械の絶対パス**が文字列リテラルに入っている（`/home/…` `/Users/…` `/sessions/…` `/var/folders/…` `/opt/homebrew/…`）|

`--constants` を付けると、**`rules.py` の「まるくない」値と一致する数値リテラル**を
全部並べる（合否には関係しない。`docs/90_improvement_notes.md` U62 の作業リスト）。
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

# ★ プロセス定数を写した名前。**値は `rules.py` からしか取らない**（決定 11）。
#   以前は 8 ファイルが同じ値を持っていて、`drc_check_cells.py` の 3 つだけが
#   **緩い方へずれていた**（M1 幅 1.4 / M2 幅 1.8 / V1 間隔 1.4。U4）。
#   「いま全部合っている」ことは、次に誰かが写すのを止めない。
# ★ `WN_` は入れない。`macro/regfile/mkspice.py` の `WN_TLAT` は
#   **N ウェルではなく NMOS のチャネル幅**（W of N）で、名前だけが衝突する。
#   名前の形だけで決めると、こういう別物を巻き込む。
# argparse の引数名がこれを含むなら、数値の既定はプロセス定数の疑い。
ARG_GRID_NAME = re.compile(
    r"(pitch|offset|width|space|gap|cut|enc|track|site|row.?h|wire|trunk|grid)", re.I)

# `rules.py` の値のうち**まるくない**もの（偶然の一致が起きにくい）。
# まるい数は普通の定数としてよく出るので外す（`lw=1.0` のような別物を拾わない）。
_ROUND = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0, 45.0,
          64.0, 100.0, 1000.0, 0.001}


def _rules_distinct():
    import rules as _r
    out = {}
    for _k, _v in vars(_r).items():
        if _k.startswith("_") or isinstance(_v, bool) \
                or not isinstance(_v, (int, float)):
            continue
        _f = round(float(_v), 6)
        if _f not in _ROUND:
            out.setdefault(_f, _k)
    return out


RULES_DISTINCT = _rules_distinct()


def _design_knobs():
    """`config_base.ENV_KNOBS` と `rules` の両方にある名前。

    = **設計が上書きできて、しかも rules にも同名がある**もの。
    `rules.X` と書くと設計の値を素通りするので、読むなら `cfg.X`。
    """
    # ★ **例外を握り潰さない。** 最初 `except Exception: return set()` と書いたら
    #   `rules` が未 import（この lint は関数の中で import している）で
    #   `NameError` になり、**検査が 1 件も出ないまま「指摘なし」**になった。
    #   検査が空振りしていることは、結果が 0 件なのと見分けが付かない（U74）。
    import config_base as _cb
    import rules as _r
    ks = {n for n in _cb.ENV_KNOBS if n.isupper() and hasattr(_r, n)}
    if not ks:
        raise SystemExit("lint: design-knob の対象が 0 個。"
                         "config_base.ENV_KNOBS と rules の突き合わせが壊れている")
    return ks


DESIGN_KNOBS = _design_knobs()

# ★ **自分のホーム以外の機械のパス**。仮名化の作業（U35）は `/Users/<自分>` と
#   同期フォルダ名だけを探したので、**回した機械が別だった時期のパス**が残った:
#     char/genjobs.py      -o の既定が `/home/claude/char/pack`（クラウド側の作業場）
#     I2C の TB 2 本       `.include '/home/claude/work/.../ip62_models'`（= U24）
#     旧世代のスクリプト群  `/sessions/<セッション名>/mnt/...` を直書き
#   どれも**その機械以外では存在しないパス**で、既定値に入っていると
#   「回したら落ちる」までは気づかない（決定 21 と同じ届かなさ）。
#   凍結した `legacy/` は対象外（SKIP_DIRS）。記録としての言及はコメントに書く。
FOREIGN_PATH = re.compile(
    r"^/(home|Users|sessions|Volumes|var/folders|private/var|opt/homebrew)/")

DRC_NAME = re.compile(
    r"^(M1|M2|V1|GC|CO)_(W|S|WIDTH|SPACE|MIN|MAX|GAP|CUT|ENC|PAD|PITCH"
    r"|OFFSET|TRUNK|WIRE|SIZE)")

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
        # --- foreign-path ---
        if isinstance(nd, ast.Constant) and isinstance(nd.value, str) \
                and FOREIGN_PATH.match(nd.value):
            add("NG", "foreign-path", nd, nd.value.split()[0][:60],
                "別の機械の絶対パス。`cfg.ROOT` / `HERE` / 環境変数から組む")
        # --- escape-apr / moved-dir / baked-path / env-* ---
        # --- drc-const ---
        if isinstance(nd, ast.Assign) and nd in tree.body \
                and os.path.basename(path) != "rules.py":   # 正本は対象外
            tg = nd.targets[0]
            pairs = []
            if isinstance(tg, ast.Name):
                pairs = [(tg.id, nd.value)]
            elif isinstance(tg, ast.Tuple) and isinstance(nd.value, ast.Tuple) \
                    and len(tg.elts) == len(nd.value.elts):
                pairs = [(e.id, v) for e, v in zip(tg.elts, nd.value.elts)
                         if isinstance(e, ast.Name)]
            for _nm, _v in pairs:
                if DRC_NAME.match(_nm) and isinstance(_v, ast.Constant) \
                        and isinstance(_v.value, (int, float)) \
                        and not isinstance(_v.value, bool):
                    add("NG", "drc-const", nd, f"{_nm} = {_v.value}",
                        "プロセス定数を写している。`rules.py` を引く（決定 11）")

        # --- design-knob: 設計が上書きできる値を rules から直読み ---
        # ★ `config_base` は `getenv("X", rules.X)` で**設計が上書きできる値**を
        #   作る（`finalize` の `setdefault` で `config.py` から直に指定もできる）。
        #   それを `rules.X` で読むと、**設計が決めた値ではなくプロセスの既定**を
        #   使うことになり、同じ設計の中で 2 つの値が並び立つ（U5、2026-09-17。
        #   `route_channels` が 5.4、`CORE_WIDTH_UM` が設計の値、という状態に
        #   なりうるところだった）。
        #   ライブラリ側（設計が無い世界）の道具は `# lint: ok` で外す。
        if isinstance(nd, ast.Attribute) and isinstance(nd.value, ast.Name) \
                and nd.value.id == "rules" and nd.attr in DESIGN_KNOBS \
                and os.path.basename(path) not in ("rules.py", "config_base.py"):
            add("NG", "design-knob", nd, f"rules.{nd.attr}",
                f"`{nd.attr}` は設計が config.py で上書きできる値。"
                f"`cfg.{nd.attr}` から取る（U5 / 決定 22）。"
                f"設計に依らない道具なら `# lint: ok 理由` を書く")

        # --- drc-const (b): argparse の既定に書かれた写し ---
        # ★ (a) は**モジュール直下の代入しか見ない**ので、
        #   `ap.add_argument("--pitch", default=5.4)` を素通りしていた
        #   （`pin_grid_check.py` が実例。U26 で見つかった）。
        #   引数の名前は `--pitch` のように弱い手がかりなので、
        #   **名前の語彙**と**値が rules の「まるくない」定数と一致するか**の
        #   両方で見る。まるい数（1.0 / 2.0 / 45.0 …）は偶然が多いので外す。
        if isinstance(nd, ast.Call) and isinstance(nd.func, ast.Attribute) \
                and nd.func.attr == "add_argument" \
                and os.path.basename(path) != "rules.py":
            _opt = next((a.value for a in nd.args
                         if isinstance(a, ast.Constant) and isinstance(a.value, str)), "")
            _dv = next((k.value for k in nd.keywords if k.arg == "default"), None)
            if isinstance(_dv, ast.Constant) and isinstance(_dv.value, (int, float)) \
                    and not isinstance(_dv.value, bool):
                _v = round(float(_dv.value), 6)
                _why = None
                if ARG_GRID_NAME.search(_opt or ""):
                    _why = "引数名がグリッド / DRC の語彙"
                elif _v in RULES_DISTINCT:
                    _why = f"値が rules.{RULES_DISTINCT[_v]} と同じ"
                if _why:
                    add("NG", "drc-const", nd, f'{_opt} default={_dv.value}',
                        f"{_why}。既定は `rules.py` から取る（決定 11 / U26）")

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
            # ★ 以前は「`print` の外だけ」NG にしていた（生成物に焼き付くのが
            #   怖かったので）。だが `print` の中でも、設計の外にあるものは
            #   `../../../../../tmp/x.gds` と出て**読めない**（U58）。
            #   `disp()`（生成物用）と `show()`（画面用）が両方あるので、
            #   **場所を問わず** NG にする。
            if s.startswith("os.path.relpath") and "cfg.ROOT" in s:
                add("NG", "baked-path", nd, s,
                    "生成物に書くなら cfg.disp()、画面に出すなら cfg.show()")

        # --- os.environ の直読み ---
        # ★ 変数名は **AST から取る**。行を引用符で split すると、同じ行の
        #   別の文字列（`ap.add_argument("--ys", default=os.environ.get("YOSYS"))`
        #   の `--ys`）を掴んで嘘の指摘になる。最初に書いたときそうなった。
        name = env_key(nd)
        if name is not None:
            parent = (lines[nd.lineno - 1] if nd.lineno - 1 < len(lines) else "").strip()
            # ★ `TR1UM_*` は **PDK / セルライブラリの場所**を指す系統で、
            #   `APR_*` のノブとは別（`char/` の道具は `config.py` を持たない
            #   単体ツールとして Mac で回すので、こちらの前置を使う）。
            if name in EXTERNAL_ENV or name.startswith(("XSCHEM", "TR1UM_")):
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



# 図の道具は対象外（`lw=1.4` / `ms=3.4` は線幅と点サイズで、**たまたま**
# プロセス定数と同じ数なだけ。実測で 69 -> 52 件に減った）。
CONST_SKIP_FILES = ("plot_", "block_report.py", "mem_array_estimate.py")
# matplotlib の見た目のキーワード。ここに来る数字は寸法ではない。
PLOT_KWARGS = {"lw", "linewidth", "ms", "markersize", "alpha", "fontsize",
               "labelpad", "elinewidth", "capsize", "rotation", "dpi", "zorder"}


def report_constants(roots):
    """`rules.py` の「まるくない」値と一致する数値リテラルを全部並べる。

    **合否には関係しない**（`SUMMARY` にも入れない）。`drc-const` が NG に
    できるのは「名前で分かるもの」だけで、`RING_VIA = 6.8` のように
    **名前が違うだけの写し**は名前からは分からない。値で当たりを付けて
    人が見るための一覧。作業リストは `docs/90_improvement_notes.md` の U62。
    """
    found = []
    for path in walk(roots):
        base = os.path.basename(path)
        if base == "rules.py" or base.startswith(CONST_SKIP_FILES[0]) \
                or base in CONST_SKIP_FILES[1:]:
            continue
        src = io.open(path, encoding="utf-8").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        skip = set()
        for nd in ast.walk(tree):
            if isinstance(nd, ast.Call):
                for kw in nd.keywords:
                    if kw.arg in PLOT_KWARGS:
                        for sub in ast.walk(kw.value):
                            skip.add(id(sub))
        for nd in ast.walk(tree):
            if isinstance(nd, ast.Constant) and isinstance(nd.value, (int, float)) \
                    and not isinstance(nd.value, bool) and id(nd) not in skip:
                v = round(float(nd.value), 6)
                if v in RULES_DISTINCT:
                    found.append((path, nd.lineno, v, RULES_DISTINCT[v],
                                  lines[nd.lineno - 1].strip()[:60]))
    return found


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*",
                    default=[here,
                             os.path.join(os.path.dirname(here), "macro"),
                             os.path.join(os.path.dirname(here), "char")],
                    help="既定: apr/ と macro/ と char/")
    ap.add_argument("--warn-only", action="store_true",
                    help="NG があっても 0 で終わる")
    ap.add_argument("-v", "--verbose", action="store_true", help="warn も全部出す")
    ap.add_argument("--constants", action="store_true",
                    help="rules.py の値と一致する数値リテラルを並べる（合否に関係しない）")
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

    if a.constants:
        rows = report_constants(a.roots)
        print(f"\n--- rules.py の値と一致する数値リテラル {len(rows)} 箇所 ---")
        print("    （合否には関係しない。名前が違うだけの写しを人が見るための一覧）")
        cur = None
        for pth, ln, v, nm, text in sorted(rows):
            rel = os.path.relpath(pth, os.path.dirname(here))
            if rel != cur:
                cur = rel
                print(f"  {rel}")
            print(f"    {ln:5d}  {v:>8} = rules.{nm:<18} {text}")

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

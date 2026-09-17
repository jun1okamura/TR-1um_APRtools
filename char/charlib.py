#!/usr/bin/env python3
"""特性化の共通部品: デッキ組み立て / ngspice 実行 / アーク列挙。"""
from __future__ import annotations
import itertools, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_comb import (to_xm, ports_of, all_ports_of, CELLDIR, CELLEXT,
                        models_dir, models_include, need_ngspice)           # noqa: E402

# ---- STDCELL 正本の場所（**ここ 1 箇所**）-------------------------------
# ★ 同じ「stdcell/<版>/ の中を探す」を `mklib` / `verify_lib` / `check_pass` が
#   **3 通りに書いていた**（U37、2026-09-17）。`check_pass` のものは
#   `{HERE}/TR-1um_STDCELL.gds` と `{HERE}/../../lef/…` を見ていて、
#   **前者は存在せず、後者は APRtools の外**を指していた（どちらも当たらない）。
STDCELL_VER = os.environ.get("TR1UM_STDCELL", "v59_4")


def stdcell_dir():
    """STDCELL 正本の置き場 `<APRtools>/stdcell/<版>`。版は `TR1UM_STDCELL`。"""
    return os.path.normpath(os.path.join(HERE, "..", "stdcell", STDCELL_VER))


def stdcell_file(name, env=None, first=(), missing_ok=False):
    """正本の中の 1 ファイルを探す。

    `env`      … これで明示できる環境変数名（あれば最優先）
    `first`    … 正本より**先に**見る場所（`mklib` の出力先など）
    `missing_ok` … 見つからないとき `None` を返す（既定は読める形で止まる）
    """
    cands = [os.environ.get(env) if env else None]
    cands += list(first)
    cands.append(os.path.join(stdcell_dir(), name))
    for p in cands:
        if p and os.path.exists(p):
            return os.path.normpath(p)
    if missing_ok:
        return None
    raise SystemExit(
        f"{name} が見つからない。正本は stdcell/<版>/{name}。\n"
        f"  版は TR1UM_STDCELL（いま {STDCELL_VER}）"
        + (f"、場所は {env} で明示できる" if env else "") + "。\n"
        f"  試した場所: {[c for c in cands if c]}")


VDD = 5.0
TEMP = 25

# --- NLDM の格子 ---------------------------------------------------------
# 入力遷移時間 [ns]。TR-1um は 1µm・5V で INV の出力遷移が素で ~1ns なので、
# 0.1ns（ほぼ理想）から 16ns（かなり鈍った波形）までを対数的に取る。
SLEWS = [0.1, 0.25, 0.6, 1.5, 4.0, 8.0, 16.0]
# 出力負荷 [fF]。INV_X1 の入力容量が ~25fF なので、ファンアウト 0.5〜32 相当。
LOADS = [10, 25, 50, 100, 200, 400, 800]
# 制約（setup/hold）は格子を粗くする。1 点ごとに二分探索が要るため。
SLEWS_C = [0.25, 1.5, 8.0]

# --- セルごとに入力遷移の格子を変える ------------------------------------
# **BUFTH はシュミットトリガ**（ヒステリシス VT+ 3.71V / VT- 1.20V、幅 2.51V）。
# 外部入力を受けるためのセルなので、数百 ns の鈍い縁が来る。
# 既定の 16ns までの表から線形外挿すると**大きく外れる**:
#   遅延/遷移 の比は 16ns で 0.738 だが 1000ns では 0.392 に漸近する
#   （50% から VT+=74% まで travel するだけになるので 0.242/0.6 = 0.40 が下限）。
#   16ns の傾きで 1000ns を外挿すると 570ns、実測は 392ns。45% 過大。
# なので BUFTH だけ 1000ns まで測る。
CELL_SLEWS = {
    "BUFTH": [0.1, 0.6, 1.5, 4.0, 8.0, 16.0, 50.0, 150.0, 400.0, 1000.0],
}


def slews_of(cell):
    return CELL_SLEWS.get(cell, SLEWS)

# 測定しきい値 [%]
TH_DELAY = 50
TH_SLEW_LO, TH_SLEW_HI = 20, 80


# index_1 は **20-80% の遷移時間**（Liberty の slew_lower/upper_threshold_pct と同じ定義）。
# フルスイングの傾斜時間はその 1/0.6 倍になる。ここを合わせておかないと、
# 前段の rise_transition（20-80% で測っている）をそのまま次段の index_1 に
# 入れたときに辻褄が合わない。
SLEW_FRAC = (TH_SLEW_HI - TH_SLEW_LO) / 100      # = 0.6


def full_ramp(slew_ns):
    """20-80% の遷移時間 -> フルスイングの傾斜時間"""
    return slew_ns / SLEW_FRAC


def pwl_ramp(t0, slew_ns, rise):
    """t0 [ns] から、20-80% が slew_ns になる傾斜で 0->VDD / VDD->0 に振る PWL"""
    a, b = (0, VDD) if rise else (VDD, 0)
    tf = full_ramp(slew_ns)
    return f"PWL(0 {a:g} {t0:g}n {a:g} {t0+tf:g}n {b:g})"


# **ngspice は絶対に並列で走らせないこと。**
# このコンテナは 2 コアで、ngspice は 1 プロセスあたり 2 スレッド使う。
# 同じデッキ 2 本を計ると 逐次 2.0 秒 に対し **並列 99 秒**（50 倍）になる。
# OMP_NUM_THREADS=1 を渡してもスレッド数は減らず、効果がなかった。
# スレッドがコア数を超えるとバリアのスピン待ちで焼き切れているものと見られる。
# 1 本 0.7 秒で終わるので、逐次で十分速い（全セルで約 10 分）。
ENV1 = {**os.environ, "OMP_NUM_THREADS": "1", "NGSPICE_NUM_THREADS": "1"}
NPROC = 1


def run_ngspice(deck, tag, timeout=600):
    dpath = f"{HERE}/decks/{tag}.spi"
    open(dpath, "w").write(deck)
    need_ngspice()
    r = subprocess.run([os.environ.get("NGSPICE", "ngspice"), "-b", dpath], capture_output=True, text=True,
                       timeout=timeout, env=ENV1)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{tag}.log", "w").write(log)
    vals = {}
    for ln in log.splitlines():
        m = re.match(r"^\s*([a-z]\w*)\s*=\s*([-\d.eE+]+)", ln)
        if m:
            try: vals[m.group(1)] = float(m.group(2))
            except ValueError: pass
    return vals, log


def header(cell):
    return [models_include(), "",
            to_xm(f"{CELLDIR}/{cell}{CELLEXT}"), "",
            f".temp {TEMP}", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]


# --- アーク列挙 -----------------------------------------------------------
def arcs_of(cell, outs):
    """cellspec の真理値関数から (出力, 入力, 側入力の値, unate) を列挙する。

    入力 i について、他の入力をある値に固定したときに i を反転させると
    出力も変わる組合せ（= アークが立つ組合せ）を探す。
    見つかった組合せでの向きが unateness。両向きが存在すれば non_unate。
    """
    out = []
    for opin, (ipins, fn) in outs.items():
        for i, p in enumerate(ipins):
            others = [q for j, q in enumerate(ipins) if j != i]
            senses, side = set(), None
            for cb in itertools.product([0, 1], repeat=len(others)):
                env = dict(zip(others, cb))
                v = [0] * len(ipins)
                for j, q in enumerate(ipins):
                    v[j] = env.get(q, 0)
                v[i] = 0; y0 = fn(*v)
                v[i] = 1; y1 = fn(*v)
                if y0 == y1:
                    continue
                s = "positive_unate" if y1 > y0 else "negative_unate"
                senses.add(s)
                if side is None or (s == "positive_unate" and len(senses) > 1):
                    side = dict(env)
            if side is None:
                continue          # このピンは出力に効かない
            sense = senses.pop() if len(senses) == 1 else "non_unate"
            if sense == "non_unate":
                # XOR/XNOR。正極性側の枝で測って non_unate と申告する
                for cb in itertools.product([0, 1], repeat=len(others)):
                    env = dict(zip(others, cb))
                    v = [env.get(q, 0) for q in ipins]
                    v[i] = 0; y0 = fn(*v)
                    v[i] = 1; y1 = fn(*v)
                    if y1 > y0:
                        side = dict(env); break
            out.append((opin, p, side, sense))
    return out

#!/usr/bin/env python3
"""順序セルの特性化: CK->Q の遅延/遷移（7x7）、setup/hold、recovery/removal（3x3）。

  usage: python3 char_seq.py [セル名 ...]     結果は char/<cell>.json

setup / hold は 1 点ごとに**二分探索**が要る。データ端とクロック端の間隔を
詰めていき、「Q が正しい値を取り込める限界」を探す。判定は取り込み後の
Q の電圧（VDD/2 を跨いだか）で行う。格子は SLEWS_C（3 点）に落としてある。

**非同期ピンを持つセルは recovery / removal も測る**（U8、2026-09-17）。
動かすのは**解除する時刻**だけで、D は余裕をもって先に新値にしておく。

  recovery  解除がクロック端の **dt だけ前**。取り込めれば OK。
  removal   解除がクロック端の **dt だけ後**。効いたままなら OK。

どちらも「dt が大きいほど安全」なので、探索の向きは setup と同じ。
★ **取り込ませる値は「非同期ピンが作る値の逆」でなければ測れない**
  （`RSTB` は Q=0 を作るので 1 を、`SET` は Q=1 を作るので 0 を取り込ませる。
  同じ値だと「取り込めたのか、効いたままなのか」が区別できない）。
  効いたときの Q は `ASYNC_Q` に名前で持たせてあり、**知らない名前は止まる**。

★ **理由は設計ごとに違う。2026-09-16 に 3 設計を実際に見て確かめた**（U8）:

  TD4 / I2C   リセットは電源投入時に一度きり。クロックとの競合が起きないので
              `set_false_path -from rst_n` が正しく、recovery は要らない。

  SCLK_SPI    **前提が成り立たない。** `cnt_rstn = rstn & ~cs_n` は電源投入時
              だけでなく**フレームごとに `cs_n` の立下りで解除される**。
              最終ネットリストで確認: 20 個の FF のうち **4 個**
              （`bit_cnt[2:0]` と `msb_done`）が `RSTB=cnt_rstn`。
              解除から最初の `sclk` 取り込み端までは**半周期**（プロトコルの
              構造上そうなる。定格 36.35 MHz で 13.76 ns）。
              recovery がこれより短ければ安全だが、**測っていないので
              数字で言えない**。`STA_FALSE_PATH_FROM` に入れてあるうえ
              アークも無いので、**STA は何も見ていない**。

  -> `DFFRB` の recovery/removal を測れば「CS 立下りから最初の SCLK までに
     必要な時間」を数字で言える（データシートに書ける類の値）。
     **2026-09-17 に実装した。** 残りは測った数字を Liberty
     （`mklib.py` の `recovery_rising` / `removal_rising`）に載せる作業。
"""
from __future__ import annotations
import json, os, sys
import cellspec
from charlib import (HERE, VDD, SLEWS, LOADS, SLEWS_C, TH_DELAY, TH_SLEW_LO,
                     TH_SLEW_HI, header, ports_of, all_ports_of, run_ngspice, pwl_ramp,
                     full_ramp)

T_CK = 200.0        # クロック立上りの 50% 通過時刻 [ns]
SETTLE = 150.0

# セルごとの: データピン, 出力, 非同期ピン(非アクティブ値), 固定する入力
SEQ = {
    "DFF":      dict(d="D", q="Q", qb="QB", idle={}),
    "DFFRB":    dict(d="D", q="Q", qb="QB", idle={"RSTB": 1}),
    "DFFS":     dict(d="D", q="Q", qb="QB", idle={"SET": 0}),
    "MUXDFFRB": dict(d="A", q="Q", qb="QB", idle={"RSTB": 1, "S": 0, "B": 0}),
}


def ramp_at(t50, slew, rise):
    """50% 通過時刻が t50 になる PWL。slew は 20-80% の遷移時間。"""
    tf = full_ramp(slew)
    t0 = t50 - tf / 2
    a, b = (0, VDD) if rise else (VDD, 0)
    return f"PWL(0 {a:g} {t0:g}n {a:g} {t0+tf:g}n {b:g})"


T_PRE = 80.0        # 下地を作る 1 発目のクロック立上り [ns]
T_DSW = 140.0       # そのあとデータを目的の値に変える時刻 [ns]


def build_ckq(cell, spec, ck_slew, d_rise):
    """CK->Q の遅延と出力遷移。負荷 7 点を 1 デッキに並べる。

    **1 発目のクロックで Q を逆の値にしておく**こと。D を最初から目的の値に
    しておくと、DC 動作点でもう Q がその値になっていて、測るべき遷移が
    起きない（CK->Q の立下りが丸ごと測れなかった原因）。
    """
    ports = ports_of(cell)
    q, qb = spec["q"], spec["qb"]
    outs = {q, qb}
    L = [f"* {cell} CK->{q} clk遷移 {ck_slew}ns data={'1' if d_rise else '0'}"]
    L += header(cell)
    # D: 最初は逆の値 -> T_DSW で目的の値へ
    v0, v1 = (0, VDD) if d_rise else (VDD, 0)
    L.append(f"Vd {spec['d']} 0 PWL(0 {v0:g} {T_DSW:g}n {v0:g} {T_DSW+1:g}n {v1:g})")
    for p, v in spec["idle"].items():
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    # **KLayout の抽出は内部ネットもピンに昇格させる**（DFF の CKB/CKP/QM/QS）。
    # 0V で駆動するとフリップフロップが壊れるので、本当の入力ピンだけ固定する。
    real_in = (set(cellspec.SEQ_PINS[cell]["data"])
               | set(cellspec.SEQ_PINS[cell]["async"]) | {"CK"})
    for p in ports:
        if (p in real_in and p not in ("CK", spec["d"])
                and p not in spec["idle"] and p not in outs):
            L.append(f"V_{p} {p} 0 0")
    # 1 発目（T_PRE）で逆の値を取り込み、2 発目（T_CK）が測定対象
    tf = full_ramp(ck_slew)
    L.append(f"Vck CK_src 0 PWL(0 0 {T_PRE-1:g}n 0 {T_PRE:g}n {VDD:g} "
             f"{T_PRE+20:g}n {VDD:g} {T_PRE+21:g}n 0 "
             f"{T_CK-tf/2:g}n 0 {T_CK+tf/2:g}n {VDD:g})")
    # 理想源を急峻に振ると 7 インスタンスぶんのゲート容量でソルバが落ちる
    L.append("Rck CK_src CK 0.001")
    L.append("")
    for k, cl in enumerate(LOADS):
        pl = {p: (f"o{k}_{p}" if p in outs else p) for p in ports}
        L.append(f"X{k} " + " ".join(pl.get(p, p) for p in all_ports_of(cell)) + f" {cell}")
        L.append(f"C{k} o{k}_{q} 0 {cl}f")
        L.append(f"Cb{k} o{k}_{qb} 0 {cl}f")
    L.append("")
    L.append(f".tran {max(min(ck_slew,0.5)/20, 0.02):g}n {T_CK+full_ramp(ck_slew)+SETTLE:g}n")
    vt = VDD * TH_DELAY / 100
    lo, hi = VDD * TH_SLEW_LO / 100, VDD * TH_SLEW_HI / 100
    edge = "RISE=1" if d_rise else "FALL=1"
    for k in range(len(LOADS)):
        o = f"o{k}_{q}"
        # クロックは 2 発あるので RISE=2 が測定対象。Q の遷移も 2 回目。
        L.append(f".meas tran d{k} TRIG v(CK) VAL={vt:g} RISE=2 TARG v({o}) VAL={vt:g} "
                 f"{'RISE=1' if d_rise else 'FALL=1'}")
        if d_rise:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={lo:g} RISE=1 TARG v({o}) VAL={hi:g} RISE=1")
        else:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={hi:g} FALL=1 TARG v({o}) VAL={lo:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


HOLD_SETUP_MARGIN = 60.0   # hold 測定で setup 側に確保する余裕 [ns]
# recovery / removal で**クロックを下ろす**時刻（取り込み端から）[ns]（U8）。
# ★ setup / hold はクロックを上げっぱなしで測っている（下ろす必要が無い）。
#   だが非同期ピンの測定では**下ろさないと測れない**: この世代の `DFFRB` は
#   スレーブが CK 高で透過なので、CK を上げたままリセットを解除すると
#   **いつ解除しても Q が D になる**。境界が出ない（実測: recovery が探索の
#   下端 -20 に張り付き、removal は「一番緩くても保持できない」で `-`）。
# ★ **これは否定対照のつまみでもある。** 答えが `CK_HIGH` と一緒に動くなら、
#   それは「クロックが下りるまでリセットを保つ」という**波形の性質**であって
#   セルの定数ではない。動かなければセルの定数。`TR1UM_CK_HIGH` で振れる。
CK_HIGH = float(os.environ.get("TR1UM_CK_HIGH", 20.0))


def build_constraint(cell, spec, ck_slew, d_slew, d_rise, dt, mode="setup"):
    """クロック端に対するデータ端の位置を変えて、正しく取り込めるかを見る。

    **setup と hold は別の刺激が要る**（同じ波形で dt を動かすと、hold 側も
    setup と同じ境界を見つけてしまう。最初それで hold = -setup になっていた）。

      setup: D を t_ck - dt で「旧値 -> 新値」に変える。そのまま保持。
             dt を詰めていき、取り込める限界が setup 時間。
      hold : D を十分前（t_ck - 60ns）に新値へ変えて setup は満たしておき、
             **t_ck + dt で旧値へ戻す**。dt を詰めていき、新値を保持できる
             限界が hold 時間。
    """
    ports = ports_of(cell)
    q, qb = spec["q"], spec["qb"]
    outs = {q, qb}
    L = [f"* {cell} {mode} 探索 dt={dt}ns"]
    L += header(cell)
    v_old, v_new = (0, VDD) if d_rise else (VDD, 0)
    apin = async_pin(cell) if mode in ("recovery", "removal") else None
    if mode == "setup":
        t_d = T_CK - dt
        L.append(f"Vd {spec['d']} 0 {ramp_at(t_d, d_slew, d_rise)}")
    elif mode == "hold":
        t_in = T_CK - HOLD_SETUP_MARGIN          # 余裕をもって新値にする
        t_out = T_CK + dt                        # ここで旧値へ戻す
        L.append(f"Vd {spec['d']} 0 PWL(0 {v_old:g} "
                 f"{t_in-d_slew/2:g}n {v_old:g} {t_in+d_slew/2:g}n {v_new:g} "
                 f"{t_out-d_slew/2:g}n {v_new:g} {t_out+d_slew/2:g}n {v_old:g})")
    else:
        # recovery / removal（U8）。**D 側は余裕を持って新値にしておき**、
        # 動かすのは**非同期リセットを解除する時刻**だけにする。
        #   recovery: 解除がクロック端より dt だけ**前**。dt が小さいほど厳しい。
        #   removal : 解除がクロック端より dt だけ**後**。dt が小さいほど厳しい。
        # どちらも「dt が大きいほど安全」なので、探索は setup と同じ向き。
        t_in = T_CK - HOLD_SETUP_MARGIN
        L.append(f"Vd {spec['d']} 0 {ramp_at(t_in, d_slew, d_rise)}")
        idle = spec["idle"][apin]                # 解除しているときの値
        on, off = (1 - idle) * VDD, idle * VDD   # 効かせる / 解除する
        t_r = (T_CK - dt) if mode == "recovery" else (T_CK + dt)
        L.append(f"V_{apin} {apin} 0 PWL(0 {on:g} "
                 f"{t_r-d_slew/2:g}n {on:g} {t_r+d_slew/2:g}n {off:g})")
    for p, v in spec["idle"].items():
        if p == apin:
            continue                             # 上で PWL で駆動している
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    # **KLayout の抽出は内部ネットもピンに昇格させる**（DFF の CKB/CKP/QM/QS）。
    # 0V で駆動するとフリップフロップが壊れるので、本当の入力ピンだけ固定する。
    real_in = (set(cellspec.SEQ_PINS[cell]["data"])
               | set(cellspec.SEQ_PINS[cell]["async"]) | {"CK"})
    for p in ports:
        if (p in real_in and p not in ("CK", spec["d"])
                and p not in spec["idle"] and p not in outs):
            L.append(f"V_{p} {p} 0 0")
    # 取り込み前に Q を逆の値にしておく（1 発目のクロックで下地を作る）
    t_pre = T_CK - 120
    tf = full_ramp(ck_slew)
    ck = (f"PWL(0 0 {t_pre-20:g}n 0 {t_pre-19:g}n {VDD:g} "
          f"{t_pre:g}n {VDD:g} {t_pre+1:g}n 0 "
          f"{T_CK-tf/2:g}n 0 {T_CK+tf/2:g}n {VDD:g}")
    if mode in ("recovery", "removal"):
        t_fall = T_CK + CK_HIGH
        ck += f" {t_fall-tf/2:g}n {VDD:g} {t_fall+tf/2:g}n 0"
    L.append(f"Vck CK_src 0 {ck})")
    L.append("Rck CK_src CK 0.001")
    L.append("")
    L.append("XU " + " ".join(all_ports_of(cell)) + f" {cell}")
    L.append(f"C0 {q} 0 {LOADS[2]}f")
    L.append(f"C1 {qb} 0 {LOADS[2]}f")
    t_meas = T_CK + 100.0
    if mode in ("recovery", "removal"):
        # ★ 解除が遅いほど落ち着くのも遅い。**測る時刻は解除から十分後**、
        #   かつ**クロックを下ろしたあと**に取る（既定の T_CK+100 のままだと
        #   dt=80 のとき 20 ns しか空かない）。
        t_meas = max(t_meas, t_r + 60.0, T_CK + CK_HIGH + 60.0)
    L.append(f".tran 0.05n {t_meas+20:g}n")
    L.append(f".meas tran vq FIND v({q}) AT={t_meas:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def captures(cell, spec, ck_slew, d_slew, d_rise, dt, tag, mode="setup"):
    vals, _ = run_ngspice(
        build_constraint(cell, spec, ck_slew, d_slew, d_rise, dt, mode), tag)
    v = vals.get("vq")
    if v is None:
        return None
    return (v > VDD / 2) == bool(d_rise)


def bisect_setup(cell, spec, ck_slew, d_slew, d_rise, lo=-20.0, hi=60.0, n=8):
    """取り込める最小の dt（= setup 時間）。dt が小さいほど厳しい。"""
    tag = f"{cell}_st_{ck_slew}_{d_slew}_{int(d_rise)}"
    if not captures(cell, spec, ck_slew, d_slew, d_rise, hi, tag + "_hi"):
        return None                      # 一番緩い条件でも取り込めない
    if captures(cell, spec, ck_slew, d_slew, d_rise, lo, tag + "_lo"):
        return lo                        # 一番厳しい条件でも取り込める
    for i in range(n):
        mid = (lo + hi) / 2
        if captures(cell, spec, ck_slew, d_slew, d_rise, mid, f"{tag}_{i}"):
            hi = mid
        else:
            lo = mid
    return hi


def bisect_hold(cell, spec, ck_slew, d_slew, d_rise, lo=-20.0, hi=40.0, n=8):
    """クロック端の後、データを戻してよい最短時間（= hold）。

    dt が大きい（データを戻すのが遅い）ほど安全。詰めていって壊れる境界を探す。
    hold が負になることもある（クロックより前に戻しても間に合う = 余裕がある）。
    """
    tag = f"{cell}_hd_{ck_slew}_{d_slew}_{int(d_rise)}"
    if not captures(cell, spec, ck_slew, d_slew, d_rise, hi, tag + "_hi", "hold"):
        return None                      # 一番緩くても保持できない
    if captures(cell, spec, ck_slew, d_slew, d_rise, lo, tag + "_lo", "hold"):
        return lo                        # 一番厳しくても保持できる
    for i in range(n):
        mid = (lo + hi) / 2
        if captures(cell, spec, ck_slew, d_slew, d_rise, mid, f"{tag}_{i}", "hold"):
            hi = mid
        else:
            lo = mid
    return hi


# 非同期ピンが**効いているとき Q がどちらになるか**。recovery/removal は
# 「その逆の値を取り込ませて」はじめて「取り込めたのか、効いたままなのか」が
# 分かれる。★ 知らない名前は**黙って決めつけない**で止める。
ASYNC_Q = {"RSTB": 0, "SET": 1}


def async_pin(cell):
    """そのセルの非同期ピン（`RSTB` / `SET`）。無ければ `None`。"""
    a = cellspec.SEQ_PINS[cell]["async"]
    return a[0] if a else None


def async_dir(cell):
    """recovery/removal で使うデータの向き（`True` = 1 を取り込ませる）。

    リセットが Q=0 を作るセルなら 1 を、セットが Q=1 を作るセルなら 0 を
    取り込ませる。**同じ値だと区別がつかない。**
    """
    a = async_pin(cell)
    if a not in ASYNC_Q:
        raise SystemExit(f"{cell}: 非同期ピン {a!r} が効いたときの Q を知らない。"
                         f"`char_seq.ASYNC_Q` に足すこと")
    return ASYNC_Q[a] == 0


def holds_reset(cell, spec, ck_slew, d_slew, d_rise, dt, tag, mode):
    """`captures` の裏返し。**非同期ピンが効いたまま**なら True。"""
    c = captures(cell, spec, ck_slew, d_slew, d_rise, dt, tag, mode)
    return None if c is None else (not c)


def bisect_async(cell, spec, ck_slew, d_slew, mode, lo=-20.0, hi=80.0, n=8):
    """recovery / removal（U8）。**dt が大きいほど安全**なので向きは setup と同じ。

      recovery: 解除がクロック端の dt だけ前。**取り込めれば OK**
                （リセット値 0 のままなら失敗）。
      removal : 解除がクロック端の dt だけ後。**リセットが効いたままなら OK**
                （取り込んでしまったら失敗）。

    ★ **取り込ませる値は「非同期ピンが作る値の逆」でなければ測れない。**
      リセット値が Q=0 のセルに 0 を取り込ませても「取り込めたのか、
      リセットされたのか」が区別できない（`async_dir`）。
    """
    d_rise = async_dir(cell)
    ok = ((lambda dt_, tag: captures(cell, spec, ck_slew, d_slew, d_rise, dt_, tag, mode))
          if mode == "recovery"
          else (lambda dt_, tag: holds_reset(cell, spec, ck_slew, d_slew, d_rise,
                                             dt_, tag, mode)))
    tag = f"{cell}_{mode[:2]}_{ck_slew}_{d_slew}"
    if not ok(hi, tag + "_hi"):
        return None                      # 一番緩い条件でも駄目
    if ok(lo, tag + "_lo"):
        return lo                        # 一番厳しい条件でも通る
    for i in range(n):
        mid = (lo + hi) / 2
        if ok(mid, f"{tag}_{i}"):
            hi = mid
        else:
            lo = mid
    return hi


def characterize(cell):
    spec = SEQ[cell]
    res = {"cell": cell, "seq": True, "q": spec["q"], "d": spec["d"],
           "ckq": {"cell_rise": [], "cell_fall": [],
                   "rise_transition": [], "fall_transition": []},
           "setup": {"rise": [], "fall": []}, "hold": {"rise": [], "fall": []},
           "cap": {}}
    for si, sl in enumerate(SLEWS):
        for d_rise in (True, False):
            vals, _ = run_ngspice(build_ckq(cell, spec, sl, d_rise),
                                  f"{cell}_ckq_s{si}_{'r' if d_rise else 'f'}")
            d = [vals.get(f"d{k}") for k in range(len(LOADS))]
            t = [vals.get(f"t{k}") for k in range(len(LOADS))]
            if d_rise:
                res["ckq"]["cell_rise"].append(d); res["ckq"]["rise_transition"].append(t)
            else:
                res["ckq"]["cell_fall"].append(d); res["ckq"]["fall_transition"].append(t)
    for d_rise in (True, False):
        k = "rise" if d_rise else "fall"
        for ds in SLEWS_C:
            rs, rh = [], []
            for cs in SLEWS_C:
                rs.append(bisect_setup(cell, spec, cs, ds, d_rise))
                rh.append(bisect_hold(cell, spec, cs, ds, d_rise))
            res["setup"][k].append(rs)
            res["hold"][k].append(rh)
    # --- recovery / removal（U8）。非同期ピンを持つセルだけ ---------------
    if async_pin(cell):
        k = "rise" if async_dir(cell) else "fall"
        res["async_pin"] = async_pin(cell)
        res["recovery"] = {k: []}
        res["removal"] = {k: []}
        for ds in SLEWS_C:
            rr, rm = [], []
            for cs in SLEWS_C:
                rr.append(bisect_async(cell, spec, cs, ds, "recovery"))
                rm.append(bisect_async(cell, spec, cs, ds, "removal"))
            res["recovery"][k].append(rr)
            res["removal"][k].append(rm)
    return res


def main():
    want = sys.argv[1:] or list(SEQ)
    from check_comb import CELLDIR, CELLEXT
    miss = [c for c in want if not os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")]
    if miss:
        # ★ **どこを見たかを言う。** 「無い」だけだと、置き場が違うのか
        #   本当に無いのかが分からない（`TR1UM_CELLDIR` / `TR1UM_CELLEXT` で
        #   変えられるので、シェルに古い値が残っているだけのことがある）。
        print(f"** ネットリストが無いので特性化しない: {', '.join(miss)}\n"
              f"   見た場所: {CELLDIR}/<セル>{CELLEXT}\n"
              f"   TR1UM_CELLDIR={os.environ.get('TR1UM_CELLDIR', '(未設定)')} "
              f"TR1UM_CELLEXT={os.environ.get('TR1UM_CELLEXT', '(未設定)')}\n"
              f"   抽出ネットリストを置くには: "
              f"python3 loadext.py <設計>/lef/extracted -o cells_ext", flush=True)
    want = [c for c in want if c not in miss]
    os.makedirs(f"{HERE}/char", exist_ok=True)
    print(f"{'cell':<10}  CK->Q(slew0.6/CL50) [ns]      setup [ns]        hold [ns]", flush=True)
    for cell in want:
        r = characterize(cell)
        json.dump(r, open(f"{HERE}/char/{cell}.json", "w"), indent=1)
        si, li = SLEWS.index(0.6), LOADS.index(50)
        dr = r["ckq"]["cell_rise"][si][li]; df = r["ckq"]["cell_fall"][si][li]
        ci = SLEWS_C.index(1.5)
        su_r = r["setup"]["rise"][ci][ci]; su_f = r["setup"]["fall"][ci][ci]
        ho_r = r["hold"]["rise"][ci][ci];  ho_f = r["hold"]["fall"][ci][ci]
        s = lambda v, k=1e9: f"{v*k:.2f}" if v is not None else "-"
        print(f"{cell:<10}  rise {s(dr)} / fall {s(df)}      "
              f"r {s(su_r,1)} / f {s(su_f,1)}    r {s(ho_r,1)} / f {s(ho_f,1)}", flush=True)
        if "recovery" in r:
            dk = next(iter(r["recovery"]))
            rec = r["recovery"][dk][ci][ci]
            rem = r["removal"][dk][ci][ci]
            print(f"{'':<10}  {r['async_pin']}: recovery {s(rec,1)} ns / "
                  f"removal {s(rem,1)} ns  （slew 1.5、CK_HIGH={CK_HIGH:g}、U8）",
                  flush=True)
            # ★ **数字が波形に張り付いていないかを、その場で言う。**
            #   removal が CK_HIGH とほぼ同じなら、測れているのは
            #   「クロックが下りるまでリセットを保て」という波形の性質で、
            #   セルの定数ではない（U8 の `DFFRB` がこれだった）。
            if rem is not None and abs(rem - CK_HIGH) < 2.0:
                print(f"{'':<10}  ★ removal が CK_HIGH({CK_HIGH:g}) に張り付いている。"
                      f"**セルの定数ではない**", flush=True)
                print(f"{'':<10}    このセルの非同期ピンは**出力段だけ**に効いて"
                      f"いて、取り込みとの競合が無い可能性が高い。", flush=True)
                print(f"{'':<10}    `TR1UM_CK_HIGH` を変えて 2 回回し、"
                      f"答えが一緒に動くかで確かめること。", flush=True)


if __name__ == "__main__":
    main()

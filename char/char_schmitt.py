#!/usr/bin/env python3
"""シュミットトリガのしきい値（VT+ / VT-）を測る。

  usage: python3 char_schmitt.py            # 既定は BUFTH
         python3 char_schmitt.py BUFTH --deck-only   # デッキを見るだけ

なぜ要るか（2026-09-17）:
  `BUFTH` の **VT+ 3.709 V / VT- 1.201 V** は `mklib.py` の `SCHMITT` に
  **直書きの定数**で、「DC で往復させて測った実測値」と書いてあるだけだった。
  デッキもログもリポジトリに無く、**測り直せない**。この値は

    - Liberty の `input_voltage (BUFTH_in)`（合成と STA が読む）
    - `insert_bufth.py` / `docs/10_pdk_facts.md` / `docs/11_frame_io.md`
    - IRSIM で BUFTH を迂回する判断（U14）

  の根拠になっている。**根拠にする数字は測り直せるようにしておく**（U45）。

測り方:
  DC 掃引は履歴を持てないので、**準 DC の三角波**で往復させる。
  0 -> VDD -> 0 を 200 µs ずつ（セル本来の遷移 ~1 ns の 2x10^5 倍）で振り、
  出力が VDD/2 を横切った瞬間の**入力電圧**を拾う。
  これが立上りのしきい値 VT+ と立下りのしきい値 VT-。

  条件は `charlib` の既定（typ モデル / VDD 5.0 V / 25 °C）。
  **条件を書かずに数字だけ出さないこと。**
"""
from __future__ import annotations

import argparse

import cellspec
from charlib import (HERE, TEMP, VDD, all_ports_of, header, run_ngspice)

RAMP_US = 200.0          # 片道の傾斜時間 [µs]。準 DC（セル本来の ~1ns の 2e5 倍）
FLAT_US = 20.0           # 両端で落ち着かせる時間 [µs]
LOAD_FF = 10.0           # 出力負荷。しきい値は DC の性質なので効かないが、数値的に安定する


def one_in_one_out(cell):
    """入力 1 本・出力 1 本のセルであることを確かめて (入力, 出力) を返す。"""
    outs = cellspec.COMB.get(cell)
    if not outs:
        raise SystemExit(f"{cell} が cellspec.COMB に無い（組合せセルの表）")
    if len(outs) != 1:
        raise SystemExit(f"{cell} は出力が {len(outs)} 本。この道具は 1 本だけ")
    opin, (ipins, _fn) = next(iter(outs.items()))
    if len(ipins) != 1:
        raise SystemExit(f"{cell} は入力が {len(ipins)} 本。この道具は 1 本だけ")
    return ipins[0], opin


def build(cell, ipin, opin):
    t0 = FLAT_US
    t1 = t0 + RAMP_US                     # 頂点
    t2 = t1 + FLAT_US
    t3 = t2 + RAMP_US                     # 谷
    tend = t3 + FLAT_US
    L = [f"* {cell} シュミットのしきい値 -- char_schmitt.py 生成",
         f"* 準 DC の三角波（片道 {RAMP_US:g} us）で往復させ、出力が VDD/2 を"
         f"横切った瞬間の入力電圧を拾う"]
    L += header(cell)
    # 理想電圧源を直につなぐとソルバが不安定になるので微小抵抗で正則化する
    # （`char_comb.py` と同じ理由）。
    L.append(f"Vin {ipin}_src 0 PWL(0 0 {t0:g}u 0 {t1:g}u {VDD:g} "
             f"{t2:g}u {VDD:g} {t3:g}u 0 {tend:g}u 0)")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    L.append("")
    L.append("X0 " + " ".join(all_ports_of(cell)) + f" {cell}")
    L.append(f"C0 {opin} 0 {LOAD_FF:g}f")
    L.append("")
    L.append(f".tran {RAMP_US / 2000:g}u {tend:g}u")
    vt = VDD / 2
    L.append(f".measure tran vt_rise FIND v({ipin}) WHEN v({opin})={vt:g} RISE=1")
    L.append(f".measure tran vt_fall FIND v({ipin}) WHEN v({opin})={vt:g} FALL=1")
    L.append(".end")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cell", nargs="?", default="BUFTH")
    ap.add_argument("--deck-only", action="store_true", help="デッキを出すだけ")
    a = ap.parse_args()

    ipin, opin = one_in_one_out(a.cell)
    deck = build(a.cell, ipin, opin)
    if a.deck_only:
        print(deck, end="")
        return 0

    vals, log = run_ngspice(deck, f"schmitt_{a.cell}")
    vr, vf = vals.get("vt_rise"), vals.get("vt_fall")
    if vr is None or vf is None:
        print(log[-2000:])
        raise SystemExit(f"** しきい値が取れなかった。{HERE}/logs/schmitt_{a.cell}.log を見ること")

    print(f"=== {a.cell} シュミットのしきい値  "
          f"（typ モデル / VDD {VDD:g} V / {TEMP:g} °C、準 DC 三角波 片道 {RAMP_US:g} us）")
    print(f"  VT+ 立上り : {vr:.3f} V")
    print(f"  VT- 立下り : {vf:.3f} V")
    print(f"  ヒステリシス: {vr - vf:.3f} V")

    import mklib
    frozen = mklib.SCHMITT.get(a.cell)
    if frozen:
        dr = vr - frozen["vt_rise"]
        df = vf - frozen["vt_fall"]
        print()
        print(f"  mklib.SCHMITT の値 : VT+ {frozen['vt_rise']:.3f} / "
              f"VT- {frozen['vt_fall']:.3f}")
        print(f"  差                 : VT+ {dr:+.3f} V / VT- {df:+.3f} V")
        if max(abs(dr), abs(df)) > 0.05:
            print("  ** 50 mV を超えてずれている。Liberty の input_voltage は"
                  " mklib の定数から出ているので、直すならそちら")
        else:
            print("  -> 一致（50 mV 以内）。Liberty の input_voltage はこの値でよい")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from charlib import (CELLDIR, CELLEXT, HERE, TEMP, VDD, all_ports_of,
                     header, models_include, run_ngspice, to_xm)
from check_comb import subckt_ports_of

RAMP_US = 200.0          # 片道の傾斜時間 [µs]。準 DC（セル本来の ~1ns の 2e5 倍）
FLAT_US = 20.0           # 両端で落ち着かせる時間 [µs]
LOAD_FF = 10.0           # 出力負荷。しきい値は DC の性質なので効かないが、数値的に安定する

# しきい値を「出力が何 % を横切った入力電圧」で定義するか。
# ★ **50 % だけ見ていると、定義の違いなのか回路の違いなのか分からない。**
#   TR-1um は 1 µm・5 V で利得が高くないので、遷移域は入力電圧で数百 mV ある。
#   10 / 50 / 90 % の 3 点を出して**遷移域の広さごと**見せる。
OUT_PCT = (10, 50, 90)


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


def ports_for(cell, netlist=None):
    """インスタンス行のポート順。`--netlist` のときはその file の宣言順を読む。"""
    return subckt_ports_of(netlist, cell) if netlist else all_ports_of(cell)


def build(cell, ipin, opin, ramp_us=RAMP_US, netlist=None):
    t0 = FLAT_US
    t1 = t0 + ramp_us                     # 頂点
    t2 = t1 + FLAT_US
    t3 = t2 + ramp_us                     # 谷
    tend = t3 + FLAT_US
    L = [f"* {cell} シュミットのしきい値 -- char_schmitt.py 生成",
         f"* 準 DC の三角波（片道 {ramp_us:g} us）で往復させ、出力が"
         f"{'/'.join(str(p) for p in OUT_PCT)} % を横切った瞬間の入力電圧を拾う"]
    if netlist:
        L += [models_include(), "", to_xm(netlist), "",
              f".temp {TEMP}", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]
    else:
        L += header(cell)
    # 理想電圧源を直につなぐとソルバが不安定になるので微小抵抗で正則化する
    # （`char_comb.py` と同じ理由）。
    L.append(f"Vin {ipin}_src 0 PWL(0 0 {t0:g}u 0 {t1:g}u {VDD:g} "
             f"{t2:g}u {VDD:g} {t3:g}u 0 {tend:g}u 0)")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    L.append("")
    # ★ **ポート順はそのネットリスト自身から読む**（U42）。
    #   `all_ports_of` は既定の置き場（抽出網）の順を返すので、`--netlist` で
    #   別の網を指すと**ずれる**。実際にずれた（2026-09-17）:
    #     抽出網          .SUBCKT BUFTH A Y vss vdd
    #     LVS ソース      .subckt BUFTH A Y vdd vss
    #   ngspice は数が合えば黙って繋ぐので、**電源と接地が入れ替わったまま
    #   落ちずに**中点に居座り、`.measure` だけが "out of interval" で失敗した。
    L.append("X0 " + " ".join(ports_for(cell, netlist)) + f" {cell}")
    L.append(f"C0 {opin} 0 {LOAD_FF:g}f")
    L.append("")
    L.append(f".tran {ramp_us / 2000:g}u {tend:g}u")
    for pct in OUT_PCT:
        v = VDD * pct / 100
        L.append(f".measure tran vr{pct} FIND v({ipin}) WHEN v({opin})={v:g} RISE=1")
    for pct in reversed(OUT_PCT):
        v = VDD * pct / 100
        L.append(f".measure tran vf{pct} FIND v({ipin}) WHEN v({opin})={v:g} FALL=1")
    L.append(".end")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cell", nargs="?", default="BUFTH")
    ap.add_argument("--deck-only", action="store_true", help="デッキを出すだけ")
    ap.add_argument("--ramp-us", type=float, default=None, metavar="US",
                    help="片道の傾斜時間 [us]。既定 %g。"
                         "複数回すと**準 DC に収束しているか**が見える" % RAMP_US)
    ap.add_argument("--sweep", action="store_true",
                    help="傾斜を 4 通り回して収束を見る（否定対照）")
    ap.add_argument("--netlist", metavar="PATH",
                    help="セルのネットリストを明示する（既定は TR1UM_CELLDIR の抽出網）")
    a = ap.parse_args()

    ipin, opin = one_in_one_out(a.cell)
    if a.deck_only:
        print(build(a.cell, ipin, opin, a.ramp_us or RAMP_US, a.netlist), end="")
        return 0

    ramps = [20.0, 200.0, 2000.0, 20000.0] if a.sweep else [a.ramp_us or RAMP_US]
    src = a.netlist or f"{CELLDIR}/{a.cell}{CELLEXT}"
    print(f"=== {a.cell} シュミットのしきい値")
    print(f"  条件   : typ モデル / VDD {VDD:g} V / {TEMP:g} °C / 準 DC 三角波")
    print(f"  網     : {src}")
    print(f"  ポート順: {' '.join(ports_for(a.cell, a.netlist))}"
          f"   （その網の .subckt 宣言順。U42）")
    print(f"  しきい値の定義: 出力が {'/'.join(str(p) for p in OUT_PCT)} % を"
          f"横切った瞬間の**入力**電圧")
    print()
    hdr = "  片道[us]  " + "".join(f"  VT+{p:<3d}" for p in OUT_PCT) \
          + "".join(f"  VT-{p:<3d}" for p in reversed(OUT_PCT)) + "   ヒス(50%)"
    print(hdr)
    last = None
    for ramp in ramps:
        deck = build(a.cell, ipin, opin, ramp, a.netlist)
        vals, log = run_ngspice(deck, f"schmitt_{a.cell}_{ramp:g}us")
        got = {k: vals.get(k) for k in
               [f"vr{p}" for p in OUT_PCT] + [f"vf{p}" for p in OUT_PCT]}
        if any(v is None for v in got.values()):
            print(log[-2000:])
            raise SystemExit(
                f"** しきい値が取れなかった。\n"
                f"   log: {HERE}/logs/schmitt_{a.cell}_{ramp:g}us.log\n"
                f"   使ったポート順: {' '.join(ports_for(a.cell, a.netlist))}\n"
                f"   ★ 出力が一度も振れていないなら**電源と接地が入れ替わって"
                f"いる**のを疑う。\n"
                f"     ngspice は数が合えば黙って繋ぐので、順を間違えても落ちない"
                f"（U42）。\n"
                f"     ログ冒頭の Initial Transient Solution で出力が中点に"
                f"居座っていたらそれ。")
        row = f"  {ramp:>8g}  " + "".join(f"  {got[f'vr{p}']:6.3f}" for p in OUT_PCT) \
              + "".join(f"  {got[f'vf{p}']:6.3f}" for p in reversed(OUT_PCT)) \
              + f"   {got['vr50'] - got['vf50']:6.3f}"
        print(row)
        last = got

    vr, vf = last["vr50"], last["vf50"]
    print()
    print(f"  VT+ 立上り : {vr:.3f} V   VT- 立下り : {vf:.3f} V   "
          f"ヒステリシス: {vr - vf:.3f} V")
    print(f"  遷移域の幅 : 立上り {abs(last[f'vr{OUT_PCT[-1]}'] - last[f'vr{OUT_PCT[0]}']):.3f} V"
          f" / 立下り {abs(last[f'vf{OUT_PCT[0]}'] - last[f'vf{OUT_PCT[-1]}']):.3f} V")
    print("  ★ 遷移域が広いほど「何 % で測るか」で値が動く。"
          "50 % 以外の定義で測られた数字と比べるときはここを見ること。")

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
            print("     直す前に (1) 傾斜を振って収束しているか（--sweep）")
            print("            (2) 別の網でも同じか（--netlist）を見ること")
        else:
            print("  -> 一致（50 mV 以内）。Liberty の input_voltage はこの値でよい")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

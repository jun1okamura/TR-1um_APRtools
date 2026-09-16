#!/usr/bin/env python3
"""chip_tb_lib.py -- チップ TB を組むときの、**設計に依らない**道具だけ。

刺激（どのパッドをいつ叩くか）と期待値は**設計ごとに違う**ので設計側の
`scripts/gen_chip_tb.py` に置く（U25）。ここに入れてよいのは

  - 抽出ネットリストから `.subckt` の**ポート順を読む**（U42）
  - 0/1 の列を PWL 文字列にする
  - PDK のモデルを `models.spice` の 1 行に閉じ込める（U24）
  - 置き場（`layout/chip/simulation/…`）の決め方

★ **ポート順は生産物から読む。** 抽出が出す並びは KLayout の**辞書順**
  （`P1 P10 P11 … P9 VDD VSS`）で、フレームの並びとは違う。**ngspice は数が
  合えば黙って繋ぐ**ので、TB 側で順番を直書きすると落ちずに全パッドが
  でたらめになる（実測: 12 項目中 10 FAIL / 2 まぐれ PASS。U42）。

★ **TB に PDK の絶対パスを書かない。** 隣に `models.spice` を起こして
  `.include 'models.spice'` だけ書く。他機でもそのまま読める（U24）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ


def sim_dir(cfg):
    return os.path.join(cfg.CHIP, "simulation")


def sim_netlist(cfg):
    """`gen_chip_sim_ready.py` が書く、ngspice で読める抽出ネットリスト。"""
    return os.path.join(sim_dir(cfg), cfg.CHIP_TOP_CELL + "_sim.spice")


def tb_path(cfg, ext=".spi"):
    return os.path.join(sim_dir(cfg), "tb_" + cfg.CHIP_TOP_CELL + ext)


def subckt_ports(path, name):
    """`.subckt <name> …` のポート順をそのまま返す（継続行 `+` も拾う）。

    ★ **語で切って比べる**（正規表現で行頭から当てない）。以前の版は
      `^\.subckt\s+<name>\s` だったので、**ポートが 1 つも無い
      `.subckt NAME` は行末に `\s` が無くて拾えなかった**。
      `.subckt` の綴りは大小どちらでもよい（SPICE の慣習）。名前の方は
      **そのまま比べる** — 抽出器が出す名前をこちらで正規化しない。
    """
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        t = line.split()
        if len(t) >= 2 and t[0].lower() == ".subckt" and t[1] == name:
            toks = t[2:]
            j = i + 1
            while j < len(lines) and lines[j].startswith("+"):
                toks += lines[j][1:].split()
                j += 1
            return toks
    raise SystemExit(f".subckt {name} が {path} に無い")


def pwl(events, vdd=5.0, tr=1.0):
    """`[(t_ns, 0/1)]` -> PWL 文字列。**t で遷移を始める**（t で終えない）。

    ★ **これは TD4 の規約。設計をまたいで使い回さないこと**（U60 で確認）。
      `TR-1um_SCLK_SPI` は**逆**で、`t - tr` で立ち上げて **t には整定済み**に
      する（クロック端でサンプルするため）。さらに時間の単位も違う —
      ここは ns で `100n` と書き、SPI は秒で `100e-9`。末尾に `tend` の点を
      足すかどうかも違う。**3 つとも意図してそうしている**ので、同じ名前の
      関数だからと寄せると、落ちずに刺激の時刻だけがずれる。
    """
    out, prev = [], None
    for t, v in events:
        lv = vdd if v else 0.0
        if prev is None:
            out.append(f"0 {lv:g}")
        else:
            out.append(f"{t:g}n {prev:g}")
            out.append(f"{t + tr:g}n {lv:g}")
        prev = lv
    return "PWL(" + " ".join(out) + ")"


def write_models_shim(cfg, out_dir, name="models.spice"):
    """TB の隣に `models.spice`（PDK のモデルへの `.include` 1 行）を書く。

    **機械依存の絶対パスをこの 1 ファイルに閉じ込める**ので、TB 自身は
    `.include 'models.spice'` だけで済む。生成物なので `.gitignore` する。
    戻り値は TB に書く相対名。
    """
    models = os.path.join(cfg.pdk_spice_models(), "ip62_models")
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("* 自動生成。回した機械の PDK を指す **1 行だけ**の橋渡し。\n"
                "* ngspice の .include は環境変数を展開しないので、素直に書くと\n"
                "* 回した機械のパスが TB に焼き付いてコミットできなくなる（U24）。\n"
                "* TR1UM_PDK を変えて gen_chip_tb.py を回し直せば更新される。\n"
                f".include '{models}'\n")
    return name

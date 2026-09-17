#!/usr/bin/env python3
"""check_top_channels.py -- チップ配線がチャネルに入るかを配線前に見積もる

コアはパッドリングの開口の中に座り、四方に通路（チャネル）ができる:

    T  コアの上    B  コアの下    L, R  コアの脇（壁からコア端まで）

T-R-B-L は閉じた輪になる。この輪を左下から反時計回りに 1 本の座標へ
伸ばす（unroll）と、どの配線も円周上の区間 1 本になり、**ある通路の中で
区間が最も深く重なった数**が、その通路が用意しなければならないトラック数
になる。

1 本の配線につき 1 トラック、寄り道なし、ビアの費用なし。つまり **下限**
である。ここで容量を超えている通路は配線できない。配置を直すのが安い。

  使い方:  python3 $APRTOOLS/apr/check_top_channels.py [--pitch 5.4]
           （設計ルートで回す。`layout/chip/signal_routing_plan.json` を読む）

★ **2026-09-17 に SCLK_SPI から移した**（U80）。`docs/23_flow_chip.md` が
  流れの step2b に書いているのに APRtools に無く、回すと
  `No such file or directory` だった。
  **`check_chip.py` と `pin_list.py` は移していない**（実体は
  `TR-1um_SCLK_SPI/scripts/`）。

★ 移すときに **中身は 2 か所とも書き直した**。元は 2 世代前の形に書かれて
  いて、SCLK_SPI 自身の `signal_routing_plan.json` でも動かなかった
  （`plan["nets"]` は無い / `chip_geometry()` に `ptect_box` は無い）。
  いまの形に合わせたのは:
    - プランは `plan["signals"]`（1 行 = 端子 2 つの配線 1 本）を読む。
    - 幾何は `config.chip_geometry()` の `core_chip_bbox` と `wall`
      （**辺ごとに実測**）を読む。測れていない辺だけ
      `rules.FRAME_INNER_WALL` で代え、そう出す。
    - 元にあった U（コアの下の PTECT との隙間）は **消した**。いまの
      `chip_geometry()` に PTECT の箱は無く、コアの下は B そのものである。
"""
import argparse
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lint: ok apr/ 自身
import apr_path  # noqa: F401,E402  設計ルートを sys.path へ

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import config as _cfg               # noqa: E402
import rules                        # noqa: E402  プロセス定数の単一ソース

PLAN = os.path.join(_cfg.CHIP, "signal_routing_plan.json")
SIDES = ("left", "right", "bottom", "top")


class Ring:
    """T-R-B-L の輪を、左下角から反時計回りに 1 本の座標へ伸ばしたもの。"""

    def __init__(self, geom):
        cl, cb, cr, ct = geom["core_chip_bbox"]
        measured = geom.get("wall") or {}
        d = rules.FRAME_INNER_WALL
        default = {"left": -d, "right": d, "bottom": -d, "top": d}
        self.wall = {k: (measured.get(k) if measured.get(k) is not None else default[k])
                     for k in SIDES}
        self.assumed = [k for k in SIDES if measured.get(k) is None]

        self.width = {"T": self.wall["top"] - ct, "B": cb - self.wall["bottom"],
                      "L": cl - self.wall["left"], "R": self.wall["right"] - cr}
        self.lx = (self.wall["left"] + cl) / 2       # 脇の通路の中心線
        self.rx = (cr + self.wall["right"]) / 2
        self.by = (self.wall["bottom"] + cb) / 2     # 下／上の通路の中心線
        self.ty = (ct + self.wall["top"]) / 2
        self.hspan, self.vspan = self.rx - self.lx, self.ty - self.by
        self.bounds = {                              # 通路 -> s の区間
            "B": (0.0, self.hspan),
            "R": (self.hspan, self.hspan + self.vspan),
            "T": (self.hspan + self.vspan, 2 * self.hspan + self.vspan),
            "L": (2 * self.hspan + self.vspan, 2 * (self.hspan + self.vspan)),
        }
        self.total = 2 * (self.hspan + self.vspan)

    def s_top(self, x):
        return self.hspan + self.vspan + (self.rx - x)

    def s_bottom(self, x):
        return x - self.lx

    def s_left(self, y):
        return 2 * self.hspan + self.vspan + (self.ty - y)

    def s_right(self, y):
        return self.hspan + (y - self.by)

    def terminal_s(self, t):
        edge = t.get("edge")
        if edge not in ("TOP", "BOTTOM", "LEFT", "RIGHT"):
            raise KeyError(f"端子の edge が読めない: {t!r}")
        return {"TOP": lambda: self.s_top(t["x"]), "BOTTOM": lambda: self.s_bottom(t["x"]),
                "LEFT": lambda: self.s_left(t["y"]), "RIGHT": lambda: self.s_right(t["y"])}[edge]()

    def arc(self, points):
        """points の s を全部覆う最小の弧 -> (始点, 長さ)。

        ★ 同じ点が 2 つ来たら **必ず落とす**。落とさないと隙間が全部 0 に
          なって「最大の隙間の裏返し」が円周 1 周になる（移植直後、パッド
          から同じパッドへ落とすだけの DIS が全通路に 1 本ずつ乗っていた）。"""
        pts = []
        for q in sorted(p % self.total for p in points):
            if not pts or abs(q - pts[-1]) > 1e-9:
                pts.append(q)
        if len(pts) > 1 and abs(pts[0] + self.total - pts[-1]) <= 1e-9:
            pts.pop()
        if len(pts) == 1:
            return pts[0], 0.0
        gaps = [(pts[(i + 1) % len(pts)] - pts[i]) % self.total for i in range(len(pts))]
        widest = max(range(len(pts)), key=lambda i: gaps[i])
        return pts[(widest + 1) % len(pts)], self.total - gaps[widest]

    def spans(self, start, length):
        """弧を (通路, s0, s1) の破片に割る。長さ 0 の弧は破片 0 個
        （通路を横切るだけで、通路に沿ってトラックを 1 本食わないため）。"""
        out = []
        s = start % self.total
        left = length
        while left > 1e-9:
            for c, (a, b) in self.bounds.items():
                if a - 1e-9 <= s < b - 1e-9 or (s < 1e-9 and a < 1e-9):
                    step = min(b - s, left)
                    out.append((c, s, s + step))
                    s = (s + step) % self.total
                    left -= step
                    break
            else:
                s = 0.0
        return out


def rows_of(plan, path):
    """プランの 1 行 = 端子 2 つの配線 1 本。同じ網が複数行に出る（DIS の
    スター配線など）ので、札は net か net.role にする。"""
    rows = plan.get("signals") if isinstance(plan, dict) else None
    bad = None
    if rows is None:
        bad = "signals という見出しが無い"
    elif not rows:
        bad = "signals が空"
    else:
        for i, r in enumerate(rows):
            if not (isinstance(r, dict) and isinstance(r.get("from"), dict)
                    and isinstance(r.get("to"), dict)):
                bad = f"signals[{i}] に from / to が無い（持っているのは {sorted(r)}）"
                break
    if bad:
        raise SystemExit(
            f"この配線プランは読めない: {path}\n"
            f"  {bad}\n"
            f"  持っている見出し: {sorted(plan) if isinstance(plan, dict) else type(plan).__name__}\n"
            f"  この道具が読むのは gen_top_routing_plan.py が書く "
            f"layout/chip/signal_routing_plan.json（1 行が net / from / to）。\n"
            f"  gio_connections.json にも signals はあるが、あれは pad の割り当て表で幾何が無い。")
    seen = {}
    for r in rows:
        seen[r.get("net")] = seen.get(r.get("net"), 0) + 1
    out = []
    for r in rows:
        net = r.get("net")
        label = str(net) if net is not None else "(名前なし)"
        if seen[net] > 1:
            label = f"{label}.{r.get('role')}"
        out.append((label, r["from"], r["to"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="チップのチャネル容量を配線前に見積もる")
    ap.add_argument("--plan", default=PLAN, help="配線プラン（既定: layout/chip/signal_routing_plan.json）")
    ap.add_argument("--pitch", type=float, default=_cfg.TRACK_PITCH, help="トラックピッチ um")
    args = ap.parse_args()

    with open(args.plan) as fh:
        plan = json.load(fh)
    ring = Ring(_cfg.chip_geometry())
    rows = rows_of(plan, args.plan)

    load = {k: [] for k in ("T", "R", "B", "L")}
    flat = []
    for label, a, b in rows:
        start, length = ring.arc([ring.terminal_s(a), ring.terminal_s(b)])
        segs = ring.spans(start, length)
        if not segs:
            flat.append(label)
        for c, lo, hi in segs:
            load[c].append((lo, hi, label))

    print(f"配線プラン {_cfg.show(args.plan)}  配線 {len(rows)} 本  "
          f"ピッチ {args.pitch} um")
    if ring.assumed:
        print(f"★ 壁を測れていない辺 {ring.assumed} は "
              f"rules.FRAME_INNER_WALL {rules.FRAME_INNER_WALL} で代えた")
    print()
    print(f"{'通路':4s} {'幅 um':>8s} {'トラック':>8s} {'要る':>6s}   混んでいるところ")
    bad = 0
    for k in ("T", "R", "B", "L"):
        segs = load[k]
        cap = int(ring.width[k] // args.pitch)
        peak, who = 0, []
        for lo, _, _ in segs:
            here = [n for a, b, n in segs if a - 1e-9 <= lo < b - 1e-9]
            if len(here) > peak:
                peak, who = len(here), here
        ok = peak <= cap
        bad += 0 if ok else 1
        print(f"{k:4s} {ring.width[k]:8.1f} {cap:8d} {peak:6d}   "
              f"{'ok  ' if ok else 'NG  '}{', '.join(sorted(who)[:6])}"
              f"{' ...' if len(who) > 6 else ''}")

    if flat:
        print(f"\n通路に沿って走らない配線（横切るだけ） {len(flat)} 本: {', '.join(sorted(flat))}")
    ties = plan.get("ties") or []
    if ties:
        print(f"tie {len(ties)} 本は見ていない（電源リングへ落とすだけで、信号の通路を走らない）")
    print("\n1 本 1 トラック・最短の弧・寄り道なしで数えた **下限**。"
          "\n電源の配線と、通路を横切る分は数えていない。")
    if bad:
        print(f"\n判定: NG  {bad} つの通路が容量を超えている")
        raise SystemExit(1)
    print("\n判定: OK  どの通路も容量の中")


if __name__ == "__main__":
    main()

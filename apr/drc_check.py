"""drc_check.py -- 自作の簡易 DRC。M1/M2 の幅と間隔、V1 の間隔・囲み・カット寸法を数える。

GDS とトップセル名を取り、件数を stdout に出すだけ（ファイルも終了コードも
変えない）。サインオフは `drc_pdk.py`（PDK の本物のデッキ）で行う。

    python3 drc_check.py <gds> [<top_cell>]

★ **トップセル名を省くとコアのセル名にフォールバックする。** 以前は渡した
  GDS と無関係にコア名で固定していて、チップレベルの GDS に当てると
  **何も検査せずに 0 件を返していた**（実 DRC は 50 件出した）。
★ **フレーム単体に 1.4 超の V1 が 17 個ある**（同名セルの重ね合わせ）。
  チップで数えるときのベースラインは 0 ではなく 17。
★ 値とレイヤ番号を直書きしている。`rules.py` に同じものがあるので、
  そちらへ寄せるかは未決（U4: `drc_check_cells.py` だけ値が違う件も同根）。
"""

# --- ported from TR-1um_Async_I2C/script/ by scripts/port_i2c_scripts.py ---
import os as _os
import sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _HERE)
import apr_path  # noqa: F401  設計ルートを sys.path へ
import config as _cfg  # noqa: E402
import rules  # noqa: E402  プロセス定数・レイヤ番号の単一ソース
# ---------------------------------------------------------------------------
import sys
import klayout.db as db

GDS = sys.argv[1] if len(sys.argv) > 1 else None
# BUG FOUND 2026-08-29 (design_notes.md 79.8): TOP_CELL was hardcoded to
# the CORE cell name regardless of which GDS was passed in. Every call
# this session against layout/step8/v9_top_routed.gds (chip-level, top
# cell "tr_1um_i2c_slave_async") was silently checking the CORE cell
# _cfg.TOP_CELL_NAME instead -- which is nested INSIDE the chip
# cell, not the other way around, so begin_shapes_rec() on it never saw
# any of the chip-level power/signal routing at all. Every "0 violations"
# report for the chip-level GDS this session was checking nothing
# relevant. Real KLayout DRC (run by the user) found 50 real violations
# this script had completely missed as a direct result. Fixed: accept an
# explicit top-cell override (2nd CLI arg), defaulting to the core name
# only for backward compatibility with the earlier core-only checks.
TOP_CELL = sys.argv[2] if len(sys.argv) > 2 else _cfg.TOP_CELL_NAME

layout = db.Layout()
layout.read(GDS)
dbu = layout.dbu
top = layout.cell(TOP_CELL)


def idx(l):
    return layout.layer(*l)


def check(layer, minw, mins, label):
    r = db.Region(top.begin_shapes_rec(idx(layer))).merged()
    w = r.width_check(int(round(minw / dbu)))
    s = r.space_check(int(round(mins / dbu)))
    print(f"{label}: width viol={w.count()} space viol={s.count()}")


check(rules.M1, rules.M1_WIDTH_MIN, rules.M1_SPACE_MIN, 'M1')
check(rules.M2, rules.M2_WIDTH_MIN, rules.M2_SPACE_MIN, 'M2')

m1 = db.Region(top.begin_shapes_rec(idx(rules.M1))).merged()
m2 = db.Region(top.begin_shapes_rec(idx(rules.M2))).merged()
gc = db.Region(top.begin_shapes_rec(idx(rules.GC))).merged()
v1 = db.Region(top.begin_shapes_rec(idx(rules.V1)))

print('V1 space viol:', v1.space_check(int(round(rules.V1_SPACE_MIN / dbu))).count())
print('V1 enclosed by M1<1.0 viol:', v1.enclosed_check(m1, int(round(rules.V1_ENC_M1 / dbu))).count())
print('V1 enclosed by M2<1.0 viol:', v1.enclosed_check(m2, int(round(rules.V1_ENC_M2 / dbu))).count())
print('V1-GC space<1.2 viol:', v1.separation_check(gc, int(round(1.2 / dbu))).count())

# V1 のカットは 1.4 角ちょうど（V1.W1: bbox_max > 1.4）。
# 2026-09-14: assemble_top.py が同名セル（コアとフレームに両方ある
# `via_1` / `via_1$1`）を KLayout の既定 AddToCell で重ねてしまい、
# カットが 0.75 µm ずれて重なって幅 2.15 の V1 が 15 個できていた。
# 図形の間隔だけ見ていると V1.S1 でしか出ないので、幅も数える。
# ※ フレーム単体にも 1.4 を超える V1 が 17 個ある（ボンドパッド下など）。
#   チップで数えるときはその 17 個がベースライン。
_big = [p for p in v1.merged().each()
        if p.bbox().width() * dbu > rules.V1_CUT + 1e-4
        or p.bbox().height() * dbu > rules.V1_CUT + 1e-4]
print(f'V1 cut > 1.4 viol: {len(_big)}')

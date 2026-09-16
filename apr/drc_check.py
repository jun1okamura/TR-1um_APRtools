"""drc_check.py -- 自作の簡易 DRC。M1/M2 の幅と間隔、V1 の間隔・囲み・カット寸法を数える。

GDS とトップセル名を取り、件数を stdout に出すだけ（ファイルも終了コードも
変えない）。サインオフは `drc_pdk.py`（PDK の本物のデッキ）で行う。

    python3 drc_check.py <gds> [<top_cell>]

★ **トップセル名を省くとコアのセル名にフォールバックする。** 以前は渡した
  GDS と無関係にコア名で固定していて、チップレベルの GDS に当てると
  **何も検査せずに 0 件を返していた**（実 DRC は 50 件出した）。

★ **デッキと同じ除外を当てる**（U54、`00_Layers.drc`）。以前は生のレイヤで
  数えていたので、チップに当てると**フレームの構造を違反として数えていた**:

      M2 幅 1 / M2 間隔 5   スクライブの構造。`MASK` を引けば消える
      V1 カット > 1.4 が 17  パッド開口 17 個の下の 70x70 パッド via 16 個と、
                             `MASK` の下の 2374 角のリング 1 個

  これを「ベースラインは 0 ではなく 17」と**手で憶えて運用していた**。
  `MASK` + `SCRB` を引き、カット寸法は `V1P`（`PO` に触れる V1）を外す
  （デッキは `V1.WP` という別の規則で見る）ようにしたので、**きれいなチップは
  素直に 0 と出る**。手で憶えるしきい値は、増えたときに気づけない。

★ `SCRB` の導出（`TEMP.holes` の switch）は再現していない。認識層 (80,0) を
  そのまま引いているだけなので**近似**。サインオフは `drc_pdk.py`。
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

def main(gds=None, top_cell=None):
    gds = gds or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not gds:
        sys.exit("usage: drc_check.py <gds> [<top_cell>]")
    # ★ トップセル名は**必ず渡す**。以前は渡した GDS と無関係にコア名で
    #   固定していて、チップに当てると何も見ていなかった（2026-08-29）。
    top_cell = top_cell or (sys.argv[2] if len(sys.argv) > 2
                            else _cfg.TOP_CELL_NAME)

    layout = db.Layout()
    layout.read(gds)
    dbu = layout.dbu
    top = layout.cell(top_cell)
    if top is None:
        sys.exit(f"top cell {top_cell} が {_cfg.show(gds)} に無い")

    def idx(l):
        return layout.layer(*l)

    def raw(l):
        return db.Region(top.begin_shapes_rec(idx(l))).merged()

    # デッキは全層を `input(...).not(MASK + SCRB)` で読む（`00_Layers.drc`）
    excl = (raw(rules.MASK) + raw(rules.SCRB_MARK)).merged()

    def reg(l):
        r = raw(l)
        return (r - excl).merged() if not excl.is_empty() else r

    def check(layer, minw, mins, label):
        r = reg(layer)
        w = r.width_check(int(round(minw / dbu)))
        s_ = r.space_check(int(round(mins / dbu)))
        print(f"{label}: width viol={w.count()} space viol={s_.count()}")

    check(rules.M1, rules.M1_WIDTH_MIN, rules.M1_SPACE_MIN, 'M1')
    check(rules.M2, rules.M2_WIDTH_MIN, rules.M2_SPACE_MIN, 'M2')

    m1, m2 = reg(rules.M1), reg(rules.M2)
    ga = (reg(rules.GC) + reg(rules.GR)).merged()      # GA = GC + GR
    v1 = db.Region(top.begin_shapes_rec(idx(rules.V1)))
    if not excl.is_empty():
        v1 = v1 - excl

    print('V1 space viol:', v1.space_check(int(round(rules.V1_SPACE_MIN / dbu))).count())
    print('V1 enclosed by M1<1.0 viol:',
          v1.enclosed_check(m1, int(round(rules.V1_ENC_M1 / dbu))).count())
    print('V1 enclosed by M2<1.0 viol:',
          v1.enclosed_check(m2, int(round(rules.V1_ENC_M2 / dbu))).count())
    print(f'V1-GA space<{rules.V1_GA_SPACE_MIN} viol:',
          v1.separation_check(ga, int(round(rules.V1_GA_SPACE_MIN / dbu))).count())

    # V1 のカットは 1.4 角ちょうど（V1.W1）。**パッドの V1 は別規則**なので外す
    #   （デッキ: `V1P = V1.interacting(PO)` / `V1.WP: V1(P) Wmin < 60.0`）。
    # 2026-09-14: assemble_top.py が同名セル（`via_1` / `via_1$1`）を重ねて
    #   カットが 0.75 µm ずれ、幅 2.15 の V1 が 15 個できていた。間隔だけ見て
    #   いると V1.S1 でしか出ないので、幅も数える。
    po = reg(rules.PO)
    v1s = v1 - v1.interacting(po) if not po.is_empty() else v1
    _big = [p for p in v1s.merged().each()
            if p.bbox().width() * dbu > rules.V1_CUT + 1e-4
            or p.bbox().height() * dbu > rules.V1_CUT + 1e-4]
    print(f'V1 cut > {rules.V1_CUT} viol: {len(_big)}')
    return 0


if __name__ == "__main__":
    sys.exit(main())

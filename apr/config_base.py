"""config_base.py -- 設計非依存の既定値と導出。

設計側は `config.py` にこう書く:

    from config_base import *

    TOP_CELL_NAME     = "spi_slave_sclk_core"
    CHIP_TOP_CELL     = "tr_1um_jun1okamura_spi"
    NET_PATH          = "layout/spi_slave_sclk_net_pnr.v"
    N_ROWS            = 2
    CORE_WIDTH_TRACKS = 299
    CH_HEIGHTS        = [140.4, 900.0, 162.0]
    PAD_MAP           = {...}

    finalize(globals())

`finalize()` が導出値を埋めて `check()` を回す。**導出値を手で書かない。**

旧世代（`i2c_config.py` / `td4_config.py` + `spi_config.py` 薄皮）との違い:
  - 薄皮を廃止。スクリプトは `import config as cfg` と書く
  - 環境変数は `APR_*` に統一。旧 `I2C_TRACK_PITCH`（config 側）と
    `TD4_TRACK_PITCH`（ルータ側）の二重定義は実質バグで、config に設定しても
    ルータに届かなかった。統一でこれが構造的に解消する
  - コア幅は**トラック本数**で持つ（`docs/03_core_geometry.md`）
  - DRC 値・レイヤ番号は `rules.py` が単一ソース
  - PDK のデータはコピーせず `TR1UM_PDK` から参照（`pdk/README.md`）
"""
import math
import os

import rules

# APRtools のルート（このファイルは apr/ にある）
APR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 設計リポジトリのルート。スクリプトは設計ルートから実行する。
ROOT = os.path.abspath(os.environ.get("APR_DESIGN_ROOT", os.getcwd()))

_NS = None                      # finalize() が設計の名前空間を覚える


# ---- 環境変数 ------------------------------------------------------------
def getenv(name, default=None, cast=None):
    """`APR_<name>` を読む。**直接 os.environ を読まない。**

    変数名の一覧がここに集まるので、二重定義が構造的に起きない。
    """
    v = os.environ.get("APR_" + name)
    if v is None:
        return default
    if cast is bool:
        return v not in ("0", "", "no", "false", "False")
    return cast(v) if cast else v


def disp(path, root=None):
    """ログや生成ファイルに**書き残してよい形**のパス。

    `os.path.relpath(x, cfg.ROOT)` を直に使うと、設計の外にあるものが
    `../../HogeHoge/TR-1um_APRtools/...` になる。**その機械の置き方が
    生成物に焼き付く**ので、リポジトリをまたぐものは `$APRTOOLS/...` と
    書く（2026-09-15、`RING_OSC.spice` の由来コメントで実際に出た）。
    """
    p = os.path.abspath(path)
    root = os.path.abspath(root or (_NS.get("ROOT") if _NS else ROOT))
    for base, tag in ((root, None), (APR_ROOT, "$APRTOOLS")):
        try:
            rel = os.path.relpath(p, base)
        except ValueError:                      # 別ドライブ（Windows）
            continue
        if not rel.startswith(".."):
            return rel if tag is None else f"{tag}/{rel}"
    env = os.environ.get("TR1UM_PDK")
    if env:
        rel = os.path.relpath(p, os.path.abspath(env))
        if not rel.startswith(".."):
            return f"$TR1UM_PDK/{rel}"
    return os.path.basename(p)


def _g(key, default=None):
    """設計の名前空間から値を取る（finalize 後に有効）。"""
    if _NS is None:
        raise SystemExit("config_base: finalize(globals()) を呼んでいない")
    return _NS.get(key, default)


# ---- PDK の解決（データはコピーしない。pdk/README.md）--------------------
def pdk_root():
    cands = [c for c in (os.environ.get("TR1UM_PDK"),) if c]
    # ★ 個人のディレクトリ構成は書かない。`TR1UM_PDK` か、
    #   **APRtools / 設計の隣**に PDK が置いてあることを当てにする。
    cands += [os.path.join(os.path.dirname(APR_ROOT), "TR-1um"),
              os.path.join(os.path.dirname(ROOT), "TR-1um"),
              os.path.expanduser("~/TR-1um")]
    for c in cands:
        if os.path.isdir(os.path.join(c, "libs.tech")):
            return c
    raise SystemExit("TR-1um PDK が見つからない。TR1UM_PDK を設定すること。\n"
                     f"  試した場所: {cands}")


def pdk_tech_python():
    """KLayout の PCell パッケージ（`from cells import tr_1um`）。
    ルータのビアは全部この PCell のインスタンスなので必須。"""
    for c in (os.path.join(pdk_root(), "libs.tech", "klayout", "tech", "python"),
              os.path.join(pdk_root(), "klayout", "tech", "python")):
        if os.path.isdir(os.path.join(c, "cells")):
            return c
    raise SystemExit("PDK の KLayout PCell パッケージ（.../tech/python/cells）が無い")


def pdk_frame_gds():
    """フレーム GDS。**`_GIO` 付きを明示的に返す。**

    PDK には**同名で中身の違うフレームが 2 つ**ある:
        TR-1um_frame_25x25.gds       23 セル。`OSS_FRAME_GIO` を**持たない**
        TR-1um_frame_25x25_GIO.gds   29 セル。GIO パッド版 ← こちら
    設計リポジトリは GIO 版を非 GIO と同じ名前で置いていたので、
    ベース名で解決すると取り違える（`docs/07_frame_issue.md` §1）。

    解決順:
      1. `APR_FRAME_GDS`                      明示指定
      2. `pdk/pending-upstream/…_GIO.gds`     上流にまだ入っていない版
      3. `$TR1UM_PDK/libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds`
    """
    env = os.environ.get("APR_FRAME_GDS")
    if env:
        if not os.path.exists(env):
            raise SystemExit(f"APR_FRAME_GDS が指すファイルが無い: {env}")
        return env
    local = os.path.join(APR_ROOT, "pdk", "pending-upstream",
                         "TR-1um_frame_25x25_GIO.gds")
    if os.path.exists(local):
        return local
    p = os.path.join(pdk_root(), "libs.tech", "klayout", "libraries",
                     "TR-1um_frame_25x25_GIO.gds")
    if not os.path.exists(p):
        raise SystemExit(f"PDK にフレーム GDS が無い: {p}")
    return p


def frame_source():
    """いまどのフレームを使っているか。`("pending-upstream"|"pdk"|"env", path)`。"""
    if os.environ.get("APR_FRAME_GDS"):
        return ("env", os.environ["APR_FRAME_GDS"])
    local = os.path.join(APR_ROOT, "pdk", "pending-upstream",
                         "TR-1um_frame_25x25_GIO.gds")
    if os.path.exists(local):
        return ("pending-upstream", local)
    return ("pdk", pdk_frame_gds())


def pdk_frame_gds_upstream():
    """PDK 側のフレーム（比較用。pending-upstream を無視する）。"""
    return os.path.join(pdk_root(), "libs.tech", "klayout", "libraries",
                        "TR-1um_frame_25x25_GIO.gds")


def pdk_spice_models():
    return os.path.join(pdk_root(), "libs.tech", "spice", "models")


def pdk_drc_deck():
    return os.path.join(pdk_root(), "libs.tech", "klayout", "tech", "drc", "run.drc")


def pdk_lvs_deck():
    return os.path.join(pdk_root(), "libs.tech", "klayout", "tech", "lvs", "run.lvs")


# ---- セルライブラリ ------------------------------------------------------
STDCELL = getenv("STDCELL", "v59_4")


def stdcell_dir():
    return os.path.join(APR_ROOT, "stdcell", _g("STDCELL", STDCELL))


ROW_HEIGHT_UM = 59.4            # v59_4 の prBoundary 実測（全論理セル）
SITE_UM = rules.SITE_W
TRACK_PITCH = getenv("TRACK_PITCH", rules.TRACK_PITCH, float)
TAP_CELL = "TAP2"
TAP_W = 10.8
TAP_PITCH = 534.6               # I2C 実チップ実測

_FILL_W = {"FILL1": 5.4, "FILL2": 10.8, "FILL3": 16.2}
FILLS = [("FILL3", 16.2), ("FILL2", 10.8)]
if getenv("USE_FILL1", False, bool):
    FILLS = FILLS + [("FILL1", 5.4)]

# 優先 M2 コリドー。FILL3（3 トラック）なら真ん中の 1 本が必ず両側とも空く。
PRI_CELL = getenv("PRI_CELL", "FILL3")
if PRI_CELL not in _FILL_W:
    raise SystemExit(f"APR_PRI_CELL は {sorted(_FILL_W)} のどれか（今 {PRI_CELL}）")
PRI_W = _FILL_W[PRI_CELL]
PRI_PITCH = getenv("PRI_PITCH", 1e9, float)   # 1e9 = TAP 直後の 1 枠だけ
PRI_MODE = getenv("PRI_MODE", "both")         # "after" | "both"
PRI_EXTRA_X = [round(round(float(v) / SITE_UM) * SITE_UM, 3)
               for v in (getenv("PRI_X", "") or "").split(",") if v.strip()]

# ---- フロアプランの既定 --------------------------------------------------
N_ROWS = getenv("N_ROWS", 2, int)
# コア幅は**トラック本数**で持つ（`docs/03_core_geometry.md`）。
#   296 -> 1598.4（I2C/TD4 実績） / 299 -> 1614.6（TAP 4 列で取れる最大）
CORE_WIDTH_TRACKS = getenv("CORE_WIDTH_TRACKS", 296, int)
CH_HEIGHTS = None               # 設計が与える。None なら finalize が既定を作る
NO_BOTTOM_PORTS = getenv("NO_BOTTOM_PORTS", False, bool)
# ch の上下端がサイトグリッドに乗っていなくても止めない（既提出設計の再現用）
CH_END_OFF_GRID_OK = getenv("CH_END_OFF_GRID_OK", False, bool)
DOWN_FACING_INSTS = set()
PER_ROW_LOCAL_NETS = set()
PAD_MAP = {}
LOGO_BOX = None                 # 設計が空き地を指定するとき (x0,y0,x1,y1)
# ---- 合成と STA（設計ごと）-----------------------------------------------
SYN_LIB = None                  # None なら stdcell_file("tr1um_typ_5v0_25c.lib")
SYN_TOP = None                  # None なら TOP_CELL_NAME
SYN_RTL = []                    # 合成に読ませる RTL。設計が与える
SYN_OUT_DIR = None              # None なら <設計>/out
SYN_CONSTR = None               # None なら $APRTOOLS/syn/abc.constr
# セルの振る舞いモデル（Verilog）。iverilog の TB が要る設計だけ。
#   SYN_CELLS_GEN      char/mkcellverilog.py で起こす（I2C）。False なら既存を使う
#   SYN_CELLS_IN_SYNTH RTL がセルを直接インスタンス化しているので yosys にも読ませる
#                      （I2C の NOR2 クロス結合）。SPI / TD4 は素の RTL なので False
SYN_CELLS_V = None
SYN_CELLS_GEN = False
SYN_CELLS_IN_SYNTH = False
SYN_CELLS_ARGS = ["--power", "--delay", "1"]
SYN_BLACKBOX = []               # 合成中セルのまま残す（例 ["RSLATCH"]）
# TB は**リスト**。1 本ずつ iverilog に掛ける（SPI は 11 本ある）。
SYN_TB_RTL = []                 # RTL に当てる TB。空なら飛ばす
SYN_TB_NET = []                 # 畳み込み後のネットリストに当てる TB
SYN_TB_INCDIR = []              # iverilog -I に渡すディレクトリ
SYN_REF_NETLIST = None          # 既提出ネットリスト（cmp_cells.py で突き合わせ）
# フレームの LVS ソース（`mkframespice.py --no-combine` の出力）。
# None なら `<設計>/lef/simulation/OSS_FRAME_GIO_nocombine.spice`。
FRAME_LVS_SPICE = None
STA_CLK_PORT = None             # クロックを入れるポート名（例 "scl" / "sclk"）
STA_PERIOD_NS = 100.0           # STA の周期
STA_FALSE_PATH_FROM = ["rst_n"] # recovery/removal を特性化していないので外す
STA_NON_SIGNAL_PORTS = ["VDD", "GND"]   # 構造インスタンスの電源ピン用のポート
LOGO_SCALE = 1                  # ロゴの縮約（1 = 等倍）
LOGO_COLS = None                # 切り出す列 "0:64" など。None で全幅
UNBONDED = set()
PAD_ONLY_NETS = {}
BUFTH_NETS = []
CLK_NETS = []

# ---- マクロ（無い設計では縮退値のまま）----------------------------------
# ★ 縮退値が下流でどう解釈されるかは 1 箇所ずつ確認する
#   （step10 に (0,0,0,0) をそのまま渡すと ch[0] の底が圧縮から外れた）。
MACRO_MODE = getenv("MACRO_MODE", "none")     # none | landscape | portrait
MACRO_NET_CELL = "__NO_MACRO__"
MACRO_CELL = "__NO_MACRO__"
MACRO_W = MACRO_H = 0.0
MACRO_SIDE_GAP = 0.0
MACRO_GAP_UM = 0.0
MACRO_Y0 = 0.0
MACRO_ALIGN_ROW = getenv("MACRO_ROW", 0, int)
SIDE_BUS_TRACKS = getenv("SIDE_BUS", 0, int)
SIDE_BUS_SLACK = getenv("SIDE_BUS_SLACK", 5.4, float)
POWER_BAR_W = 10.0
POWER_BAR_GAP = 2.0
MACRO_POWER = getenv("MACRO_POWER", False, bool)

# ---- チップ --------------------------------------------------------------
FRAME_CELL = "OSS_FRAME_GIO"
FRAME_CELL_CHIP = "OSS_FRAME"   # 提出時に改名（pre_check.py の FRAME_CELL_NAMES）
GIO_PIN_RADIUS = rules.GIO_PIN_RADIUS
PTECT_LAYER = rules.PTECT
FRAME_HARD_LAYERS = rules.FRAME_HARD_LAYERS
LOGO_PITCH = rules.LOGO_PITCH
LOGO_DOT = rules.LOGO_DOT


# ---- TAP 列（`docs/03_core_geometry.md` §2）-----------------------------
def stdcell_file(name):
    """STDCELL 正本の中のファイル。`stdcell/<世代>/<name>`。

    セルライブラリそのもの（`.lef` / `.gds` / `.spice` / `.lib` /
    `simulation/`）は**設計ではなく APRtools のもの**。設計の `lef/` を
    指していた箇所はここへ寄せる（`apr/lint.py` の `moved-dir`）。
    """
    return os.path.join(stdcell_dir(), name)


def tap_columns(width_um, pitch=TAP_PITCH, tap_w=TAP_W):
    """x=0 から pitch 刻み + 行末（W - tap_w）。最後の間隔が pitch を超えたら
    列を 1 本増やす。返り値はサイトグリッドに乗った x のリスト。"""
    xs, x = [], 0.0
    last = round(width_um - tap_w, 3)
    while x + tap_w <= last - 1e-9:
        xs.append(round(x, 3))
        x += pitch
    xs.append(last)
    # 最後の間隔が **広すぎる**（pitch 超え）か **痩せすぎ**（pitch の半分未満）
    # なら等間隔に振り直す。
    #
    # ★ 痩せすぎも直す理由: 行幅 1150.2 だと列が 0 / 534.6 / 1069.2 / 1139.4 に
    #   なり、最後の区間が 70.2 µm しかない。そこへ回されたセルが入らず
    #   step3 が「1 個が行に入りきらない」で落ちる（TD4 縦置きで実際に起きた）。
    #
    # ★ 刻みは **1 回だけ丸める**（`round(step)` してから掛ける）。i ごとに
    #   丸めると 2 本目が 761.4 になり、TD4 の実績値 756.0 と合わない。
    gap = xs[-1] - xs[-2] if len(xs) >= 2 else 0.0
    if len(xs) >= 2 and (gap > pitch + 1e-6 or gap < pitch / 2):
        # **区間が全部 pitch 以内に収まる最小の本数**を取る。丸めで最後の
        # 区間が溢れることがあるので、収まるまで 1 本ずつ増やす。
        n = max(1, math.ceil(last / pitch))
        while True:
            step = round(round(last / n / SITE_UM) * SITE_UM, 3)
            cand = [round(i * step, 3) for i in range(n)] + [last]
            if max(b - a for a, b in zip(cand, cand[1:])) <= pitch + 1e-6:
                break
            n += 1
        xs = cand
    return xs


def max_core_width(n_taps, pitch=TAP_PITCH, tap_w=TAP_W):
    """TAP を n 列で済ませられるコア幅の上限。"""
    return round((n_taps - 1) * pitch + tap_w, 3)


# ---- 導出（finalize 後に有効）------------------------------------------
def row_y():
    """各行の prBoundary 下端 y（コアローカル）と、行スタックの総高。"""
    ch, nr, rh = _g("CH_HEIGHTS"), _g("N_ROWS"), _g("ROW_HEIGHT_UM")
    ys, y = [], 0.0
    for i in range(nr):
        y += ch[i]
        ys.append(round(y, 3))
        y += rh
    return ys, round(y + ch[-1], 3)


def _f(name):
    """設計が同名の関数を定義していればそちらを返す。

    `from config_base import *` した後に設計が上書きしても、**config_base の
    中からの呼び出しは base 側を見る**（Python の名前解決はモジュール単位）。
    `core_size` だけ上書きして `chip_core_box` が base を呼ぶ、のような
    「途中まで効いている」事故を避けるため、チェーンはここを通す。
    """
    fn = _NS.get(name) if _NS else None
    return fn if callable(fn) else globals()[name]


def core_size():
    _, stack_h = _f("row_y")()
    return _g("CORE_WIDTH_UM"), stack_h


def macro_box():
    if _g("MACRO_MODE") == "none":
        return (0.0, 0.0, 0.0, 0.0)
    raise SystemExit("macro_box(): マクロを使う設計は config.py で上書きすること")


def side_bus_x():
    return []


def power_bars():
    return []


def chip_core_box():
    w, h = _f("core_size")()
    return (0.0, 0.0, w, h)


def chip_core_height():
    _, b, _, t = _f("chip_core_box")()
    return round(t - b, 3)


def artifact(basename):
    return os.path.join(_g("LAYOUT"), basename)


def channel_heights(placement_json=None):
    import json
    return json.load(open(placement_json or _g("PLACEMENT_JSON")))["ch_heights"]


# ---- 検証 ----------------------------------------------------------------
def check():
    """フロアプランの内部矛盾を潰す。finalize() が毎回呼ぶ。"""
    msg = []
    nr, ch = _g("N_ROWS"), _g("CH_HEIGHTS")
    cw, rw = _g("CORE_WIDTH_UM"), _g("ROW_WIDTH_UM")
    tap_x, tap_w, pitch = _g("TAP_X"), _g("TAP_W"), _g("TAP_PITCH")
    site = _g("SITE_UM")

    if len(ch) != nr + 1:
        msg.append(f"CH_HEIGHTS は {nr+1} 本要る（今 {len(ch)}）")
    # ★ ch の上下端はサイトグリッドに乗せる。乗っていないと ch0 の最上
    #   トラックが行の M1 に寄る（APR_2026 で 131.6/153.2 のまま回して
    #   M1 間隔違反 3 件が step10 まで残った。docs/22_flow_route.md §…）。
    #   ただし**必ず違反になるわけではない**（TD4 は 250.0 / 85.4 で DRC 0）。
    #   既提出設計を再現するときは `CH_END_OFF_GRID_OK = True` で警告に落とす。
    off_grid = [v for v in (ch[0], ch[-1])
                if abs(v / site - round(v / site)) > 1e-9]
    if off_grid:
        note = (f"CH_HEIGHTS の端 {off_grid} が {site} の倍数でない "
                "（ch0 の最上トラックが行の M1 に寄って間隔違反が出る）")
        if _g("CH_END_OFF_GRID_OK"):
            print(f"  ** config: {note}\n"
                  f"     -> CH_END_OFF_GRID_OK で承知のうえ。DRC で必ず確かめること")
        else:
            msg.append(note)
    if rw > cw + 1e-6:
        msg.append(f"行幅 {rw} がコア幅 {cw} を超える")
    if abs(cw / site - round(cw / site)) > 1e-9:
        msg.append(f"コア幅 {cw} がサイトグリッド {site} に乗っていない")
    if cw + 2 * rules.NWELL_OVERHANG_X > rules.FRAME_OPENING_UM + 1e-6:
        msg.append(f"コア bbox({cw}+12.6) がフレーム開口 {rules.FRAME_OPENING_UM} を超える")
    if any(abs(t / site - round(t / site)) > 1e-9 for t in tap_x):
        msg.append("TAP_X がサイトグリッドに乗っていない")
    if tap_x and tap_x[-1] + tap_w > rw + 1e-6:
        msg.append(f"行末の TAP ({tap_x[-1]} + {tap_w}) が行幅 {rw} を超える")
    gaps = [round(b - a, 3) for a, b in zip(tap_x, tap_x[1:])]
    if gaps and max(gaps) > pitch + 1e-6:
        msg.append(f"TAP の最大間隔 {max(gaps)} が TAP_PITCH {pitch} を超える"
                   f"（間隔 {gaps}）— docs/03_core_geometry.md §2")
    if _g("TRACK_PITCH") < rules.TRACK_PITCH_MIN - 1e-9:
        msg.append(f"TRACK_PITCH {_g('TRACK_PITCH')} が下限 {rules.TRACK_PITCH_MIN} 未満")
    if msg:
        raise SystemExit("config: フロアプランが矛盾している\n  - " + "\n  - ".join(msg))


def check_bbox(native_bbox):
    """配置後の native bbox がコア幅から想定どおりはみ出しているか。
    `(l, b, r, t)` を渡す。`docs/03_core_geometry.md` §1-1。"""
    l, _, r, _ = native_bbox
    over = round((r - l) - _g("CORE_WIDTH_UM"), 3)
    ok = {0.0, rules.NWELL_OVERHANG_X, 2 * rules.NWELL_OVERHANG_X}
    if not any(abs(over - v) < 1e-6 for v in ok):
        raise SystemExit(f"native bbox のはみ出し {over} が想定外（{sorted(ok)}）")
    return over


# ---- finalize ------------------------------------------------------------
def finalize(ns):
    """設計の `config.py` の末尾で `finalize(globals())` と呼ぶ。"""
    global _NS
    ns.setdefault("ROOT", ROOT)
    root = ns["ROOT"]

    # コア幅 -- トラック本数から導出（`docs/03_core_geometry.md`）
    tp = ns.setdefault("TRACK_PITCH", TRACK_PITCH)
    ns["CORE_WIDTH_UM"] = round(ns.setdefault("CORE_WIDTH_TRACKS",
                                              CORE_WIDTH_TRACKS) * tp, 3)
    # 縦置きマクロは行スタックの**右**に並ぶので、行幅はコア幅から
    # マクロ本体と帯（縦 M2 バス + 余り）を引いた残り。
    #   帯 = SIDE_BUS_SLACK + SIDE_BUS_TRACKS x SITE
    # コア幅 1600 を超えるとフレーム開口が 1840 -> 1600 に落ちるので、
    # **コア幅は動かさず行幅で吸収する**（docs/11_frame_io.md）。
    if ns.get("MACRO_MODE") == "portrait":
        ns["SIDE_BUS_TRACKS"] = ns.get("SIDE_BUS_TRACKS", SIDE_BUS_TRACKS)
        ns["SIDE_BUS_SLACK"] = ns.get("SIDE_BUS_SLACK", SIDE_BUS_SLACK)
        # ★ ここは setdefault にしない。`from config_base import *` で
        #   `MACRO_SIDE_GAP = 0.0` が設計の名前空間に**もう入っている**ので、
        #   setdefault は必ず空振りして 0.0 のままになる（2026-09-15 に踏んだ）。
        #   縦置きの帯幅は定義そのものなので、ここで決めてしまう。
        #   幅を変えたい設計は SIDE_BUS_TRACKS / SIDE_BUS_SLACK を動かす。
        ns["MACRO_SIDE_GAP"] = round(ns["SIDE_BUS_SLACK"]
                                     + ns["SIDE_BUS_TRACKS"] * SITE_UM, 3)
        ns.setdefault("ROW_WIDTH_UM",
                      round(ns["CORE_WIDTH_UM"] - ns["MACRO_W"]
                            - ns["MACRO_SIDE_GAP"], 3))
    ns.setdefault("ROW_WIDTH_UM", ns["CORE_WIDTH_UM"])
    ns.setdefault("TAP_X", tap_columns(ns["ROW_WIDTH_UM"],
                                       ns.setdefault("TAP_PITCH", TAP_PITCH),
                                       ns.setdefault("TAP_W", TAP_W)))
    ns["TAP_X_DEFAULT"] = list(ns["TAP_X"])
    # ★ コアのオフセットは「行幅の半分」ではなく「native bbox の中心」。
    #   配置後に chip_geometry() が実測して上書きする。ここは参考値。
    ns["CORE_OFFSET_X_NOMINAL"] = round(-ns["CORE_WIDTH_UM"] / 2.0, 3)

    # ---- 配置の再現に効くパラメータ -------------------------------------
    # **フラグや環境変数に頼らない。** 提出した配置を作った値は設計の
    # config.py に書く（`PAD_WEIGHT` を export し忘れた 1 回だけが別の配置に
    # なる、という事故を 2026-09-15 に実際に起こした。`docs/40_gotchas.md` §4-3）。
    # 優先順は **環境変数 > config.py > 既定**（掃引は環境変数で回す）。
    for _k, _d, _c in (("PAD_WEIGHT", 1.0, float), ("PLACE_SEED", 7, int),
                       ("PLACE_RESTARTS", 800, int),
                       ("PLACE_ORDER_PASSES", 40, int),
                       ("PLACE_BALANCE_TOL", 0.02, float)):
        ns.setdefault(_k, _d)
        _v = getenv(_k)
        if _v is not None:
            ns[_k] = _c(_v)

    # チャネル予算
    env_ch = getenv("CH_HEIGHTS")
    if env_ch:
        ns["CH_HEIGHTS"] = [float(v) for v in env_ch.split(",")]
    elif ns.get("CH_HEIGHTS") is None:
        nr = ns.setdefault("N_ROWS", N_ROWS)
        ns["CH_HEIGHTS"] = [140.4] + [700.0] * (nr - 1) + [162.0]
    ns.setdefault("ROUTE_CH_HEIGHTS", list(ns["CH_HEIGHTS"]))

    # パス
    ns.setdefault("LAYOUT", os.path.join(root, "layout"))
    lay = ns["LAYOUT"]
    sc = os.path.join(APR_ROOT, "stdcell", ns.setdefault("STDCELL", STDCELL))
    ns.setdefault("LIB_LEF", os.path.join(sc, "TR-1um_cells.lef"))
    ns.setdefault("LIB_GDS", os.path.join(sc, "TR-1um_STDCELL.gds"))
    ns.setdefault("LEF_PATH", os.path.join(sc, "TR-1um_PNR.lef"))
    ns.setdefault("CELL_GDS", os.path.join(sc, "TR-1um_PNR.gds"))
    ns.setdefault("LIBERTY", os.path.join(sc, "tr1um_typ_5v0_25c.lib"))
    ns.setdefault("LOGO_BITMAP", os.path.join(APR_ROOT, "art", "opensusi_logo.txt"))
    # ★ フレームは PDK から参照する（コピーしない）。生成物は設計の作業ディレクトリへ。
    if "FRAME_GDS" not in ns:
        try:
            ns["FRAME_GDS"] = pdk_frame_gds()
        except SystemExit:
            ns["FRAME_GDS"] = None              # PDK が無い環境。使う側でエラーにする
    ns.setdefault("FRAME_LEF", os.path.join(lay, "frame", "TR-1um_frame.lef"))
    ns.setdefault("RING_OSC_GDS", os.path.join(APR_ROOT, "macro", "ringosc", "RING_OSC.gds"))
    ns.setdefault("RING_OSC_LEF", os.path.join(APR_ROOT, "macro", "ringosc", "RING_OSC.lef"))
    ns.setdefault("RING_OSC_CELL", "RING_OSC")
    ns.setdefault("RING_OSC_ORIGIN", None)      # 載せる設計だけが (x, y) を与える
    # ★ 「RING_OSC を載せるか」の単一の判定。`RING_OSC_CELL` は既定で
    #   名前が入っているので、**セル名の有無で判定してはいけない**。
    ns["HAS_RING_OSC"] = ns["RING_OSC_ORIGIN"] is not None

    # セル寸法表。**中身は STDCELL の性質**（LEF の SIZE と GDS の prBoundary）
    # なので正本は `stdcell/<世代>/cell_info.json`。ただし**既提出設計が持って
    # いる `layout/cell_info.json` を黙って置き換えない**（TD4 は MEMPORT の
    # 高さが 550.8 で、APRtools 側の 502.2 と違う）。設計側にあればそちらが勝つ。
    # どちらを使ったかは `selfcheck.py` が出す。
    if not ns.get("CELL_INFO"):
        _design_ci = os.path.join(lay, "cell_info.json")
        # ★ ここで `stdcell_file()` は呼べない。`_NS` はまだ None で、
        #   `stdcell_dir()` -> `_g("STDCELL")` が落ちる（SYN_LIB と同じ書き方にする）。
        ns["CELL_INFO"] = _design_ci if os.path.exists(_design_ci) else os.path.join(
            APR_ROOT, "stdcell", ns.setdefault("STDCELL", STDCELL), "cell_info.json")
    ns.setdefault("PLACEMENT_JSON", os.path.join(lay, "placement.json"))
    ns.setdefault("PLACEMENT_GDS", os.path.join(lay, "step5", "route_step_1_placement.gds"))
    ns.setdefault("ROUTED_RAW_GDS", os.path.join(lay, "step6", "route_step_2_routed_raw.gds"))
    ns.setdefault("RIPUP_GDS", os.path.join(lay, "step7", "route_step_3_ripup_reroute.gds"))
    ns.setdefault("TOPPINS_GDS", os.path.join(lay, "step8", "route_step_4_top_pins.gds"))
    ns.setdefault("POWERPINS_GDS", os.path.join(lay, "step9", "route_step_5_power_pins.gds"))
    # ---- チップ組み立ての連鎖 -------------------------------------------
    # 段の順番は**設計で違う**。APR_2026 はロゴを配線の前に置き
    #   assemble -> ringosc -> logo -> route_chip -> add_top_pins
    # TD4 はロゴが最後で
    #   assemble -> route_chip -> add_top_pins -> logo
    # 各スクリプトが自分のファイル名を直書きしていたので、TD4 を回すと
    # 「step1c_logo.gds が無い」で止まった（2026-09-15）。ここで名前を持つ。
    chip = ns.setdefault("CHIP", os.path.join(lay, "chip"))
    ns.setdefault("CHIP_ASSEMBLED_GDS", os.path.join(chip, "step1_assembled.gds"))
    ns.setdefault("CHIP_RINGOSC_GDS", os.path.join(chip, "step1b_ringosc.gds"))
    ns.setdefault("CHIP_LOGO_IN_GDS", ns["CHIP_RINGOSC_GDS"])
    ns.setdefault("CHIP_LOGO_OUT_GDS", os.path.join(chip, "step1c_logo.gds"))
    ns.setdefault("CHIP_ROUTE_IN_GDS", ns["CHIP_LOGO_OUT_GDS"])
    ns.setdefault("CHIP_ROUTED_GDS", os.path.join(chip, "step2_routed.gds"))
    ns.setdefault("CHIP_TOPPINS_GDS", os.path.join(chip, "step3_top_pins.gds"))
    # 提出に載せる最終 GDS（ロゴが最後の設計は step4_final）
    ns.setdefault("CHIP_FINAL_GDS", ns["CHIP_TOPPINS_GDS"])

    # ---- 合成 / STA ------------------------------------------------------
    ns["SYN_LIB"] = ns.get("SYN_LIB") or os.path.join(
        APR_ROOT, "stdcell", ns.setdefault("STDCELL", STDCELL),
        "tr1um_typ_5v0_25c.lib")
    ns["SYN_TOP"] = ns.get("SYN_TOP") or ns["TOP_CELL_NAME"]
    # ★ setdefault は使わない。`from config_base import *` で既定値が設計の
    #   名前空間に入っているので必ず空振りする（docs/08_migration_td4.md #3）。
    ns["SYN_OUT_DIR"] = ns.get("SYN_OUT_DIR") or os.path.join(ns["ROOT"], "out")
    ns["SYN_CONSTR"] = ns.get("SYN_CONSTR") or os.path.join(APR_ROOT, "syn", "abc.constr")
    ns["NET_PATH"] = ns.get("NET_PATH") or os.path.join(
        ns["SYN_OUT_DIR"], ns["SYN_TOP"] + "_pnr.v")
    ns.setdefault("SQUEEZED_GDS", os.path.join(lay, "step10", "route_step_6_squeezed.gds"))
    ns.setdefault("MACROPWR_GDS", os.path.join(lay, "step11", "route_step_7_macro_power.gds"))
    for key, base in (("PIN_MAP_JSON", "pin_map.json"),
                      ("PIN_MAP_RR_JSON", "pin_map_rr.json"),
                      ("PIN_MAP_SQ_JSON", "pin_map_sq.json"),
                      ("PIN_MAP_TP_JSON", "pin_map_tp.json"),
                      ("NET_SHAPES_JSON", "net_shapes.json"),
                      ("NET_SHAPES_RR_JSON", "net_shapes_rr.json"),
                      ("NET_SHAPES_SQ_JSON", "net_shapes_sq.json"),
                      ("NET_SHAPES_TP_JSON", "net_shapes_tp.json"),
                      ("NET_SHAPES_TP2_JSON", "net_shapes_tp2.json"),
                      ("CHANNEL_USAGE_JSON", "channel_usage.json"),
                      ("FORCE_JOG_EVENTS_JSON", "force_jog_events.json"),
                      ("PER_ROW_SPINE_JSON", "per_row_spine_events.json"),
                      ("COMPACTION_INFO_JSON", "compaction_info.json")):
        ns.setdefault(key, os.path.join(lay, base))

    ns.setdefault("FINAL_GDS", ns["MACROPWR_GDS"] if ns.get("MACRO_POWER")
                  else ns["SQUEEZED_GDS"])
    ns.setdefault("CHIP", os.path.join(lay, "chip"))
    # ★ 中間成果物の取り違え防止（TD4 が step10 を載せた事故）
    ns.setdefault("CHIP_CORE_GDS",
                  ns["MACROPWR_GDS"] if os.path.exists(ns["MACROPWR_GDS"])
                  else ns["FINAL_GDS"])

    _NS = ns
    check()
    return ns


# ---- フレームの実ジオメトリ（LEF の OBS ではなく図形を測る）-------------
# ★ `docs/10_pdk_facts.md` §7 / `docs/40_gotchas.md` §0-2
_FRAME_REGION = {}


def frame_region(gds=None, cell=None):
    """フレームの実ジオメトリ（`FRAME_HARD_LAYERS` の和）。結果はキャッシュ。"""
    import klayout.db as db
    key = (gds or _g("FRAME_GDS"), cell or _g("FRAME_CELL"))
    if key[0] is None:
        raise SystemExit("FRAME_GDS が解決できていない（TR1UM_PDK を設定すること）")
    if key not in _FRAME_REGION:
        ly = db.Layout()
        ly.read(key[0])
        top = ly.cell(key[1])
        if top is None:
            raise SystemExit(f"{key[1]} が {key[0]} に無い")
        r = db.Region()
        for lay in _g("FRAME_HARD_LAYERS", rules.FRAME_HARD_LAYERS):
            r += db.Region(top.begin_shapes_rec(ly.layer(*lay)))
        r.merge()
        _FRAME_REGION[key] = (r, ly.dbu)
    return _FRAME_REGION[key]


def frame_clear(x0, y0, x1, y1, gds=None, cell=None):
    """その矩形がフレームの実ジオメトリと重ならないか。"""
    import klayout.db as db
    r, u = frame_region(gds, cell)
    box = db.Region(db.Box(int(round(x0 / u)), int(round(y0 / u)),
                           int(round(x1 / u)), int(round(y1 / u))))
    return (r & box).is_empty()


def frame_opening(width_um=None, gds=None, cell=None):
    """幅 width_um のコアが収まる最大の y 帯（ダイ中心基準）。**実ジオメトリ実測。**

    実測: 原点中心 1840 x 1840 は全層で完全に空き、1844 で当たる。
    開口は**四隅まで含めて 1840 角**。LEF の OBS が作る「崖」は実在しない。
    """
    w = width_um if width_um is not None else _g("CORE_WIDTH_UM")
    lo, hi = 0.0, rules.DIE_HALF
    for _ in range(40):
        mid = (lo + hi) / 2
        if frame_clear(-w / 2, -mid, w / 2, mid, gds, cell):
            lo = mid
        else:
            hi = mid
    return (-round(lo, 3), round(lo, 3))


def frame_inner_wall(box, gds=None, cell=None):
    """コアの箱の四方で、フレームの実ジオメトリが来ている位置。"""
    import klayout.db as db
    r, u = frame_region(gds, cell)
    x0, y0, x1, y1 = box
    d = rules.DIE_HALF
    out = {}
    for side, probe in (("left", (-d, y0, x0, y1)), ("right", (x1, y0, d, y1)),
                        ("bottom", (x0, -d, x1, y0)), ("top", (x0, y1, x1, d))):
        reg = r & db.Region(db.Box(int(round(probe[0] / u)), int(round(probe[1] / u)),
                                   int(round(probe[2] / u)), int(round(probe[3] / u))))
        if reg.is_empty():
            out[side] = None
            continue
        b = reg.bbox()
        out[side] = {"left": b.right * u, "right": b.left * u,
                     "bottom": b.top * u, "top": b.bottom * u}[side]
    return out


def frame_obs_rects(lef=None):
    """`OSS_FRAME_GIO` の OBS 矩形（ダイ中心が原点）。**比較用。設計の根拠にしない。**"""
    import re
    path = lef or _g("FRAME_LEF")
    if not path or not os.path.exists(path):
        # LEF は PDK の GDS から `apr/mkleffrm.py` が生成する派生物
        return (rules.DIE_UM, [])
    txt = open(path).read()
    fc = _g("FRAME_CELL")
    body = re.search(rf"MACRO {fc}(.*?)END {fc}", txt, re.S).group(1)
    m = re.search(r"OBS(.*?)END", body, re.S)
    die = float(re.search(r"SIZE\s+([\d.]+)\s+BY", body).group(1))
    c = die / 2
    if not m:
        return die, []
    return die, sorted({tuple(float(v) - c for v in q) for q in
                        re.findall(r"RECT\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)"
                                   r"\s+(-?[\d.]+)\s*;", m.group(1))})


def core_bbox_um(gds=None, cell=None):
    """配置配線済みコアの native bbox（GDS 実測）。"""
    import klayout.db as db
    path = gds or _g("FINAL_GDS")
    name = cell or _g("TOP_CELL_NAME")
    ly = db.Layout()
    ly.read(path)
    c = ly.cell(name)
    if c is None:
        raise SystemExit(f"{name} が {path} に無い")
    b = c.bbox()
    return (b.left * ly.dbu, b.bottom * ly.dbu, b.right * ly.dbu, b.top * ly.dbu)


# ---- ロゴ / RING_OSC / 縦積み -------------------------------------------
def logo_size():
    """ビットマップから実寸 (幅, 高さ)。**決め打ちにしない。**"""
    com = rules.LOGO_COMMENT
    rows = [l.rstrip("\n") for l in open(_g("LOGO_BITMAP"), encoding="utf-8")
            if not l.startswith(com) and l.strip()]
    w, h = max(len(r) for r in rows), len(rows)
    p, d = _g("LOGO_PITCH", rules.LOGO_PITCH), _g("LOGO_DOT", rules.LOGO_DOT)
    return (round((w - 1) * p + d, 3), round((h - 1) * p + d, 3))


def ringosc_box():
    """RING_OSC の絶対フットプリント。載せない設計では None。"""
    origin = _g("RING_OSC_ORIGIN")
    if origin is None:
        return None
    import klayout.db as db
    ly = db.Layout()
    ly.read(_g("RING_OSC_GDS"))
    c = ly.cell(_g("RING_OSC_CELL"))
    b, u = c.bbox(), ly.dbu
    ox, oy = origin
    return (ox + b.left * u, oy + b.bottom * u, ox + b.right * u, oy + b.top * u)


def logo_box():
    """ロゴの帯。RING_OSC を載せる設計ではその上、そうでなければコアの下。

    **空き地の位置は設計で違う**ので、`config.py` が `LOGO_BOX` を持っていれば
    それを使う（TD4 はコア右下の空き (410,-680)-(790,-470)。U30）。
    """
    box = _g("LOGO_BOX")
    if box:
        return tuple(box)
    w, h = logo_size()
    ro = ringosc_box()
    y0 = round(ro[3] + _g("LOGO_GAP", 20.0), 3) if ro else _g("LOGO_Y0", 0.0)
    return (round(-w / 2, 3), y0, round(w / 2, 3), round(y0 + h, 3))


def core_bottom_y():
    """コアの下端（チップ座標）。縦積みしない設計では None（= 中央寄せ）。"""
    if _g("RING_OSC_ORIGIN") is None and not _g("STACK_BELOW_CORE", False):
        return None
    return round(logo_box()[3] + _g("CORE_LOGO_GAP", 20.0), 3)


def chip_geometry(gds=None, cell=None):
    """コアをパッドリングの開口に落としたときの寸法一式。

    ★ オフセットは **native bbox の中心**（行幅の半分ではない）。
      `docs/03_core_geometry.md` §1-1。
    ★ 壁は**実ジオメトリ**で測る。LEF の OBS は使わない。
    """
    l, b, r, t = core_bbox_um(gds or _g("CHIP_CORE_GDS"), cell)
    check_bbox((l, b, r, t))
    ox = round(-(l + r) / 2.0, 3)
    cb = core_bottom_y()
    oy = round(-(b + t) / 2.0, 3) if cb is None else round(cb - b, 3)
    box = (round(l + ox, 3), round(b + oy, 3), round(r + ox, 3), round(t + oy, 3))
    w = frame_inner_wall(box)
    gp = _g("GIO_PIN_RADIUS", rules.GIO_PIN_RADIUS)
    return {
        "die": rules.DIE_UM,
        "core_offset": (ox, oy),
        "core_native_bbox": (l, b, r, t),
        "core_chip_bbox": box,
        "wall": {k: (round(v, 3) if v is not None else None) for k, v in w.items()},
        "channel_left": (round(box[0] - w["left"], 3) if w["left"] is not None else None,
                         round(box[0] + gp, 3)),
        "channel_right": (round(w["right"] - box[2], 3) if w["right"] is not None else None,
                          round(gp - box[2], 3)),
        "channel_bottom": (round(box[1] - w["bottom"], 3) if w["bottom"] is not None else None,
                           round(box[1] + gp, 3)),
        "channel_top": (round(w["top"] - box[3], 3) if w["top"] is not None else None,
                        round(gp - box[3], 3)),
    }


def chip_fits(geom=None):
    """コアがフレームの実ジオメトリと重ならないか。[(理由, 情報)]（空なら OK）。"""
    g = geom or chip_geometry()
    box = g["core_chip_bbox"]
    return [] if frame_clear(*box) else [("コアがフレームの実ジオメトリと重なる", box)]


def check_opening():
    """圧縮後のコア高がフレーム開口に収まるか。**配線が終わってから**使う。"""
    lo, hi = frame_opening(_g("CORE_WIDTH_UM"))
    h = chip_core_height()
    return h, hi - lo, (hi - lo) - h

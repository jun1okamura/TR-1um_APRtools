"""rules.py -- TR-1um のプロセス定数の単一ソース。

ここに書いてある値の出典は `docs/10_pdk_facts.md`。**数値を他所に書き写さない。**
以前は DRC 値が `drc_check.py` / `check_chip.py` / `drc_check_cells.py` /
`place_logo.py` の 4 箇所に散っていて、しかも `drc_check_cells.py` だけ値が違った。

出典:
  レイヤ番号      $TR1UM_PDK/libs.tech/klayout/tech/drc/00_Layers.drc
  設計規則        $TR1UM_PDK/Document/TR-1um_Drawing_Layer_DR_Table.csv
                  $TR1UM_PDK/libs.tech/klayout/tech/drc/run.drc（実装）
  グリッド        stdcell/v59_4/TR-1um_tech.lef
"""

# ---- GDS レイヤ（00_Layers.drc）------------------------------------------
WN = (140, 0)          # N-well
AP = (3, 1)            # 活性 P
AN = (3, 2)            # 活性 N
AR = (3, 3)            # 抵抗の活性
AC = (3, 4)            # 容量の活性
GC = (8, 1)            # ゲートポリ
GR = (8, 2)            # 抵抗ポリ
CO = (11, 0)           # コンタクト
M1 = (13, 0)           # メタル1 -- 水平
V1 = (19, 0)           # ビア1
M2 = (20, 0)           # メタル2 -- 垂直
PO = (14, 0)           # パッド開口

# ★ DRC / LVS がテキストを拾うのはこの 2 層だけ（labels(48,0) / labels(49,0)）
M1_LBL = (48, 0)
M2_LBL = (49, 0)

# 自作フローが使う層（PDK の DRC は見ない）
M1_PIN = (48, 1)
M2_PIN = (49, 1)
PRBOUNDARY = (235, 0)
PTECT = (63, 1)        # キープアウト認識（PDK 側の定義と同じ）
MASK = (63, 0)         # DRC 除外
SCRB_MARK = (80, 0)    # スクライブ認識（デッキの `TEMP`）。**セルには無い**。
                       # デッキは全層を `input(...).not(MASK + SCRB)` で読む
                       # ので、生の層で比べると偽陽性が出る（U55）。
ESD_RECOG = (63, 2)

# 可視化・診断専用
CH_ANNOT = (250, 0)
CH_BAR = (250, 1)
CH_LABEL = (250, 2)
TOPPIN_DIAG = (260, 2)
TOPPIN_DIAG2 = (260, 3)

LABEL_LAYER = {"M1": M1_LBL, "M2": M2_LBL}
PIN_LAYER = {"M1": M1_PIN, "M2": M2_PIN}
WIRE_LAYER = {"M1": M1, "M2": M2}

# ---- BEOL 設計規則 -------------------------------------------------------
# 判定は「**未満が違反**」= ちょうどは合法（ロゴのドット設計がこれに依存）。
M1_WIDTH_MIN = 1.8         # M1.W1
M1_SPACE_MIN = 1.4         # M1.S1
M2_WIDTH_MIN = 3.0         # M2.W1
M2_SPACE_MIN = 2.0         # M2.S1
V1_CUT = 1.4               # V1.W1  幅・bbox_min・bbox_max すべて 1.4 ちょうど
V1_SPACE_MIN = 1.5         # V1.S1
V1_ENC_M1 = 1.0            # V1.M1
V1_ENC_M2 = 1.0            # M2.V1
V1_GA_SPACE_MIN = 1.2      # V1.GA（GA = GC + GR。重なりは即違反）

# ★ 自作チェッカが実装していないが PDK デッキにはあるルール。
#   `docs/10_pdk_facts.md` §3-2 / `docs/40_gotchas.md` §2-4
# ★ **ちょうど 10.0 は M1(W) ではない**（U18、2026-09-17 に実測）。
#   デッキの M1W = M1.sized(-5.0).merged.sized(5.0).merged は
#   幅 10.000 を幅 0 に潰して落とす。**10.000 を超えたら**（1 dbu = 0.001 でも）
#   M1(W) になり、接する M1 に 2.0 を要求する。
#   電源バー（CHIP_BUS_W / POWER_BAR_W / RO_VSS_BAR_W）は 10.0 ちょうどで、
#   **境界の内側**にいる（余裕は MFG_GRID 1 つ分）。
#   探針は mk_drc_probe.py の T_SW_10 / T_SW_10p / T_SW_TEE。デッキで確認済み。
M1_WIDE_MIN = 10.0         # M1.W2  これを**超える**と M1(W)
# ★ 製造グリッド。`01_Basics.drc` が 12 層すべてに `ongrid(0.050)` を掛けており、
#   外れると `ERR01: OFFGRID 0.050`。**DBU（0.001）は座標の刻みであって、
#   作れる刻みではない。** したがって 10.0 の電源バーの次に作れる幅は 10.050 で、
#   `M1(W)` までの余裕は 1 dbu ではなく **0.050 µm**（U18 / U84、2026-09-17）。
MFG_GRID = 0.05            # ERR01
M1_WIDE_SPACE_MIN = 2.0    # M1.SW  M1(W) に接する M1 は 2.0 必要（1.4 ではない）
METAL_WIDTH_MAX = 45.0     # M1.W3 / M2.W3（パッド部と AC は除外）
SCRIBE_SPACE_MIN = 5.0     # M1.SCR / M2.SCR

# FEOL で P&R に効くもの
GC_WIDTH_MIN = 1.0         # GC.W1 = 最小ゲート長
GC_SPACE_MIN = 1.2         # GC.S1
CO_SIZE = 1.0              # CO.W1 / CO.WM
CO_SPACE_MIN = 1.0         # CO.S1
WN_WIDTH_MIN = 8.0         # WN.W1
WN_SPACE_MIN = 4.0         # WN.S1

# N-well が prBoundary からはみ出す量（WN.S1 と AP.WN の帰結）。
# **両端のセル次第で片側だけのこともある。bbox は実測すること。**
NWELL_OVERHANG_X = 6.3
NWELL_OVERHANG_Y = 4.0

# ---- グリッド（TR-1um_tech.lef）-----------------------------------------
SITE_W = 5.4               # SITE TR1UM の幅 = ポリピッチ
TRACK_PITCH = 5.4          # チャネルの M1 トラック間隔（下限。下記）
TRACK0_OFFSET = 2.0
M2_TRACK_OFFSET = 2.7      # セル内 M2 は prBoundary 左端から 2.7 + n*5.4
VIA_PAD = 3.4              # via_1 PCell の M1/M2 パッド（±1.7）
M1_TRUNK_WIDTH = 1.8
M2_WIRE_WIDTH = 3.4

# トラックピッチ 5.4 の根拠:
#   via_1 は M1/M2 の両方に 3.4 角のパッドを置く。隣接トラックの via が
#   同じ x に来たときの拘束は M1: 3.4+1.4=4.8 / M2: 3.4+2.0=5.4 -> 5.4 が効く。
#   5.0 にすると M2 間隔違反が dy=1.6 dx=3.4 で出る（実測）。
TRACK_PITCH_MIN = round(VIA_PAD + M2_SPACE_MIN, 3)

# 同じネットでも via のカット間隔は効く: カット 1.4 + 間隔 1.5
VIA_CENTER_MIN = round(V1_CUT + V1_SPACE_MIN, 3)

# ---- 方向規則 ------------------------------------------------------------
# 水平は M1、垂直は M2。層が変わるところに必ず via_1。
# これを守ると全ての交差が M1 x M2 になり、繋ぎたい所にだけ via が現れる。
HORIZONTAL_LAYER = "M1"
VERTICAL_LAYER = "M2"

# ---- ピンとラベル --------------------------------------------------------
PIN_MARKER_UM = 3.0        # ピンマーカーは 3.0 x 3.0 の正方形
PIN_TEXT_UM = 20.0         # ラベルはサイズ 20 の TEXT を**箱の中心**に

# ---- 電源ネット名 --------------------------------------------------------
# 自作フローが名前を決める場所は全て小文字（`docs/04_naming.md` §1）。
PWR_NET = "vdd"
GND_NET = "vss"
# フレーム由来。**変更不可**（OSS_FRAME_GIO の LEF ピン名）。
PAD_PWR = "VDD"
PAD_GND = "VSS"
# ★ SPICE は大小を区別しない。大小だけで別ネットを作れない。

# ---- コア側とチップ側の境界（U21）---------------------------------------
# コアの中は小文字（`PWR_NET` / `GND_NET`）、チップの中はフレームに合わせて
# 大文字。**その 2 つを繋ぐ写像はここ 1 箇所だけ**に置く。
# 以前は `route_chip.core_power_pins()` と `verify_chip.py` が別々に
# 書いていて、`verify_chip` の方が小文字を見落として**照合が一度も
# 動いていなかった**（「コアの電源タップ 0 本を確認」と出して通っていた）。
CHIP_PWR_RAIL = "VDD"
CHIP_GND_RAIL = "GND"        # チップ側は GND。フレームのピン名 VSS とは別
# コアのラベル -> チップ側のレール名。旧世代のコア（大文字ラベル）も読める。
RAIL_OF = {PWR_NET: CHIP_PWR_RAIL, GND_NET: CHIP_GND_RAIL,
           "VDD": CHIP_PWR_RAIL, "GND": CHIP_GND_RAIL, PAD_GND: CHIP_GND_RAIL}
# チップ側のレール名 -> コアが実際に書いているラベル（照合はこちら向き）。
CORE_LABEL_OF = {CHIP_PWR_RAIL: PWR_NET, CHIP_GND_RAIL: GND_NET}

# ---- チップの縦の積み方（フレーム実測 + V10 の形）------------------------
# ★ ここが**詰まっているときに順番に破綻する**ところ（U46）。SCLK_SPI で
#   全信号を上辺から出したら 3 回続けて落ちた:
#     (1) レーン帯が GND リングに当たる
#     (2) リングを外へ寄せたら via が重なって V1.W1
#     (3) レーンを内へ寄せたら電源バスと M1.S1
#   値は `config_base.chip_stack()` が検算する。
CHIP_RING_W = 10.0             # リングの幅（M1/M2 とも）
CHIP_GND_RING_R = 884.0        # 既定。設計は CHIP_GND_RING_R で動かせる
CHIP_VDD_RING_R = 902.0
CHIP_BUS_W = 10.0              # コアの電源を束ねる M1 バー
CHIP_LANE_R0 = 815.4           # 既定。レーン 0 の中心
CHIP_LANE_PITCH = SITE_W       # 5.4。コア内のトラックと同じ
CHIP_STRIP_W = 10.0            # パッド <-> バスのストリップ（V10 の形、5 本）
CHIP_STRIP_VIA = 6.8           # 10 µm どうしの重なりに収まる 2x2 カット
CHIP_VDD_CROSS_Y = 914.5       # M2 を止めて M1 に跳ねる y
CHIP_VDD_PIN_Y = 927.0         # フレームの M1 VDD ピン（x 50…350）
CHIP_VSS_LAND_Y = -926.0       # 下辺の VSS 壁ピン（x -450…50）

# ---- ロゴ ----------------------------------------------------------------
LOGO_PITCH = 5.0           # = M2 最小幅 3.0 + 最小スペース 2.0
LOGO_DOT = 3.0             # 直交隣接 2.0 / 斜め 2.83 -- どちらも合法
LOGO_COMMENT = "%"         # ★ '#' は ON セルそのもの

# ---- ダイ ----------------------------------------------------------------
DIE_UM = 2500.0
DIE_HALF = 1250.0
DBU = 0.001
FRAME_OPENING_UM = 1840.0  # 四隅まで含めて正方形（GDS 実測。LEF の OBS は使わない）
GIO_PIN_RADIUS = 921.7     # P / HIZ / OUT 端子とVSS 壁ピンの半径
FRAME_INNER_WALL = 920.0   # M1 / M2 / WN / ピンの内壁

# 「コアが当たってはいけない」層（ウェルも含む）
FRAME_HARD_LAYERS = (AP, AN, GC, CO, M1, PO, V1, M2, M1_PIN, M2_PIN, WN)


def drc_rules():
    """自作 DRC チェッカに渡す辞書。**値はここからしか取らない。**"""
    return {
        "M1_W": M1_WIDTH_MIN, "M1_S": M1_SPACE_MIN,
        "M2_W": M2_WIDTH_MIN, "M2_S": M2_SPACE_MIN,
        "V1_CUT": V1_CUT, "V1_S": V1_SPACE_MIN,
        "V1_ENC_M1": V1_ENC_M1, "V1_ENC_M2": V1_ENC_M2,
        "V1_GA_S": V1_GA_SPACE_MIN,
    }

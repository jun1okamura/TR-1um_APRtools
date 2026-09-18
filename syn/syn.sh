#!/bin/sh
# TR-1um: 合成 → 実セルへのマッピング → 後処理 → 検証 → 面積 → STA
#
#   usage: sh $APRTOOLS/syn/syn.sh          （設計のルートで。引数は要らない）
#          PER=2500 sh $APRTOOLS/syn/syn.sh （STA の周期だけ上書き）
#
# **設計ごとの値は全部 `config.py` から取る。** 以前は I2C の値（RTL の場所・
# トップ名・abc 制約・BUFTH のネット・V10 の参照ネットリスト）がこのファイルに
# 直書きで、TD4 と SCLK_SPI では回らなかった（`docs/40_gotchas.md` §4-0d）。
#
# 段は config.py が与えたものだけ回る:
#
#   0  セルの Verilog モデル生成   SYN_CELLS_GEN のときだけ
#   1  RTL の機能検証（iverilog）  SYN_TB_RTL があるときだけ
#   2  合成 → 実セルへマッピング   SYN_RTL / SYN_LIB / SYN_CONSTR / SYN_BLACKBOX
#   3  重複ゲートの整理            常に（**必ず 4 の前**）
#   4  MUXDFFRB / RSLATCH へ畳む   常に
#   5  ゲートレベル TB             SYN_TB_NET があるときだけ
#   6  BUFTH で外部入力を受ける    BUFTH_NETS が空でないときだけ
#   7  面積と使用率                常に
#   8  既提出ネットリストと比較    SYN_REF_NETLIST があるときだけ
#   9  STA                         STA_CLK_PORT があるときだけ
#
# 出力は `SYN_OUT_DIR`（既定 `<設計>/out`）。最終ネットリストは `NET_PATH`。
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
APR=$(cd "$HERE/.." && pwd)/apr
PYTHONPATH=${PYTHONPATH:-$APR}; export PYTHONPATH

# --- 設計の config.py を読む -------------------------------------------------
CFG=$(python3 - <<'PY'
# ★ `apr_path` を先に通す。`config` という名前は仮想環境の pip パッケージ
#   にもあるので、素の `import config` は**別物を掴むことがある**（2026-09-18、
#   `.venv` で `AttributeError: module 'config' has no attribute 'SYN_TOP'`）。
#   `apr_path` は設計ルートの config.py を**名指しで**読み込む。
import apr_path  # noqa: F401
import os, config as c
def one(v):        return "" if v is None else str(v)
def many(v):       return " ".join(str(x) for x in (v or []))
print(one(c.SYN_TOP))                                   # 1
print(one(c.SYN_LIB))                                   # 2
print(many(c.SYN_RTL))                                  # 3
print(one(c.SYN_OUT_DIR))                               # 4
print(one(c.SYN_CONSTR))                                # 5
print(one(getattr(c, "SYN_CELLS_V", None)))             # 6
print(many(getattr(c, "SYN_CELLS_ARGS", [])))           # 7
print(many(getattr(c, "SYN_BLACKBOX", [])))             # 8
print(many(getattr(c, "SYN_TB_RTL", [])))               # 9
print(many(getattr(c, "SYN_TB_NET", [])))               # 10
print(many(getattr(c, "BUFTH_NETS", [])))               # 11
print(one(getattr(c, "SYN_REF_NETLIST", None)))         # 12
print(one(c.NET_PATH))                                  # 13
print(one(getattr(c, "STA_CLK_PORT", None)))            # 14
print(one(getattr(c, "STA_PERIOD_NS", "")))             # 15
print("1" if getattr(c, "SYN_CELLS_GEN", False) else "")        # 16
print("1" if getattr(c, "SYN_CELLS_IN_SYNTH", False) else "")   # 17
print(" ".join("-I" + d for d in (getattr(c, "SYN_TB_INCDIR", []) or [])))  # 18
print(one(c.ROOT))                                      # 19
print(one(getattr(c, "OUT_LOAD_CELL", "")))             # 20
print(one(getattr(c, "OUT_LOAD_PIN", "")))              # 21
print(one(getattr(c, "DRIVING_CELL", "")))              # 22
PY
) || { echo "config.py が読めない（設計のルートで、PYTHONPATH=\$APRTOOLS/apr）" >&2; exit 1; }
f() { echo "$CFG" | sed -n "$1p"; }
TOP=$(f 1);   LIB=$(f 2);       RTL=$(f 3);     OUT=$(f 4);   CONSTR=$(f 5)
CELLS=$(f 6); CELLS_ARGS=$(f 7); BLACKBOX=$(f 8)
TB_RTL=$(f 9); TB_NET=$(f 10);  BUFTH=$(f 11);  REF=$(f 12);  NET=$(f 13)
CLK=$(f 14);  PER=${PER:-$(f 15)}
CELLS_GEN=$(f 16); CELLS_SYN=$(f 17); INCDIR=$(f 18); ROOTDIR=$(f 19)
LOADCELL=$(f 20); LOADPIN=$(f 21); DRVCELL=$(f 22)
APRROOT=$(cd "$HERE/.." && pwd)

# 生成ログに**その機械の置き方を焼き付けない**（U35 / `config_base.disp()` と同じ規約）。
#   設計の下   -> 相対パス
#   APRtools の下 -> $APRTOOLS/...
#   それ以外のホーム配下 -> $HOME/...
# 端末に出す間は絶対パスのまま（`show()` の側。人がそのまま開ける）。
# **ファイルに落とし切ってから**書き換える。
sanitize_file() {
  [ -f "$1" ] || return 0
  t=${TMPDIR:-/tmp}/tr1um_syn_san.$$
  sed -e "s#$ROOTDIR/##g" -e "s#$ROOTDIR#.#g" \
      -e "s#$APRROOT#\$APRTOOLS#g" -e "s#$HOME/#\$HOME/#g" \
      "$1" > "$t" && cat "$t" > "$1"
  rm -f "$t"
}
[ -n "$CELLS_SYN" ] && SYN_CELLS=$CELLS || SYN_CELLS=""

[ -n "$TOP" ] || { echo "config.py の SYN_TOP / TOP_CELL_NAME が空" >&2; exit 1; }
[ -n "$RTL" ] || { echo "config.py に SYN_RTL が無い（合成する RTL を書くこと）" >&2; exit 1; }
mkdir -p "$OUT"

# --- ABC の制約は **`.lib` から起こす**（U99）------------------------------
# ★ 以前は `syn/abc.constr` に `set_load 36.2` と**直書き**してあった。
#   この 36.2 は「パッドセル `OSS_ESD_5V_DIO` の `OUT` ピンの入力容量」を
#   `.lib` から**写した**数字で、U96 で `.lib` を作り直したら実測は
#   45.923 fF になり、**写した側だけが古いまま**になった（U65 と同じ形）。
#   毎回 `.lib` から引けば、特性化 -> `.lib` -> 合成 が 1 本に繋がる。
#   `config.SYN_CONSTR` を設計が明示したときは、そちらをそのまま使う。
if [ -z "$CONSTR" ]; then
  CONSTR=$OUT/abc.constr
  CAP=$(python3 "$APRROOT/apr/lib_pin_cap.py" "$LIB" "$LOADCELL" "$LOADPIN") || {
    echo "** $LIB から $LOADCELL/$LOADPIN の capacitance が読めない" >&2; exit 1; }
  printf 'set_driving_cell %s
set_load %s
' "$DRVCELL" "$CAP" > "$CONSTR"
fi

LOG=$OUT/SYN_RESULTS.txt
if [ -z "${SYN_TEE:-}" ]; then
  SYN_TEE=1; export SYN_TEE
  sh "$0" "$@" 2>&1 | tee "$LOG"
  sanitize_file "$LOG"
  sanitize_file "$OUT/$TOP.synlog"
  tail -1 "$LOG" | grep -q '^完了' || {
    echo "** 途中で止まった。$LOG を見てください" >&2; exit 1; }
  exit 0
fi

[ -f "$LIB" ] || { echo "$LIB が無い。char/RUN.md の手順で作ってください" >&2; exit 1; }
case " $BLACKBOX " in
  *" RSLATCH "*)
    grep -q "cell (RSLATCH)" "$LIB" || {
      echo "** $LIB に RSLATCH が無い。char/run_rslatch.sh を先に流してください" >&2
      exit 1; } ;;
esac

# --- Yosys を探す ------------------------------------------------------------
find_yosys() {
  for c in $YOSYS yowasp-yosys yosys; do
    [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  for d in "$HOME/.local/bin" "$HOME/Library/Python"/*/bin /opt/homebrew/bin \
           /usr/local/bin "$HOME/.pyenv/shims"; do
    for c in yowasp-yosys yosys; do
      [ -x "$d/$c" ] && { echo "$d/$c"; return 0; }
    done
  done
  if python3 -c "import yowasp_yosys" >/dev/null 2>&1; then
    W="${TMPDIR:-/tmp}/tr1um-yowasp-yosys"
    printf '#!/bin/sh\nexec python3 -c %s "$@"\n' \
      "'import sys,yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))'" > "$W"
    chmod +x "$W"
    echo "$W"; return 0
  fi
  return 1
}
YS=$(find_yosys) || {
  echo "Yosys が見つからない。次のどれかをしてください:" >&2
  echo "  pip3 install yowasp-yosys        (または brew install yosys)" >&2
  echo "  YOSYS=/path/to/yosys sh \$APRTOOLS/syn/syn.sh" >&2
  exit 1; }
echo "設計 : $TOP   ($(pwd))"
echo "Yosys: $YS  ($($YS -V 2>&1 | head -1))"
echo "Liberty: $LIB"
command -v iverilog >/dev/null 2>&1 || echo "** iverilog が無いので段 1 と段 5 を飛ばします"
[ -f "$CONSTR" ] && echo "ABC 制約: $(tr '\n' ' ' < "$CONSTR") \
  （$CONSTR。set_load は $LIB の $LOADCELL / $LOADPIN から引いた値。U99）"

echo
echo "##################### 0. セルの Verilog モデルを生成"
if [ -n "$CELLS_GEN" ] && [ -n "$CELLS" ]; then
  # cellspec.py（ngspice で実レイアウトと突き合わせ済み）から起こす。
  #   --power  RTL が .VDD/.GND まで繋いでいる設計用
  #   --delay  クロス結合 NOR2 を iverilog で収束させる単位遅延
  mkdir -p "$(dirname "$CELLS")"
  python3 "$APR/../char/mkcellverilog.py" $CELLS_ARGS -o "$CELLS"
elif [ -n "$CELLS" ]; then
  echo "  $CELLS を既存のまま使う（SYN_CELLS_GEN=False）"
else
  echo "  セルモデルを使わない設計（SYN_CELLS_V 未設定）"
fi

echo
echo "##################### 1. RTL の機能検証"
run_tbs() {   # $1 = 被テスト Verilog, 残りが TB のリスト
  dut=$1; shift
  ng=0
  for tb in "$@"; do
    name=$(basename "$tb" .v)
    if iverilog -g2012 $INCDIR -o "$OUT/$name.vvp" "$tb" $dut $CELLS 2>"$OUT/$name.ivl"; then
      r=$(vvp "$OUT/$name.vvp" | grep -E "PASS|FAIL|OK:|NG:|ERROR" | tail -2 | tr '\n' ' ')
      case "$r" in *FAIL*|*NG:*|*ERROR*) ng=$((ng+1)); echo "  [FAIL] $name  $r" ;;
                   *)                    echo "  [ ok ] $name  $r" ;; esac
    else
      ng=$((ng+1)); echo "  [FAIL] $name  コンパイルできない"; head -5 "$OUT/$name.ivl"
    fi
  done
  [ "$ng" = 0 ] || { echo "** TB が $ng 本落ちた"; exit 1; }
}

if [ -n "$TB_RTL" ] && command -v iverilog >/dev/null 2>&1; then
  run_tbs "$RTL" $TB_RTL
else
  echo "  飛ばす（SYN_TB_RTL 未設定か iverilog 無し）"
fi

echo
echo "##################### 2. 合成 → 実セルへマッピング"
# セルモデルは **ライブラリ (-lib) ではなく普通の Verilog として**読む。
# RTL のクロス結合 NOR2 を論理まで展開し、ABC に貼り直させるため。
# -lib で読むとブラックボックスのまま残り、後段の merge が効かない。
# `blackbox RSLATCH` は RSLATCH を**セルのまま残す**ための指定。これが無いと
# 振る舞いモデルが展開され、ABC が入力ゲートごと吸収して NOR3/NAND3 の生ループに化ける。
BB=""
for b in $BLACKBOX; do BB="$BB blackbox $b;"; done
ABC="abc -liberty $LIB"
[ -f "$CONSTR" ] && ABC="$ABC -constr $CONSTR"
$YS -p "read_verilog $SYN_CELLS $RTL;$BB hierarchy -check -top $TOP; \
        synth -top $TOP -flatten; \
        dfflibmap -liberty $LIB; $ABC; opt_clean; \
        write_verilog -noattr $OUT/$TOP.v; tee -o $OUT/$TOP.stat stat -liberty $LIB" \
    > "$OUT/$TOP.synlog" 2>&1 || { echo "** 合成に失敗"; tail -30 "$OUT/$TOP.synlog"; exit 1; }
grep -iE "combinational loop|warning: found" "$OUT/$TOP.synlog" | sort -u | head -5
if grep -qE '^\s+\$_[A-Z]' "$OUT/$TOP.stat"; then
  echo "** マップできていないセルが残っている"; grep -E '^\s+\$_[A-Z]' "$OUT/$TOP.stat"
fi
NT=$(grep -cE "\.[A-Z]+\(1'[hb][01]\)" "$OUT/$TOP.v" || true)
python3 "$APR/syn_report.py" "$TOP" -n "$OUT/$TOP.v" --brief
[ "$NT" = 0 ] || echo "    ** 定数に繋がったセル入力ピンが $NT 個ある（TIEHI/TIELO が要る）"

echo
echo "##################### 3. 重複ゲートの整理（dedup_gates.py）"
# **必ずここで通す。** ABC は同じ入力に繋がった同じセルを何個も撒くことがあり、
# それが配線の混雑と短絡の真の原因になる（design_notes 108.37）。
python3 "$APR/dedup_gates.py" "$OUT/$TOP.v" "$OUT/${TOP}_dedup.v"

echo
echo "##################### 4. MUXDFFRB / RSLATCH への畳み込み"
#   MUX2 -> DFFRB.D（単一ファンアウト）      -> MUXDFFRB 1 個
#   クロス結合 NOR2 対                        -> RSLATCH 1 個
python3 "$APR/merge_muxdffrb_rslatch.py" --in "$OUT/${TOP}_dedup.v" \
                                         --out "$OUT/${TOP}_merged.v"

echo
echo "##################### 5. ゲートレベル TB（畳み込み後）"
if [ -n "$TB_NET" ] && command -v iverilog >/dev/null 2>&1; then
  run_tbs "$OUT/${TOP}_merged.v" $TB_NET
else
  echo "  飛ばす（SYN_TB_NET 未設定か iverilog 無し）"
fi

echo
echo "##################### 6. BUFTH で外部入力を受ける"
# OSS_ESD_5V_DIO には入力バッファが無く、PAD の 4.8 pF を外部ドライバが直接振る。
# BUFTH は立上り 3.71V / 立下り 1.20V（ヒステリシス 2.51V）。
if [ -n "$BUFTH" ]; then
  python3 "$APR/insert_bufth.py" "$OUT/${TOP}_merged.v" "$NET" \
          --nets "$(echo "$BUFTH" | tr ' ' ',')"
else
  echo "  BUFTH_NETS が空なので畳み込み後をそのまま使う"
  cp "$OUT/${TOP}_merged.v" "$NET"
fi
python3 "$APR/syn_report.py" "$TOP" -n "$NET" --brief

echo
echo "##################### 7. 面積と使用率"
python3 "$APR/syn_report.py" "$TOP" -n "$NET"

echo
echo "##################### 8. 既提出ネットリストとの突き合わせ"
if [ -n "$REF" ] && [ -f "$REF" ]; then
  python3 "$APR/cmp_cells.py" "$REF" "$NET"
else
  echo "  飛ばす（SYN_REF_NETLIST 未設定）"
fi

echo
echo "##################### 9. STA"
if [ -z "$CLK" ]; then
  echo "  飛ばす（config.py に STA_CLK_PORT が無い）"
elif command -v "${STA:-sta}" >/dev/null 2>&1; then
  # **必ず merge 後のネットリストに当てる。** 畳み込み前は NOR2 のクロス結合が
  # 生のループとして残っていて、OpenSTA が勝手にアークを 1 本切る。
  sh "$HERE/sta/sta.sh" "$NET" "$TOP" "$PER" 2>&1 | grep -vE "Warning (1210|503)"
else
  echo "  OpenSTA が無いので飛ばす（syn/sta/README.md にビルド手順）"
fi

echo
echo "完了"

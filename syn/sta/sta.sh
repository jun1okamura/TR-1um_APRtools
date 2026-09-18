#!/bin/sh
# OpenSTA を当てる。
#   usage: sh $APRTOOLS/syn/sta/sta.sh <netlist> <top> <period_ns> [report.tcl]
#          sh $APRTOOLS/syn/sta/sta.sh out/td4_soc_arr_pnr.v td4_soc_arr 100
#
# ★ **当てるのは「最後のネットリスト」**（`config.NET_PATH`）。途中の版を
#   渡すと、落ちずに**別の回路の数字**が出る。TD4 には 4 つあり、
#   `out/td4_soc_arr.v` はメモリが **DFF 128 個**に展開された版（4,175 行）、
#   `_bb.v` は `td4_mem` がブラックボックスのまま、`_mw.v` は BUFTH 前。
#   下見（このスクリプトが当てる前に回す）が、モジュール数と
#   Liberty に無いセルで気づけるようにしてある。
#
# OpenSTA 本体はこのリポジトリには入っていない。ビルド手順は syn/sta/README.md。
# $STA で実行ファイルを指定できる（既定は PATH の `sta`）。
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
NET=$1; TOP=$2; PER=$3; RPT=${4:-$HERE/report.tcl}
[ -n "$PER" ] || { echo "usage: $0 <netlist> <top> <period_ns> [report.tcl]" >&2; exit 1; }
STA=${STA:-sta}
command -v "$STA" >/dev/null 2>&1 || { echo "$STA が無い。ビルド手順は $(dirname "$0")/README.md" >&2; exit 1; }
# Liberty / クロックポート / false path は **設計の config.py** から取る。
# （PYTHONPATH=$APRTOOLS/apr が要る。手で上書きするなら LIB= / CLK= を渡す）
CFG=$(python3 - <<'PY'
import apr_path  # noqa: F401  設計の config.py を名指しで読む（U94）
import config as c
print(c.SYN_LIB)
print(getattr(c, "STA_CLK_PORT", "") or "")
print(" ".join(getattr(c, "STA_FALSE_PATH_FROM", []) or []))
print(" ".join(getattr(c, "STA_NON_SIGNAL_PORTS", []) or []))   # 4
print(" ".join(getattr(c, "STA_MACRO_INSTS", []) or []))        # 5
print(getattr(c, "NET_PATH", "") or "")                         # 6
print(getattr(c, "STA_EXTRA_TCL", "") or "")                    # 7
# \u2605 **足すなら末尾**。下は `sed -n Np` で**位置**で読んでいるので、
#   途中に挟むと以降が 1 つずつずれる（2026-09-18 に実際にずらして
#   `STA_EXTRA_TCL が無い: BUF_X2` を出した）。
print(getattr(c, "OUT_LOAD_CELL", "") or "")                    # 8
print(getattr(c, "OUT_LOAD_PIN", "") or "")                     # 9
print(getattr(c, "DRIVING_CELL", "") or "")                     # 10
print(getattr(c, "DRIVING_PIN", "") or "")                      # 11
PY
) || { echo "config.py が読めない（PYTHONPATH=\$APRTOOLS/apr）" >&2; exit 1; }
LIB=${LIB:-$(echo "$CFG" | sed -n 1p)}
CLK=${CLK:-$(echo "$CFG" | sed -n 2p)}
FALSEPATH=${FALSEPATH:-$(echo "$CFG" | sed -n 3p)}
NONSIG=${NONSIG:-$(echo "$CFG" | sed -n 4p)}
LOADCELL=$(echo "$CFG" | sed -n 8p);  LOADPIN=$(echo "$CFG" | sed -n 9p)
DRVCELL=$(echo "$CFG" | sed -n 10p); DRVPIN=$(echo "$CFG" | sed -n 11p)
# ★ 出力ポートに掛ける負荷は **`.lib` から引く**（U99）。`setup.tcl` に
#   `36.2` と直書きしてあり、U96 で `.lib` を作り直したら実測が 45.923 fF に
#   なって**写した側だけが古いまま**になった（U65 と同じ形）。
HERE_APR=$(cd "$(dirname "$0")/../../apr" && pwd)
OUTLOAD=${OUTLOAD:-$(python3 "$HERE_APR/lib_pin_cap.py" "$LIB" "$LOADCELL" "$LOADPIN")} || {
  echo "** $LIB から $LOADCELL/$LOADPIN の capacitance が読めない" >&2; exit 1; }
MACROS=${MACROS:-$(echo "$CFG" | sed -n 5p)}
FINAL=$(echo "$CFG" | sed -n 6p)
EXTRA=${EXTRA:-$(echo "$CFG" | sed -n 7p)}
if [ -n "$EXTRA" ]; then
  [ -f "$EXTRA" ] || { echo "STA_EXTRA_TCL が無い: $EXTRA" >&2; exit 1; }
  echo "  設計の追加制約: ${EXTRA#$PWD/}"
fi
[ -n "$CLK" ] || { echo "config.py に STA_CLK_PORT が無い" >&2; exit 1; }
[ -f "$LIB" ] || { echo "$LIB が無い" >&2; exit 1; }
[ -f "$NET" ] || { echo "$NET が無い" >&2; exit 1; }

# --- 当てる前の下見 ----------------------------------------------------------
# ★ **最後のネットリスト以外を当てても、落ちずに別の回路の数字が出る。**
#   `config.NET_PATH` と違うものを渡したら言う（止めはしない。途中の版を
#   意図して測ることはある）。TD4 の `out/td4_soc_arr.v` は**メモリが
#   DFF 128 個に展開された版**で、セルは全部 Liberty にあるので
#   下のセル検査では気づけない。
if [ -n "$FINAL" ] && [ "$(cd "$(dirname "$NET")" && pwd)/$(basename "$NET")" != "$FINAL" ]; then
  echo "  ** config.NET_PATH と違うネットリストを当てている"
  echo "     渡された: $NET"
  echo "     NET_PATH: ${FINAL#$PWD/}"   # 機械依存のパスを出さない（U58）
fi
# ★ **`read_verilog` は知らないセルを黙って受ける。** 足りないセルは
#   link_design のときに「port not found」や「パス無し」として現れるだけで、
#   **報告は普通に出てしまう**（U73 / U74 と同じ「回っていないのに OK」）。
#   当てる前に、ネットリストのセルが全部 Liberty にあるかを見る。
python3 - "$NET" "$LIB" <<'PY' || exit 1
import re, sys
net, lib = open(sys.argv[1]).read(), open(sys.argv[2]).read()
mods = re.findall(r"^module\s+(\w+)", net, re.M)
used = set(re.findall(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s+\\?\S+\s*\(", net, re.M)) - set(mods)
used -= {"module", "input", "output", "inout", "wire", "reg", "assign", "endmodule"}
have = set(re.findall(r"^\s*cell \((\w+)\)", lib, re.M))
miss = sorted(used - have)
print(f"  セル {len(used)} 種 / モジュール {len(mods)} 個")
if len(mods) > 1:
    print(f"  ** モジュールが {len(mods)} 個ある: {' '.join(mods)}")
    print("     OpenSTA は Liberty のセルしか知らない。**平らな 1 モジュール**を渡すこと")
if miss:
    print(f"  ** Liberty に無いセルが {len(miss)} 種: {' '.join(miss)}")
    print("     このまま当てると、その先のパスが**黙って消える**。当てるネットリストを間違えていないか")
    sys.exit(1)
PY

T=$(mktemp "${TMPDIR:-/tmp}/sta_XXXXXX.tcl")
{ echo "set NET $NET"; echo "set TOP $TOP"; echo "set PER $PER"
  echo "set LIB $LIB"; echo "set CLK $CLK"
  echo "set OUTLOAD $OUTLOAD"
  echo "set DRVCELL $DRVCELL"; echo "set DRVPIN $DRVPIN"
  echo "set FALSEPATH [list $FALSEPATH]"; echo "set NONSIG [list $NONSIG]"
  echo "set MACROS [list $MACROS]"
  echo "set HERE $HERE"; cat "$HERE/setup.tcl"
  # 設計固有の制約は setup.tcl の**後**（クロックも駆動セルも決まってから当てる）
  [ -n "$EXTRA" ] && cat "$EXTRA"
  cat "$RPT"
  # マクロがある設計では、制約が**実際に見られているか**まで出す（U73）。
  [ -n "$MACROS" ] && cat "$HERE/report_macro.tcl"; } > "$T"
# 電源ピンの Warning 201 をたたむ。
#   Warning 201: ... instance u_muxdffrb_1 port VDD not found.
# merge_muxdffrb_rslatch.py が書く MUXDFFRB / RSLATCH のインスタンスは
# `.VDD(VDD), .GND(GND)` まで繋いである（V10 からの書式）が、`.lib` のセルには
# 電源ピンが無いので読むたびに 2 行ずつ出る。19 インスタンスで 40 行になり、
# **本物の「port not found」が埋もれる**。VDD/GND のものだけ数えて 1 行にする。
"$STA" -no_splash -exit "$T" 2>&1 | awk '
  /^Warning 201: .*port (VDD|GND) not found/ { n++; next }
  { print }
  END { if (n) printf "  (電源ピン VDD/GND の Warning 201 を %d 行たたみました。.lib に\n   電源ピンが無いだけで、タイミングには影響しません)\n", n }'
rm -f "$T"

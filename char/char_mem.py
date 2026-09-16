#!/usr/bin/env python3
"""`REG8x16`（16 ワード x 8 ビットの命令メモリマクロ）の特性化。

  usage: python3 $APRTOOLS/char/char_mem.py [-n cells_mem/REG8x16.spi]
                                          [-o char/REG8x16.json] [-j 2]

P&R の本命 `td4_soc_arr_bb` は `REG8x16` をマクロとして持つので、
**これのタイミングが `.lib` に無いと STA が当てられない**。ここで測る。

セルの素性（`lef/simulation/REG8x16.spice`）:
  ラッチ型 12T ビットセル `TLAT` を 16 行 x 8 列。**クロックは無い。**
    リード  ADD[3:0] -> 行デコーダ -> RD/RDB -> TG -> ql[7:0] -> REGBUF -> Q[7:0]
            組合せ（非同期）。CPI=1 のためこれが必須。
    ライト  `WR = NOR2(RDB, WEB)` — WEB=0（アクティブロー）の間だけ選択行が
            素通しになり、**WEB の立上りでラッチ**される。

測るもの（**実装されているのはこの 2 つだけ**。`--only` の選択肢と一致）:
  1. ADD[j] -> Q[i]  リードアクセス時間（組合せアーク）。7 スルー x 7 負荷。
  2. 入力容量 ADD / WEB / D。

**まだ測っていない = 書込みパス**（U7、2026-09-16 に確認）:
  * `D` / `ADD` の `WEB` 立上りに対する setup / hold
  * `WEB` -> `Q`（書込み中に Q が追従する経路）
  * `WEB` の最小ローパルス幅
  読出しは `char/REG8x16.json` の `read` に入り Liberty にも出ている
  （`bus (Q)` の中の `related_pin: "ADD[0..3]"`）ので、**読出しなら STA は
  当たる**。書込みを STA で見るには上の 3 つが要る。測り方は `char_seq.py`
  の二分探索がそのまま使えるが、**寄生込みの数字を出すには下の未解決
  （抽出ネットリストで書込みが効かない）が先**。

測り方の要点:
  * **アレイにリセットが無い**ので、読む前に必ず書く。
    word0 = 0x00 / word1,2,4,8 = 0xFF を書いておくと、ADD=0 から
    ADD[j] を 1 本立てるだけで **全 8 ビットが 0x00 -> 0xFF に振れる**。
    4 本のアドレスビットすべてを 1 つの書込みパターンで賄える。
  * 負荷掃引は **Q[0..6] に別々の容量をぶら下げて 1 デッキで済ませる**。
    8 ビットは同じ列構造なので、7 個のインスタンスを並べるより 2 桁速い。
    ビット間のばらつきは Q[7] に Q[0] と同じ負荷を付けて監視する。
  * `.meas` には必ず `TD=` を入れる。入れないと書込みフェーズの
    エッジを拾ってしまう（実際に踏んだ）。

**未解決: 抽出ネットリストでは書込みが効かない。原因は PS/PD。**
  `lef/simulation/REG8x16.spice`（設計ネットリスト）では期待どおり動く
  —— word0 に 0x00、word1/2/4/8 に 0xFF を書いて読み戻せる。
  ところが `lef/extracted/REG8x16.extracted` を同じ刺激で回すと
  **どのアドレスを読んでも 5V** になる。

  ★ **2026-09-16: 以前ここに書いていた切り分け結果は再現しなかった。**
    旧記述は「AS/AD だけ外す → 動かない / **PS/PD だけ外す → 動く**
    （22.28ns -> 21.81ns）」で、そこから「原因は PS/PD」としていた。
    `--strip` で 3 通りを回し直したところ（Mac / ngspice）:

        そのまま         Q[0] = 5.0   効かない
        PS/PD を既定へ   Q[0] = 5.0   効かない
        AS/AD を既定へ   Q[0] = 5.0   効かない

    **どれも効かない。** つまり「PS/PD が原因」という結論の根拠が無い。
    接合パラメータの話ではないところに原因がある。

  ★ 分かっていること（U2 の進捗、`docs/90_improvement_notes.md`）:
      2 つのネットリストは**同じ回路**（素子 1,876 個・葉セル 4 つの
      トポロジ・アレイ 112 ネットの使われ方まで一致）。
      トップのポート順も `PORTS_EXT` と実物が一致している。
  ★ 次に確かめること: **設計ネットリストの方はいま本当に動くのか**。
      `char/REG8x16.json` は設計ネットリストで測れた記録だが、
      当時と ngspice の版が違う。両方を同じ日に回して比べる。

  （抽出が実行ごとに揺れるという以前の推測は**誤り**。3 回流して同一で、
    REG8x16 の抽出もバイト一致。順が違って見えたのは抽出スコープの違い。）

  ★ **2 つのネットリストは同じ回路であることを確認した**（2026-09-16、
    ngspice 無しの静的比較）。ここまで分かっているので、残る違いは
    `AS/AD/PS/PD` だけだと言い切れる:

      素子       1,876 個、W/L の内訳まで一致
                 （NMOS 3.4u×810 / 4.6u×128、PMOS 7.2u×768 / 10.2u×42 / 12.2u×128）
      葉セル     TLAT / REGBUF / ADDBUF / DEC2 の 4 つとも**トポロジ一致**
                 （MOS の d/s は入れ替え可能として正準化して突き合わせ）
      アレイ     ネット 112 本・インスタンス 145 個で、
                 **ネットの使われ方の分布まで一致**

    ★ **`--strip` で切り分けを再現できる**（手で消さない）:

        python3 char_mem.py --ext --only read              # そのまま
        python3 char_mem.py --ext --only read --strip perim   # PS/PD を落とす
        python3 char_mem.py --ext --only read --strip area    # AS/AD を落とす

    ★ **落とすと 0 になるのではなく、PDK の既定式に戻る** —
      `AS/AD = w*sdwidth`、`PS/PD = 2*(sdwidth+w)`。つまり設計ネットリストと
      同じ扱いになる。そして**抽出の実測値はどれも既定以下**
      （この設計で全素子を確認。比 0.21〜1.00）。
      容量が**減っている**側が動かず、**増やす**と動く、ということなので、
      「接合容量が重くて書けない」では説明がつかない。
      次に見るのは ngspice の BSIM3 が PS/PD をどう食っているか
      （`cjsw` / `cjswg` は PDK のモデルカードに無く BSIM3 の既定）。
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
VDD, TEMP = 5.0, 25
CELL = "REG8x16"
# ★ 既定は PDK（`TR1UM_PDK`）。リポジトリにモデルを写さない（U65）。
from check_comb import models_dir, need_ngspice                                 # noqa: E402
MODELS = models_dir()
FRAME_LEF = None            # マクロなので面積は cell_area.json から取る

SLEWS = [0.1, 0.25, 0.6, 1.5, 4.0, 8.0, 16.0]      # 標準セルと同じ格子
LOADS = [10, 20, 50, 100, 200, 400, 800]           # fF。Q はコアの標準セルを駆動する
SLEWS_C = [0.6, 1.5, 4.0]                          # setup/hold の格子
TH, LO, HI = 50, 20, 80
SLEW_FRAC = (HI - LO) / 100
EDGE = 0.1              # 書込みフェーズの矩形波の立上り [ns]
IDLE = 100.0            # 最初の書込みの前に置く待ち時間 [ns]
TW = 120.0              # 1 ワードの書込みに使う時間 [ns]
SETTLE = 100.0          # 書込み後に落ち着かせる時間 [ns]
TAIL = 400.0            # 測定エッジの後ろに取る時間 [ns]
WORDS = [(0, 0x00), (1, 0xFF), (2, 0xFF), (4, 0xFF), (8, 0xFF)]

APIN = [f"A{j}" for j in range(4)]
DPIN = [f"DD{i}" for i in range(8)]
QPIN = [f"QQ{i}" for i in range(8)]
# **ポート順はネットリストによって違う。**
#   抽出 (lef/extracted/REG8x16.extracted): ADD D Q WEB vdd vss
#   設計 (lef/simulation/REG8x16.spice):     ADD WEB D Q vdd vss
PORTS_EXT = " ".join(APIN + DPIN + QPIN + ["WEB", "vdd", "vss"])
PORTS_SRC = " ".join(APIN + ["WEB"] + DPIN + QPIN + ["vdd", "vss"])
PORTS = PORTS_SRC


def full_ramp(s):
    return s / SLEW_FRAC


def pwl(pts):
    """[(t_ns, v)] -> PWL 文字列"""
    return "PWL(" + " ".join(f"{t:g}n {v:g}" for t, v in pts) + ")"


def step(seq):
    """[(t_ns, v)] を**区間一定**の波形に直す（PWL は点間を線形補間するので、
    そのまま渡すと 40ns かけてだらだら遷移してしまう）。"""
    out = []
    for k, (t, v) in enumerate(seq):
        if k == 0:
            out.append((t, v))
        else:
            pv = seq[k - 1][1]
            if v != pv:
                out.append((t - EDGE, pv))
            out.append((t, v))
    return out


def write_phase():
    """word0=0x00 / word1,2,4,8=0xFF を書く波形。(add, d, web, t_end) を返す。

    **最初に IDLE の待ちが要る。** 動作点から立ち上がった直後は内部の WEB
    バッファ（16 個の DEC2 の NOR2 を駆動する）がまだ遷移中で、書込みが
    効かない。IDLE=0 / WEB 低 24ns で試したときは word0 だけ書けず、
    全アドレスが 0xFF に見えていた。
    """
    add = [[] for _ in range(4)]
    dat = [[] for _ in range(8)]
    web = [(0.0, VDD)]
    for j in range(4):
        add[j].append((0.0, 0))
    for i in range(8):
        dat[i].append((0.0, 0))
    t = IDLE
    for a, d in WORDS:
        for j in range(4):
            add[j].append((t, VDD if (a >> j) & 1 else 0))
        for i in range(8):
            dat[i].append((t, VDD if (d >> i) & 1 else 0))
        web += [(t, VDD), (t + 20, 0), (t + TW - 20, 0), (t + TW - 5, VDD)]
        t += TW
    return add, dat, web, t


PROBE = False          # --probe。書込みの経路を段ごとに見る（U2）


def tlat_nets(netlist, pin):
    """アレイの中の TLAT の `pin` に繋がっているネットを重複なしで拾う。

    ★ 行や列の番号は分からなくてよい。知りたいのは「**何本が振れるか**」
      だけで、それで段を切り分けられる（`WR` が立つか / `D` が届くか）。
      名前をこちらに写さない（決定 22）ので、`.SUBCKT TLAT` の並びから
      その pin の位置を読んで、インスタンス行から取る。
    """
    lines = []
    for ln in open(netlist, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("+") and lines: lines[-1] += " " + ln[1:].strip()
        else: lines.append(ln)
    idx = None
    for ln in lines:
        t = ln.split()
        if len(t) > 2 and t[0].lower() == ".subckt" and t[1] == "TLAT":
            if pin not in t[2:]:
                return []
            idx = t[2:].index(pin)
            break
    if idx is None:
        return []
    out, depth = [], 0
    for ln in lines:
        t = ln.split()
        if not t: continue
        if t[0].lower() == ".subckt": depth += 1; top = (t[1] == CELL); continue
        if t[0].lower() == ".ends": depth -= 1; continue
        if depth == 1 and top and t[0].upper().startswith("X") and t[-1] == "TLAT":
            if len(t) > idx + 1: out.append(t[1 + idx])
    seen, uniq = set(), []
    for n in out:
        if n not in seen: seen.add(n); uniq.append(n)
    return uniq


def header(netlist):
    return [f".include {MODELS}/ip62_models", f".include {netlist}", "",
            f".temp {TEMP}", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]


def drive(L, name, pin, pts):
    L.append(f"V{name} {name}s 0 {pwl(step(pts))}")
    L.append(f"R{name} {name}s {pin} 0.001")


def build_read(netlist, bit, slew, rise):
    """ADD[bit] -> Q[0..7]。負荷は Q[0..6] に 7 点、Q[7] は Q[0] と同じ（ばらつき監視）。"""
    add, dat, web, t = write_phase()
    T0 = t + SETTLE
    tf = full_ramp(slew)
    a0 = 0 if rise else (1 << bit)
    a1 = (1 << bit) if rise else 0
    for j in range(4):
        add[j].append((t, VDD if (a0 >> j) & 1 else 0))
    web.append((t, VDD))

    L = [f"* {CELL} ADD[{bit}] -> Q  入力遷移 {slew}ns {'rise' if rise else 'fall'}"
         f"  -- char_mem.py 生成"]
    L += header(netlist)
    for j in range(4):
        pts = step(add[j])
        if j == bit:            # 測定エッジだけは指定のスルーで振る
            pts += [(T0, VDD if (a0 >> j) & 1 else 0),
                    (T0 + tf, VDD if (a1 >> j) & 1 else 0)]
        else:
            pts += [(T0 + tf, pts[-1][1])]
        L.append(f"Va{j} a{j}s 0 {pwl(pts)}")
        L.append(f"Ra{j} a{j}s A{j} 0.001")
    for i in range(8):
        drive(L, f"d{i}", f"DD{i}", dat[i] + [(T0 + tf + TAIL, dat[i][-1][1])])
    drive(L, "web", "WEB", web + [(T0 + tf + TAIL, VDD)])
    L.append(f"XU {PORTS} {CELL}")
    for i, cl in enumerate(LOADS):
        L.append(f"C{i} QQ{i} 0 {cl}f")
    L.append(f"C7 QQ7 0 {LOADS[0]}f")

    tend = T0 + tf + TAIL
    L.append(f".tran {max(min(slew, 0.5) / 20, 0.05):g}n {tend:g}n")
    vt, lo, hi = VDD * TH / 100, VDD * LO / 100, VDD * HI / 100
    td = T0 - 1.0                       # 書込みフェーズのエッジを拾わないため
    ed = "RISE=1" if rise else "FALL=1"
    for i in range(8):
        L.append(f".meas tran d{i} TRIG v(A{bit}) VAL={vt:g} {ed} TD={td:g}n "
                 f"TARG v(QQ{i}) VAL={vt:g} {ed} TD={td:g}n")
        if rise:
            L.append(f".meas tran t{i} TRIG v(QQ{i}) VAL={lo:g} RISE=1 TD={td:g}n "
                     f"TARG v(QQ{i}) VAL={hi:g} RISE=1 TD={td:g}n")
        else:
            L.append(f".meas tran t{i} TRIG v(QQ{i}) VAL={hi:g} FALL=1 TD={td:g}n "
                     f"TARG v(QQ{i}) VAL={lo:g} FALL=1 TD={td:g}n")
    # 書込みが効いているかの確認。読出し直前の Q[0] は word0 = 0x00 -> 0V のはず
    L.append(f".meas tran chk FIND v(QQ0) AT={T0 - 5:g}n")
    if PROBE:
        # ★ 書込みフェーズのあいだ、行選択の WR 線が 1 本でも上がるか。
        #   上がらなければデコーダ側、上がるならラッチ側（U2）。
        for i, n in enumerate(tlat_nets(netlist, "WR")):
            L.append(f".meas tran wr{i} MAX v(xu.{n}) FROM=0n TO={t:g}n")
        # D 線（列ごとに 1 本）。書込みの**データ**がセルまで来ているか。
        for i, n in enumerate(tlat_nets(netlist, "D")):
            L.append(f".meas tran dmax{i} MAX v(xu.{n}) FROM=0n TO={t:g}n")
            L.append(f".meas tran dmin{i} MIN v(xu.{n}) FROM=0n TO={t:g}n")
        L.append(f".meas tran webmin MIN v(WEB) FROM=0n TO={t:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_cap(netlist, pin_idx, kind):
    """入力ピンに流れ込む電荷から容量を出す。kind は 'add' / 'web' / 'd'。"""
    sl = 2.0
    add, dat, web, t = write_phase()
    T0 = t + SETTLE
    tf = full_ramp(sl)
    L = [f"* {CELL} {kind}{pin_idx} 入力容量 -- char_mem.py 生成"]
    L += header(netlist)
    tgt = {"add": f"A{pin_idx}", "web": "WEB", "d": f"DD{pin_idx}"}[kind]
    for j in range(4):
        pts = step(add[j]) + [(t, add[j][-1][1])]
        if kind == "add" and j == pin_idx:
            pts += [(T0, 0), (T0 + tf, VDD)]
        else:
            pts += [(T0 + tf + 200, pts[-1][1])]
        L.append(f"V{'in' if (kind=='add' and j==pin_idx) else f'a{j}'} "
                 f"{'insrc' if (kind=='add' and j==pin_idx) else f'a{j}s'} 0 {pwl(pts)}")
        L.append(f"R{'in' if (kind=='add' and j==pin_idx) else f'a{j}'} "
                 f"{'insrc' if (kind=='add' and j==pin_idx) else f'a{j}s'} A{j} 0.001")
    for i in range(8):
        pts = dat[i] + [(t, dat[i][-1][1])]
        if kind == "d" and i == pin_idx:
            pts = step(pts) + [(T0, 0), (T0 + tf, VDD)]
            L.append(f"Vin insrc 0 {pwl(pts)}"); L.append(f"Rin insrc DD{i} 0.001")
        else:
            drive(L, f"d{i}", f"DD{i}", pts + [(T0 + tf + 200, pts[-1][1])])
    wpts = web + [(t, VDD)]
    if kind == "web":
        wpts = step(wpts) + [(T0, VDD), (T0 + tf, 0)]
        L.append(f"Vin insrc 0 {pwl(wpts)}"); L.append("Rin insrc WEB 0.001")
    else:
        drive(L, "web", "WEB", wpts + [(T0 + tf + 200, VDD)])
    L.append(f"XU {PORTS} {CELL}")
    for i in range(8):
        L.append(f"C{i} QQ{i} 0 {LOADS[2]}f")
    L.append(f".tran 0.05n {T0+tf+200:g}n")
    L.append(f".meas tran q INTEG i(Vin) FROM={T0:g}n TO={T0+tf:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


# ★ 実験ごとにデッキとログの置き場を分ける。以前は decks/ logs/ が 1 つで、
#   `--strip` を替えて回すと**前の実験のログを上書き**していた（切り分けの
#   比較ができない。生産者と消費者が同じ場所を取り合う形）。
RUNTAG = "src"


def run(deck, tag, need=True):
    """1 デッキ回して .meas の結果を返す。

    **失敗は握りつぶさない。** ngspice が落ちても空の dict を返していたため、
    ネットリストが 1 つ無いだけで 56 デッキぶん静かに空回りしたことがある
    （`cells_mem/REG8x16_src.spi` の include に失敗していた）。
    """
    dd, ld = f"{HERE}/decks/{RUNTAG}", f"{HERE}/logs/{RUNTAG}"
    os.makedirs(dd, exist_ok=True)
    os.makedirs(ld, exist_ok=True)
    p = f"{dd}/{tag}.spi"
    open(p, "w").write(deck)
    r = subprocess.run([os.environ.get("NGSPICE", "ngspice"), "-b", p], capture_output=True, text=True, timeout=3600)
    log = r.stdout + r.stderr
    open(f"{ld}/{tag}.log", "w").write(log)
    v = {}
    for ln in log.splitlines():
        m = re.match(r"^\s*([a-z]\w*)\s*=\s*([-\d.eE+]+)", ln)
        if m:
            try: v[m.group(1)] = float(m.group(2))
            except ValueError: pass
    if need and not v:
        why = [ln for ln in log.splitlines()
               if re.search(r"(?i)\b(error|could not|fatal|no such)\b", ln)]
        raise SystemExit(
            f"** {tag}: ngspice が値を 1 つも返さなかった（exit {r.returncode}）\n"
            + "\n".join(f"   {w}" for w in why[:5])
            + f"\n   デッキ: {p}\n   ログ:   {ld}/{tag}.log")
    return v


RE_AREA = re.compile(r"\s+A[SD]=\S+", re.I)
RE_PERIM = re.compile(r"\s+P[SD]=\S+", re.I)


def strip_junction(netlist, mode):
    """接合パラメータを落とした写しを作り、その道を返す（U2 の切り分け用）。

    ★ **落とすと 0 になるのではなく、PDK のサブサーキットの既定式に戻る**:
        AS/AD = w*sdwidth        PS/PD = 2*(sdwidth+w)
    つまり**設計ネットリストと同じ扱い**になる。抽出の実測値はどれも
    この既定以下（この設計で確認済み）なので、「落とすと動く」は
    「容量が減ったから」では説明がつかない。そこが U2 の謎。
    """
    out = netlist.replace(".spi", "") + f"_no-{mode}.spi"
    n = 0
    with open(netlist, encoding="utf-8") as f, open(out, "w", encoding="utf-8") as g:
        for ln in f:
            if ln[:2].upper() == "XM" or ln[:1].upper() == "M":
                before = ln
                if mode in ("area", "both"):
                    ln = RE_AREA.sub("", ln.rstrip("\n")) + "\n"
                if mode in ("perim", "both"):
                    ln = RE_PERIM.sub("", ln.rstrip("\n")) + "\n"
                n += (ln != before)
            g.write(ln)
    print(f"  {n} 行から落とした")
    return out


def main():
    ap = argparse.ArgumentParser()
    # ★ 既定は **None**。実際の道は --ext を見てから決める。
    #   以前は既定に設計ネットリストの道を入れていて、**存在チェックが
    #   --ext の差し替えより前**に走ったので、--ext を付けても
    #   「使いもしない設計ネットリストが無い」で止まっていた（決定 23 の仲間 —
    #   判定の対象が確定する前に判定していた）。
    ap.add_argument("-n", "--netlist", default=None,
                    help="既定は設計ネットリスト由来。--ext で抽出由来に切り替える")
    ap.add_argument("--ext", action="store_true",
                    help="抽出ネットリスト（cells_mem/REG8x16.spi）を使う。"
                         "**現状これは書込みが効かない。下の注意を参照**")
    # ★ 既定の出力先も実験ごとに分ける。`--ext` や `--strip` の結果が
    #   **正本の char/REG8x16.json を上書きしない**ようにするため。
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--only", choices=["read", "cap"])
    ap.add_argument("--probe", action="store_true",
                    help="書込みの経路を段ごとに見る（U2）。行選択の WR 線が"
                         "1 本でも上がるかを測り、デコーダ側かラッチ側かを分ける")
    ap.add_argument("--quick", action="store_true",
                    help="代表 1 点（ADD[0] / slew 1.5ns / rise）だけ回す。"
                         "書込みが効いているかを見るだけならこれで足りる")
    ap.add_argument("--strip", choices=["none", "area", "perim", "both"],
                    default="none",
                    help="接合パラメータを落とした写しで回す（U2 の切り分け）。"
                         "area=AS/AD / perim=PS/PD / both=両方。"
                         "落とすと PDK の既定式に戻る（0 になるのではない）")
    a = ap.parse_args()
    need_ngspice()                              # 先に確かめる（決定 23）
    global PORTS, RUNTAG, PROBE
    PROBE = a.probe
    RUNTAG = ("ext" if a.ext else "src") + ("" if a.strip == "none" else f"_no-{a.strip}")
    if a.out is None:
        a.out = (f"{HERE}/char/{CELL}.json" if RUNTAG == "src"
                 else f"{HERE}/char/{CELL}_{RUNTAG}.json")
    if a.ext:
        PORTS = PORTS_EXT
    if a.netlist is None:                       # -n が無いときだけこちらが決める
        a.netlist = (f"{HERE}/cells_mem/{CELL}.spi" if a.ext
                     else f"{HERE}/cells_mem/{CELL}_src.spi")
    if not os.path.exists(a.netlist):
        how = (f"     python3 $APRTOOLS/char/loadext.py <設計>/lef/extracted "
               f"-o $APRTOOLS/char/cells_mem" if a.ext else
               f"     python3 $APRTOOLS/char/mkmemsrc.py <設計>/lef/simulation/{CELL}.spice \\\n"
               f"             -o $APRTOOLS/char/cells_mem/{CELL}_src.spi")
        raise SystemExit(
            f"** ネットリストが無い: {a.netlist}\n"
            f"   {'抽出' if a.ext else '設計'}ネットリストから作るには:\n{how}")
    if a.strip != "none":
        a.netlist = strip_junction(a.netlist, a.strip)
        print(f"  接合パラメータ {a.strip} を落とした写し: {a.netlist}")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    res = {"cell": CELL, "netlist": os.path.basename(a.netlist), "macro": True, "slews": SLEWS, "loads": LOADS,
           "read": {}, "cap": {}, "bit_spread": {}}

    if a.only in (None, "read"):
        jobs = ([(0, 3, SLEWS[3], True)] if a.quick else
                [(b, si, sl, rise)
                 for b in range(4) for si, sl in enumerate(SLEWS) for rise in (True, False)])
        def one(j):
            b, si, sl, rise = j
            tag = f"mem_a{b}_s{si}_{'r' if rise else 'f'}"
            return j, run(build_read(a.netlist, b, sl, rise), tag)
        out = {}
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for k, (j, v) in enumerate(ex.map(one, jobs)):
                out[j[:1] + j[1:2] + j[3:]] = v
                print(f"  [{k+1:>2}/{len(jobs)}] ADD[{j[0]}] slew {j[2]:>5}ns "
                      f"{'rise' if j[3] else 'fall'}  d(CL=100fF) = "
                      f"{(v.get('d3') or 0)*1e9:.2f} ns  chk = {v.get('chk')}", flush=True)
        if a.quick:
            # ★ 代表 1 点だけなので表は作らない。**書込みが効いたかだけ**出す。
            v = out[(0, 3, True)]
            chk = v.get("chk")
            print(f"\n  読出し直前の Q[0] = {chk}  "
                  f"（word0 = 0x00 なので **0V 付近なら書込みが効いている**。"
                  f"5V 付近なら効いていない）")
            print(f"  ADD[0] -> Q[0] の遅延 = "
                  f"{(v.get('d0') or 0)*1e9:.2f} ns（0.00 は測れなかったということ）")
            if a.probe:
                wr = sorted(k for k in v if k.startswith("wr"))
                hi = [k for k in wr if (v[k] or 0) > VDD / 2]
                print(f"  WEB の最低値 = {v.get('webmin')} "
                      f"（0V 付近まで下がっていれば書込み指示は届いている）")
                print(f"  行選択の WR 線 {len(wr)} 本のうち "
                      f"**{len(hi)} 本**が VDD/2 を超えた")
                if wr:
                    print("    最大値: " + ", ".join(f"{v[k]:.2f}" for k in wr[:8])
                          + (" …" if len(wr) > 8 else ""))
                dmx = sorted(k for k in v if k.startswith("dmax"))
                dmn = sorted(k for k in v if k.startswith("dmin"))
                if dmx:
                    sw = [k for k in dmx
                          if (v[k] or 0) > VDD / 2
                          and (v.get("dmin" + k[4:]) or VDD) < VDD / 2]
                    print(f"  セル側の D 線 {len(dmx)} 本のうち "
                          f"**{len(sw)} 本**が 0V と 5V の両方に振れた")
                    print("    最大: " + ", ".join(f"{v[k]:.2f}" for k in dmx)
                          + "\n    最小: " + ", ".join(f"{v[k]:.2f}" for k in dmn))
                print("  -> WR が立たないならデコーダ側、D が振れないなら入力バッファ側、"
                      "どちらも正常ならラッチ側")
            print(f"  デッキとログ: {HERE}/decks/{RUNTAG} / {HERE}/logs/{RUNTAG}")
            return
        for b in range(4):
            arc = {}
            for key, rise in (("cell_rise", True), ("cell_fall", False)):
                arc[key] = [[out[(b, si, rise)].get(f"d{i}") for i in range(7)]
                            for si in range(len(SLEWS))]
                tk = "rise_transition" if rise else "fall_transition"
                arc[tk] = [[out[(b, si, rise)].get(f"t{i}") for i in range(7)]
                           for si in range(len(SLEWS))]
            res["read"][f"ADD[{b}]"] = arc
            # ビット間のばらつき: Q[7] は Q[0] と同じ負荷
            sp = []
            for si in range(len(SLEWS)):
                for rise in (True, False):
                    v = out[(b, si, rise)]
                    if v.get("d0") and v.get("d7"):
                        sp.append(abs(v["d7"] - v["d0"]) / v["d0"])
            res["bit_spread"][f"ADD[{b}]"] = max(sp) if sp else None

    if a.only in (None, "cap"):
        for kind, n in (("add", 4), ("web", 1), ("d", 8)):
            for i in range(n):
                q = run(build_cap(a.netlist, i, kind), f"mem_cap_{kind}{i}").get("q")
                nm = {"add": f"ADD[{i}]", "web": "WEB", "d": f"D[{i}]"}[kind]
                res["cap"][nm] = abs(q) / VDD * 1e15 if q is not None else None
        print("\n入力容量: " + " / ".join(f"{k} {v:.1f} fF"
                                          for k, v in res["cap"].items() if v))

    got = sum(1 for arc in res["read"].values() for tbl in arc.values()
              for row in tbl for x in row if x is not None)
    if a.only in (None, "read") and got == 0:
        raise SystemExit("** 測定値が 1 点も取れなかった。logs/ を見てください")

    if os.path.exists(a.out):
        old = json.load(open(a.out))
        for k, v in old.items():
            if k not in res:
                res[k] = v
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()

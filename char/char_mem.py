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

**解決（2026-09-16）: セルの問題ではなく、この測り方の問題だった。**
**`WEB` を上げてから次のワードのアドレスを変えるまでが 5ns しか無かった。**

  症状: `lef/extracted/REG8x16.extracted` を回すと**どのアドレスを読んでも 5V**。
        設計ネットリスト（`lef/simulation/REG8x16.spice`）なら期待どおり。

  ★ 実測（`--web-pre` を振る。抽出ネットリスト）:

        WEB 余裕  5 ns   保持しない
        WEB 余裕 20 ns   保持する
        WEB 余裕 40 ns   保持する

    内部の `WEB` は 16 個の `DEC2` の `NOR2` を駆動するバッファを通るので遅い
    （**`IDLE` が要るのと同じ理由。この docstring の `write_phase` の項に
    最初から書いてある**）。5ns では**アドレスが変わる瞬間にまだ書込みが
    有効**で、前の行に次のワードのデータ（0xFF）が入る。

  ★ そこに至るまでの測定（`--probe`）。どれも「セルは正常」を示していた:
      デコーダ / 入力バッファ / デコードの一致 / 帰還の開閉  すべて正常
      書込み中はセル内 4 ノードが全部正しく反転する
      **反転した時刻 223.2 ns** = アドレスが変わる 220 ns の直後
      `WR` を**窓の最大**で測り直すと、`word1` の窓でも立っている
      （中点の `FIND` では取りこぼしていた）

  ★ **外れた仮説を 3 つ潰した。残しておく**:
      1. 「原因は `PS/PD`」（旧記述）— 再現しない。`--strip` 5 通りのうち
         保持するのは `both` だけで、「`PS/PD` だけ」は成り立たない
      2. 「帰還が切れて浮き、リークで戻る」— `WRB` は `WR=0` のとき 5 に
         戻っており、帰還は閉じている
      3. 「トランスファゲートが閉じるときの電荷注入」— 縁を 0.1→10ns と
         **100 倍振っても一切変わらない**。注入なら必ず変わる
    `--strip both` で直って見えたのも、接合が余裕を作っていたのではなく、
    **内部 `WEB` の遅れが変わってタイミングが噛み合っただけ**。

  ★ **これは測り方の話だが、同時に実物の要求でもある。**
    「`WEB` を上げてからアドレスを変えるまでに空けるべき時間」は
    `REG8x16` を使う側が守るべき制約。**実測（抽出ネットリスト）:**

        `WEB↑` から内部 `WR` が落ちるまで = **8.2 ns**

    刺激の余裕が 5ns では `WR` がまだ落ちきる前にアドレスが変わるので
    前の行が書き換わる。6ns では通ったが**残りの重なりが 2ns ほどしか
    無い**ので、安全側の要求は **`8.2 ns` 以上**。既定の 20ns はその上。
    これが U7（書込みパスの特性化）の**最初の 1 項目**になる。

  ★ **既定を 5 → 20 ns にした。** 5 は「たまたま設計ネットリストでだけ
    通る値」で、実物の値で回すと落ちる。
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
# ★ **WEB を上げてから次のワードのアドレス / データを変えるまでの余裕** [ns]。
#   内部の WEB は 16 個の DEC2 の NOR2 を駆動するバッファを通るので遅い
#   （IDLE が要るのと同じ理由。この docstring の冒頭を参照）。ここが足りないと
#   **アドレスが変わる瞬間にまだ書込みが有効**で、前の行に次のデータが入る。
WEB_PRE = 20.0          # ★ 5.0 では足りない（実測）。下の「解決」を参照
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
    """`PWL(...)` の文字列。★ **時刻が逆行していたら止める。**

    掃引するつまみ（`--web-pre` / `--edge`）は範囲の端で刺激を壊しうる。
    実際 `WEB_PRE > 20` で点の順序が崩れ、**壊れた刺激のまま「保持する」と
    出ていた**。黙って通すと掃引の結論がまるごと嘘になるので、ここで弾く。
    """
    for i in range(len(pts) - 1):
        if pts[i + 1][0] < pts[i][0]:
            raise SystemExit(
                f"** 刺激の時刻が逆行している: {pts[i]} -> {pts[i + 1]}\n"
                f"   つまみの値が範囲外（WEB_PRE={WEB_PRE:g} / EDGE={EDGE:g}）")
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
        # ★ 低の終わりを `WEB_PRE` で決める。以前は `t+TW-20` に低の点を
        #   固定したまま立上りだけ動かしていたので、`WEB_PRE > 20` で
        #   **時刻が逆行して PWL が壊れていた**（40ns の結果は無効だった）。
        web += [(t, VDD), (t + 20, 0), (t + TW - WEB_PRE, VDD)]
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


def read_time():
    """読出し直前の時刻（`chk` と同じ）。**式はここ 1 か所だけに置く。**

    ★ `main` の要約で `T0 - 5` と書いて `NameError` を出した（`T0` は
      `build_read` のローカル）。**同じ時刻を 2 か所で別々に書いていた**のが
      原因なので、式を 1 つにまとめた（決定 21 の小さい版）。
    """
    return write_phase()[3] + SETTLE - 5


def tlat_inner(netlist):
    """`TLAT` の**内部ノード**（ポートでも電源でもないもの）を全部返す。

    ★ どのノードが反転しそこねているかを名前で決め打ちしない（決定 22）。
    4 本しかないので全部測る。
    """
    lines = []
    for ln in open(netlist, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("+") and lines: lines[-1] += " " + ln[1:].strip()
        else: lines.append(ln)
    ports, nodes, cur = [], [], None
    for ln in lines:
        t = ln.split()
        if not t: continue
        if t[0].lower() == ".subckt":
            cur = t[1]
            if cur == "TLAT": ports = t[2:]
            continue
        if t[0].lower() == ".ends": cur = None; continue
        if cur == "TLAT" and t[0].upper().startswith(("M", "XM")):
            for n in t[1:5]:
                if n not in ports and n not in nodes:
                    nodes.append(n)
    return nodes


def tlat_rows(netlist):
    """行ごとに 1 個ずつ TLAT を選び、`(インスタンス名, WR, WRB, RD, 記憶ノード)` を返す。

    ★ **記憶ノードの名前は写さない**（抽出は `n4`、設計は `n3`。決定 22）。
    `.SUBCKT TLAT` の中で「ゲートが `WR`/`WRB` で、片方の端子が `D`」の
    2 素子＝書込みトランスファゲートを見つけ、その**反対側の端子**を取る。
    """
    lines = []
    for ln in open(netlist, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("+") and lines: lines[-1] += " " + ln[1:].strip()
        else: lines.append(ln)
    order, body = None, []
    cur = None
    for ln in lines:
        t = ln.split()
        if not t: continue
        if t[0].lower() == ".subckt":
            cur = t[1]
            if cur == "TLAT": order = t[2:]
            continue
        if t[0].lower() == ".ends": cur = None; continue
        if cur == "TLAT" and t[0].upper().startswith(("M", "XM")):
            body.append(t)
    if not order:
        return []
    store = None
    for t in body:                                  # d g s b …
        d, g, sn = t[1], t[2], t[3]
        if g in ("WR", "WRB") and "D" in (d, sn):
            store = sn if d == "D" else d
            break
    if store is None:
        return []
    rows, seen, top = [], set(), False
    for ln in lines:
        t = ln.split()
        if not t: continue
        if t[0].lower() == ".subckt": top = (t[1] == CELL); continue
        if t[0].lower() == ".ends": top = False; continue
        if top and t[0].upper().startswith("X") and t[-1] == "TLAT":
            m = dict(zip(order, t[1:1 + len(order)]))
            if m["WR"] in seen: continue
            seen.add(m["WR"])
            rows.append((t[0], m["WR"], m["WRB"], m["RD"], store))
    return rows


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
    L.append(f".meas tran chk FIND v(QQ0) AT={read_time():g}n")
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
        # ★ **word0 を書いている瞬間**を切って見る。範囲の MAX/MIN では
        #   「立った」ことしか分からず、**同時に**立っているかが分からない。
        tw0 = IDLE + TW / 2
        for i, n in enumerate(tlat_nets(netlist, "WR")):
            L.append(f".meas tran wrat{i} FIND v(xu.{n}) AT={tw0:g}n")
        for i, n in enumerate(tlat_nets(netlist, "D")):
            L.append(f".meas tran dat{i} FIND v(xu.{n}) AT={tw0:g}n")
        L.append(f".meas tran webat FIND v(WEB) AT={tw0:g}n")
        # ★ 行ごとに 1 個、TLAT の中を覗く。WR と **WRB が相補か**（帰還の
        #   トランスファゲートが切れているか）と、記憶ノードが動いたか。
        inner = tlat_inner(netlist)
        for i, (inst, wr, wrb, rd, node) in enumerate(tlat_rows(netlist)):
            L.append(f".meas tran wrbat{i} FIND v(xu.{wrb}) AT={tw0:g}n")
            L.append(f".meas tran st{i} FIND v(xu.{inst}.{node}) AT={tw0:g}n")
            # ★ **読出しの瞬間**（chk と同じ時刻）。書いた行がまだ 0 を
            #   持っているか、そしてそのとき **RD が立っているのはどの行か**。
            L.append(f".meas tran str{i} FIND v(xu.{inst}.{node}) AT={read_time():g}n")
            # ★ **5 つのワードを書くあいだの足取り**。word0 に 0 を書いたあと、
            #   どのワードの書込みで消えるのかを見る（WR の MAX だけでは
            #   「いつ立ったか」が分からない）。
            for k in range(len(WORDS)):
                L.append(f".meas tran w{k}s{i} FIND v(xu.{inst}.{node}) "
                         f"AT={IDLE + TW / 2 + k * TW:g}n")
                # ★ **中点の値ではなく窓の最大**にする。中点の FIND では
                #   「そのワードの途中で一瞬立った」を取りこぼす。
                L.append(f".meas tran w{k}r{i} MAX v(xu.{wr}) "
                         f"FROM={IDLE + k * TW:g}n TO={IDLE + (k + 1) * TW:g}n")
                # ★ **WRB も追う**。WR = 0 のとき WRB = 5 でなければ
                #   帰還のトランスファゲートが**両方とも off** になり、
                #   記憶ノードが浮く（浮けば接合のリークで VDD 側へ戻る）。
                L.append(f".meas tran w{k}b{i} FIND v(xu.{wrb}) "
                         f"AT={IDLE + TW / 2 + k * TW:g}n")
            # ★ **いつ反転したか**を直接測る。word0 の書込みが終わったあと、
            #   記憶ノードが最初に VDD/2 を上向きに跨いだ時刻。
            L.append(f".meas tran flip{i} WHEN v(xu.{inst}.{node})={VDD / 2:g} "
                     f"RISE=1 TD={IDLE + TW - 10:g}n")
            # ★ **WEB を上げてから内部の WR が落ちるまで**の実時間。
            #   これが「アドレスを変える前に空けるべき余裕」そのもの。
            L.append(f".meas tran wfall{i} WHEN v(xu.{wr})={VDD / 2:g} FALL=1 "
                     f"TD={IDLE + TW - WEB_PRE - 1:g}n")
            # ★ 読む行だけは**セルの内部ノードを全部**追う。どのノードが
            #   反転しそこねているかを見る。1 行ぶんなので本数は少ない。
            for j, nd in enumerate(inner):
                for k in range(len(WORDS)):
                    L.append(f".meas tran n{j}w{k}r{i} FIND v(xu.{inst}.{nd}) "
                             f"AT={IDLE + TW / 2 + k * TW:g}n")
            L.append(f".meas tran rdat{i} FIND v(xu.{rd}) AT={read_time():g}n")
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
    """接合パラメータを触った写しを作り、その道を返す（U2 の切り分け用）。

    ★ **`area` / `perim` / `both` は「落とす」= PDK の既定式に戻す**:
        AS/AD = w*sdwidth        PS/PD = 2*(sdwidth+w)
      つまり**設計ネットリストと同じ扱い**になる。抽出の実測値はどれも
      この既定以下（全素子で比 0.21〜1.00）なので、**接合が増える方向**に
      しか動かせない。

    ★ **`zero-*` は 0 を明示的に入れる** = 接合を消す。容量そのものが
      効いているのかを試せるのはこちらだけ。
      **以前の記録「PS/PD だけ外すと動く」は、こちらのことだった可能性がある**
      （消すのと 0 を入れるのは別物）。
    """
    zero = mode.startswith("zero-")
    what = mode.split("-")[-1]
    out = netlist.replace(".spi", "") + f"_{mode}.spi"
    n = 0
    with open(netlist, encoding="utf-8") as f, open(out, "w", encoding="utf-8") as g:
        for ln in f:
            if ln[:2].upper() == "XM" or ln[:1].upper() == "M":
                before, body = ln, ln.rstrip("\n")
                if what in ("area", "both"):
                    body = RE_AREA.sub("", body)
                    if zero:
                        body += " AS=0 AD=0"
                if what in ("perim", "both"):
                    body = RE_PERIM.sub("", body)
                    if zero:
                        body += " PS=0 PD=0"
                ln = body + "\n"
                n += (ln != before)
            g.write(ln)
    print(f"  {n} 行を書き換えた（{'0 を入れた' if zero else 'PDK の既定式に戻した'}）")
    return out



def sweep_edge(a, vals, knob="edge"):
    """刺激の縁を振って、**書込みが保持できる境界**を出す（U7 / U2）。

    `TLAT` にキーパーが無いので、トランスファゲートが閉じるときの電荷注入に
    対する余裕は記憶ノードの容量そのもの。**縁が鋭いほど注入が大きい**ので、
    「どこまで鋭い縁なら保持できるか」が書込みパスの実際の要求になる。

    ★ 縁は `WEB` だけでなく `ADD` / `D` にも同じ値がかかる（`step()` が
      全部の刺激を同じ台形にする）。**分けて振りたくなったらここを直す。**
    """
    global EDGE, WEB_PRE
    label = {"edge": "縁", "webpre": "WEB 余裕"}[knob]
    rows = []
    for e in vals:
        if knob == "edge": EDGE = e
        else: WEB_PRE = e
        v = run(build_read(a.netlist, 0, SLEWS[3], True), f"{knob}{e:g}")
        chk = v.get("chk")
        ok = chk is not None and chk < VDD / 2
        rows.append((e, chk, ok))
        print(f"  {label} {e:>6.2f} ns  読出し直前の Q[0] = "
              f"{'—' if chk is None else format(chk, '.3f')}  "
              f"{'保持する' if ok else '保持しない'}")
    good = [e for e, _, ok in rows if ok]
    bad = [e for e, _, ok in rows if not ok]
    print()
    if good and bad:
        print(f"  ★ 境界: {max(bad):g} ns では保持せず、{min(good):g} ns では保持する")
        print(f"     -> {label}は **{min(good):g} ns 以上**が要る（この条件で）")
    elif good:
        print(f"  ★ 振った範囲（{min(vals):g}〜{max(vals):g} ns）では**全部保持した**")
    else:
        print(f"  ★ 振った範囲（{min(vals):g}〜{max(vals):g} ns）では**どれも保持しない**")
    print(f"  デッキとログ: {HERE}/decks/{RUNTAG} / {HERE}/logs/{RUNTAG}")


def probe_summary(v):
    """`--probe` の測定値を段ごとに読み下す。

    ★ **表示だけの関数にしておく**（`main` の中に書いていたら `T0` の
      `NameError` を出した）。ここだけ切り出してあれば作り物の値で試せる。
    """
    num = lambda p: sorted((k for k in v if k.startswith(p) and k[len(p):].isdigit()),
                           key=lambda k: int(k[len(p):]))
    # ★ **`or` で既定値を入れない**。測定値 0.0 は falsy なので
    #   `v[k] or VDD` が 0V を VDD に化けさせる（実際に「0 を保持している行 = []」
    #   と出た）。欠測は None なので、None かどうかで判断する。
    val = lambda k, d: d if v.get(k) is None else v[k]
    wr, dmx, dmn = num("wr"), num("dmax"), num("dmin")
    wat, dat, strv, rdv = num("wrat"), num("dat"), num("str"), num("rdat")
    hi = [k for k in wr if val(k, 0) > VDD / 2]
    print(f"  WEB の最低値 = {v.get('webmin')} "
          f"（0V 付近まで下がっていれば書込み指示は届いている）")
    print(f"  行選択の WR 線 {len(wr)} 本のうち **{len(hi)} 本**が VDD/2 を超えた")
    if wr:
        print("    最大値: " + ", ".join(f"{v[k]:.2f}" for k in wr[:8])
              + (" …" if len(wr) > 8 else ""))
    if dmx:
        sw = [k for k in dmx if val(k, 0) > VDD / 2
              and val("dmin" + k[4:], VDD) < VDD / 2]
        print(f"  セル側の D 線 {len(dmx)} 本のうち **{len(sw)} 本**が 0V と 5V の両方に振れた")
        print("    最大: " + ", ".join(f"{v[k]:.2f}" for k in dmx)
              + "\n    最小: " + ", ".join(f"{v[k]:.2f}" for k in dmn))
    if wat:
        on = [int(k[4:]) for k in wat if val(k, 0) > VDD / 2]
        print(f"\n  ★ word0（= 0x00）を書いている瞬間 t={IDLE + TW / 2:g}ns:")
        print(f"    WEB = {v.get('webat'):.2f}  "
              f"WR が立っている行 = **{len(on)} 本**（1 本であるべき）")
        print("    D = " + " ".join(f"{v[k]:.1f}" for k in dat)
              + "  （0x00 なので全部 0 であるべき）")
        for i in on:
            print(f"    選ばれた行 {i}: WR = {v.get(f'wrat{i}'):.2f} / "
                  f"WRB = {v.get(f'wrbat{i}'):.2f}  （相補でなければ帰還が切れていない）")
            print(f"      記憶ノード = {v.get(f'st{i}'):.2f}  "
                  f"（D = 0 を書いているので 0 に落ちるべき）")
    if strv:
        zero = [int(k[3:]) for k in strv if val(k, VDD) < VDD / 2]
        rdon = [int(k[4:]) for k in rdv if val(k, 0) > VDD / 2]
        print(f"\n  ★ 読出しの瞬間 t={read_time():g}ns:")
        print(f"    0 を保持している行 = {zero}")
        print(f"    RD が立っている行   = {rdon}")
        print("    -> 重なっていなければ「書く行」と「読む行」が食い違っている")
        # ★ 読む行の足取りを 5 ワードぶん並べる。どの書込みで消えるかが見える。
        for r in rdon:
            tr = []
            for k in range(len(WORDS)):
                st, wr_ = v.get(f"w{k}s{r}"), v.get(f"w{k}r{r}")
                if st is None: continue
                wb = v.get(f"w{k}b{r}")
                wr_lbl = ("**立つ**" if (wr_ or 0) > VDD / 2 else "0")
                hold = "" if wb is None else (
                    "  帰還 **切れている**" if (wb if wb is not None else 0) < VDD / 2
                    and (wr_ or 0) < VDD / 2 else "  帰還 ○")
                tr.append(f"word{WORDS[k][0]}: 記憶 {st:.1f} "
                          f"/ WR(窓の最大) {wr_lbl}"
                          f" / WRB {'-' if wb is None else format(wb, '.1f')}{hold}")
            nodes = sorted({int(k[1:k.index("w")]) for k in v
                            if k.startswith("n") and "w" in k and k.endswith(f"r{r}")
                            and k[1:k.index("w")].isdigit()})
            for j in nodes:
                vals = [v.get(f"n{j}w{k}r{r}") for k in range(len(WORDS))]
                if any(x is not None for x in vals):
                    tr.append("  セル内ノード %d: " % j
                              + " ".join("-" if x is None else f"{x:.1f}" for x in vals))
            wf = v.get(f"wfall{r}")
            if wf is not None:
                up = IDLE + TW - WEB_PRE
                tr.append(f"  WEB↑({up:g} ns) から内部 WR が落ちるまで = "
                          f"{wf * 1e9 - up:.1f} ns")
            fl = v.get(f"flip{r}")
            if fl is not None:
                tr.append(f"  ★ 反転した時刻 = {fl * 1e9:.1f} ns"
                          f"（word0 の書込みは {IDLE:g}〜{IDLE + TW:g} ns）")
            if tr:
                print(f"    行 {r}（読む行）の足取り:")
                for x in tr: print(f"      {x}")
                print(f"      読出し時 {val(f'str{r}', VDD):.1f}")
    print("  -> WR が立たないならデコーダ側、D が振れないなら入力バッファ側、"
          "どちらも正常ならラッチ側")


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
    ap.add_argument("--web-pre", default=None,
                    help="WEB を上げてから次のワードのアドレス/データを変える"
                         "までの余裕 [ns]（既定 5）。**カンマ区切りで掃引できる**")
    ap.add_argument("--edge", default=None,
                    help="刺激の縁の時間 [ns]（既定 0.1）。**カンマ区切りで複数**"
                         "書くと掃引して、書込みが保持できる境界を出す（U7 / U2）")
    ap.add_argument("--quick", action="store_true",
                    help="代表 1 点（ADD[0] / slew 1.5ns / rise）だけ回す。"
                         "書込みが効いているかを見るだけならこれで足りる")
    ap.add_argument("--strip", default="none",
                    choices=["none", "area", "perim", "both",
                             "zero-area", "zero-perim", "zero-both"],
                    help="接合パラメータを触った写しで回す（U2 の切り分け）。"
                         "area=AS/AD / perim=PS/PD / both=両方。"
                         "**そのままは PDK の既定式に戻す**（＝増える方向）。"
                         "zero- を付けると 0 を入れる（＝接合を消す）")
    a = ap.parse_args()
    need_ngspice()                              # 先に確かめる（決定 23）
    global PORTS, RUNTAG, PROBE
    PROBE = a.probe
    RUNTAG = ("ext" if a.ext else "src") + ("" if a.strip == "none" else f"_{a.strip}")
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
    global EDGE, WEB_PRE
    edges = ([float(x) for x in a.edge.split(",")] if a.edge else [])
    if len(edges) == 1:
        EDGE = edges[0]
    pres = ([float(x) for x in a.web_pre.split(",")] if a.web_pre else [])
    if len(pres) == 1:
        WEB_PRE = pres[0]
    if a.strip != "none":
        a.netlist = strip_junction(a.netlist, a.strip)
        print(f"  接合パラメータ {a.strip} の写し: {a.netlist}")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if len(edges) > 1:                      # ★ 掃引なら普通の測定はしない
        sweep_edge(a, edges, "edge")
        return
    if len(pres) > 1:
        sweep_edge(a, pres, "webpre")
        return
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
                # ★ `chk` は読出し直前の Q[0]。**期待値は向きで違う** —
                #   rise はエッジ前のアドレスが 0（word0 = 0x00）なので 0V、
                #   fall は 1<<bit（word1 = 0xFF）なので 5V が正しい。
                #   これを書いておかないと fall の 5.0 を誤報する。
                _c = v.get("chk")
                _exp = 0.0 if j[3] else VDD
                _ok = _c is not None and abs(_c - _exp) < VDD / 2
                print(f"  [{k+1:>2}/{len(jobs)}] ADD[{j[0]}] slew {j[2]:>5}ns "
                      f"{'rise' if j[3] else 'fall'}  d(CL=100fF) = "
                      f"{(v.get('d3') or 0)*1e9:.2f} ns  "
                      f"chk = {'—' if _c is None else format(_c, '.3g')}"
                      f"（期待 {_exp:g}V {'○' if _ok else '×'}）", flush=True)
        if a.quick:
            # ★ 代表 1 点だけなので表は作らない。**書込みが効いたかだけ**出す。
            v = out[(0, 3, True)]
            print(f"\n  読出し直前の Q[0] = {v.get('chk')}  "
                  f"（word0 = 0x00 なので **0V 付近なら書込みが効いている**。"
                  f"5V 付近なら効いていない）")
            print(f"  ADD[0] -> Q[0] の遅延 = "
                  f"{(v.get('d0') or 0)*1e9:.2f} ns（0.00 は測れなかったということ）")
            if a.probe:
                try:
                    probe_summary(v)
                except Exception as e:
                    # ★ **要約の表示で測定結果を捨てない**（決定 23）。
                    #   25 秒回したあとに表示の不具合で全部消えるのは割に合わない。
                    print(f"  ★ probe の要約でこけた: {type(e).__name__}: {e}")
                    print("     測定そのものはログに残っている")
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

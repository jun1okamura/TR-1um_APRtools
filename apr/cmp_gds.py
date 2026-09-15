#!/usr/bin/env python3
"""cmp_gds.py -- 2 つの GDS が**同じものか**を判定する。

  usage:
    python3 apr/cmp_gds.py <base.gds> <new.gds>
    python3 apr/cmp_gds.py HEAD:layout/step10/route_step_6_squeezed.gds \
                           layout/step10/route_step_6_squeezed.gds
    python3 apr/cmp_gds.py --dir <baseDir> <newDir>      # 同名ファイルを総当たり

## なぜ生の md5 ではいけないか

KLayout は保存のたびに `BGNLIB`(0x0102) / `BGNSTR`(0x0502) に**その時刻**を
書く。同じ図形でも実行するたびに md5 が変わるので、生の md5 で「一致しない」
と言っても何の情報も無い。ここではそのレコードの中身をゼロで潰してから
md5 を取る（**正規化 md5**）。

## 正規化 md5 が違っても「違う」とは限らない

- **ラベルだけの差**（`VDD`->`vdd` のような改名）は図形を変えない
- **KLayout のバージョン差**でバイト列の書き方が変わることがある
  （セル参照の並び、配列の畳み方、実数の丸め）

なので不一致のときは、`klayout.db` があれば**幾何そのもの**を比べる:

    Region(base) ^ Region(new)   が層ごとに空か

これが全層で空なら「図形は 1 つも動いていない」と言い切れる。
テキスト（ラベル）は別に集合として差を出す。

  「md5 が違う」で止めない。**何が違うのかを言えるところまで出す。**
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile

TS_RECORDS = (0x0102, 0x0502)      # BGNLIB / BGNSTR


def norm_md5(path):
    """タイムスタンプのレコードをゼロで潰してから md5。"""
    d = open(path, "rb").read()
    i, out = 0, bytearray()
    while i < len(d) - 4:
        ln, rt = struct.unpack(">HH", d[i:i + 4])
        if ln < 4:
            break
        body = bytes(d[i + 4:i + ln])
        if rt in TS_RECORDS:
            body = b"\x00" * len(body)
        out += struct.pack(">HH", ln, rt) + body
        i += ln
    return hashlib.md5(out).hexdigest()


def resolve(spec, tmpdir):
    """`REF:path` なら git から取り出して一時ファイルに置く。"""
    if ":" in spec and not os.path.exists(spec):
        ref, _, path = spec.partition(":")
        blob = subprocess.run(["git", "show", f"{ref}:{path}"],
                              capture_output=True)
        if blob.returncode != 0:
            raise SystemExit(f"git show {ref}:{path} が失敗した\n"
                             f"  {blob.stderr.decode(errors='replace').strip()}")
        out = os.path.join(tmpdir, ref.replace("/", "_") + "_"
                           + os.path.basename(path))
        open(out, "wb").write(blob.stdout)
        return out, spec
    if not os.path.exists(spec):
        raise SystemExit(f"{spec} が無い")
    return spec, spec


def tops(ly):
    """トップセル名の集合。

    **`Layout.top_cell()` は使わない。** 参照されないセルが 1 つでも
    残っていると「トップが複数ある」で例外になる。配置配線の中間 GDS には
    使われなかったライブラリセルが混ざることが実際にある（そしてそれ自体が
    2 つの GDS の差になる）ので、**トップの集合そのものを比較対象にする**。"""
    return {c.name for c in ly.top_cells()}


def geom_diff(base, new, top=None, verbose=True):
    """層ごとに Region の XOR を取る。戻り値は (差のある層, ラベル差, 注記)。

    比較できなければ None を返す（`klayout` モジュールが無いとき）。"""
    try:
        import klayout.db as db
    except ImportError:
        return None

    def load(p):
        ly = db.Layout()
        ly.read(p)
        return ly

    la, lb = load(base), load(new)
    notes = []

    ta_, tb_ = tops(la), tops(lb)
    if top:
        roots = {top}
        for ly, tag in ((la, "base"), (lb, "new")):
            if ly.cell(top) is None:
                raise SystemExit(f"{tag} にセル {top} が無い")
    elif ta_ == tb_:
        roots = ta_
        if len(roots) > 1:
            notes.append(f"トップセルが {len(roots)} 個（両方同じ）: "
                         f"{sorted(roots)}  ※参照されないセルが残っている")
    else:
        roots = ta_ | tb_
        notes.append(f"**トップセルの顔ぶれが違う** base のみ {sorted(ta_ - tb_)}"
                     f" / new のみ {sorted(tb_ - ta_)}")

    ca, cb = {c.name for c in la.each_cell()}, {c.name for c in lb.each_cell()}
    if ca != cb:
        notes.append(f"セル定義 base {len(ca)} / new {len(cb)} 本 — "
                     f"base のみ {sorted(ca - cb)[:6]} / new のみ {sorted(cb - ca)[:6]}")

    def regions(ly, lay, dt):
        r = db.Region()
        idx = ly.find_layer(lay, dt)
        if idx is None:
            return r
        for name in sorted(roots):
            c = ly.cell(name)
            if c is not None:
                r.insert(c.begin_shapes_rec(idx))
        return r

    layers = sorted({(li.layer, li.datatype) for li in la.layer_infos()} |
                    {(li.layer, li.datatype) for li in lb.layer_infos()})
    bad = []
    for lay, dt in layers:
        x = (regions(la, lay, dt) ^ regions(lb, lay, dt))
        x.merge()
        if not x.is_empty():
            bad.append(((lay, dt), x.count(), round(x.area() / 1e6, 3)))
            if verbose:
                print(f"       ({lay},{dt}) 差 {x.count()} 図形 "
                      f"/ {x.area()/1e6:.3f} um^2")

    def texts(ly):
        out = set()
        for li in ly.layer_infos():
            idx = ly.find_layer(li)
            if idx is None:
                continue
            for name in sorted(roots):
                c = ly.cell(name)
                if c is None:
                    continue
                for it in c.begin_shapes_rec(idx):
                    sh = it.shape()
                    if sh.is_text():
                        t = sh.text.transformed(it.trans())
                        out.add((sh.text.string, li.layer, li.datatype,
                                 round(t.x * ly.dbu, 3), round(t.y * ly.dbu, 3)))
        return out

    ta, tb = texts(la), texts(lb)
    return bad, (ta - tb, tb - ta), notes


def compare(base_spec, new_spec, tmpdir, quiet=False, top=None):
    base, blabel = resolve(base_spec, tmpdir)
    new, nlabel = resolve(new_spec, tmpdir)
    ma, mb = norm_md5(base), norm_md5(new)
    name = os.path.basename(new)
    if ma == mb:
        print(f"[  ok  ] {name:42s} 正規化 md5 一致  {ma[:16]}…")
        return True
    print(f"[  NG  ] {name:42s} 正規化 md5 不一致")
    print(f"         base {ma[:16]}…  {os.path.getsize(base):,} B  {blabel}")
    print(f"         new  {mb[:16]}…  {os.path.getsize(new):,} B  {nlabel}")
    if quiet:
        return False
    r = geom_diff(base, new, top)
    if r is None:
        print("         （`pip install klayout` があれば幾何とラベルの差まで出せる）")
        return False
    bad, (only_a, only_b), notes = r
    for n in notes:
        print(f"         ! {n}")
    if not bad:
        print("         → **幾何は完全一致**（Region XOR が全層で空）")
    else:
        print(f"         → 幾何が違う層 {len(bad)} 個 ↑")
    if only_a or only_b:
        sa = sorted({t[0] for t in only_a})
        sb = sorted({t[0] for t in only_b})
        print(f"         ラベル: base のみ {len(only_a)} / new のみ {len(only_b)}")
        if sa != sb or len(sa) <= 8:
            print(f"           {sa[:8]} -> {sb[:8]}")
    elif not bad:
        print("         → ラベルも一致。差はバイト列の書き方だけ"
              "（KLayout のバージョン差、あるいは使われていないセルの有無）")
    return not bad and not only_a and not only_b and not notes


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="基準。`HEAD:path` のように git の参照も使える")
    ap.add_argument("new")
    ap.add_argument("--dir", action="store_true",
                    help="2 つをディレクトリとして扱い、同名の .gds を総当たり")
    ap.add_argument("--top", default=None,
                    help="このセルだけを見る（既定: トップセル全部。"
                         "参照されないセルが残っていても落ちない）")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="md5 だけ見る（幾何の比較をしない）")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        if not a.dir:
            return 0 if compare(a.base, a.new, tmp, a.quiet, a.top) else 1
        names = sorted(f for f in os.listdir(a.new) if f.endswith(".gds")
                       if os.path.exists(os.path.join(a.base, f)))
        if not names:
            raise SystemExit("同名の .gds が 1 つも無い")
        ng = 0
        for f in names:
            if not compare(os.path.join(a.base, f), os.path.join(a.new, f),
                           tmp, a.quiet, a.top):
                ng += 1
        print(f"\n{len(names)} 本中 {len(names)-ng} 本一致 / {ng} 本不一致")
        return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())

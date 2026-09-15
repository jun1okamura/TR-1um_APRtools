#!/usr/bin/env python3
"""selfcheck.py -- 移行の下ごしらえを KLayout 無しで点検する。

    cd <設計リポジトリ>
    python3 <APRtools>/apr/selfcheck.py

見るもの:
  1. `config.py` が読めて `finalize()` / `check()` が通るか
  2. 入力ファイルが実在するか
  3. `stdcell/` のライブラリが設計リポジトリの `lef/` と**バイト一致**か
     （一致していれば、成果物の md5 比較が意味を持つ）
  4. TAP 列とコア幾何の整合
  5. PDK が解決できるか（デッキ・モデル・PCell・フレーム）
"""
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apr_path  # noqa: F401,E402
import rules  # noqa: E402

OK, NG, WARN = "  ok  ", "  NG  ", " warn "
_bad = 0


def line(tag, msg):
    global _bad
    if tag == NG:
        _bad += 1
    print(f"[{tag}] {msg}")


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def main():
    global _bad
    try:
        import config as cfg
    except Exception as e:
        line(NG, f"config.py が読めない: {e}")
        return 1
    line(OK, f"config.py 読み込み / check() 通過  ROOT={cfg.ROOT}")

    # ---- 提出物の命名規則（`info.yaml` の注記）--------------------------
    #   * "tr_1um_" で始まる
    #   * GitHub 名を含む（一意にするため）
    #   * 同じ人が複数出すので**設計の識別子**も要る
    # -> `tr_1um_<GitHub 名>_<識別子>`。区切りが 2 つ以上あるかを見る。
    # GitHub 名そのものは APRtools からは分からないので、**形だけ**検査する。
    # 2026-09-15: TD4 が `tr_1um_jun1okamura`（識別子なし）、SCLK_SPI が
    # `tr_1um_3wire_SPI`（GitHub 名なし）で提出されていた。
    import re as _re
    _top = getattr(cfg, "CHIP_TOP_CELL", "") or ""
    if not _re.match(r"^tr_1um_[A-Za-z0-9][A-Za-z0-9-]*_[A-Za-z0-9_]+$", _top):
        line(NG, f"CHIP_TOP_CELL {_top!r} が命名規則に合わない"
                 "（tr_1um_<GitHub 名>_<設計の識別子>）")
    else:
        line(OK, f"CHIP_TOP_CELL  {_top}")
    _yaml = os.path.join(cfg.ROOT, "info.yaml")
    if os.path.exists(_yaml):
        _m = _re.search(r'^\s*top_cell:\s*"([^"]+)"', open(_yaml, encoding="utf-8").read(), _re.M)
        if _m and _m.group(1) != _top:
            line(NG, f"info.yaml の top_cell {_m.group(1)!r} と "
                     f"config.CHIP_TOP_CELL {_top!r} が違う")

    print("\n--- 0. 実行環境 ---")
    print(f"       python            {sys.executable}")
    try:
        import klayout as _kl
        _v = getattr(_kl, "__version__", "?")
        line(OK, f"klayout モジュール  {_v}（pip。配置・配線・抽出に要る）")
    except ImportError:
        line(NG, "klayout の Python モジュールが無い"
                 f" -> {sys.executable} -m pip install klayout")
        print("       ※ KLayout アプリ（`klayout` コマンド）とは別物。"
              "アプリだけでは import できない。")
    _exe = shutil.which(os.environ.get("KLAYOUT", "klayout"))
    line(OK if _exe else WARN,
         f"klayout コマンド      {_exe or '見つからない（drc_pdk.py / lvs_pdk.py で要る）'}")
    if not _exe:
        print("       ※ シェルの alias は subprocess から見えない。"
              "`export KLAYOUT=/Applications/klayout.app/Contents/MacOS/klayout`")
    _ng = shutil.which("ngspice")
    line(OK if _ng else WARN,
         f"ngspice               {_ng or '見つからない（機能回帰で要る）'}")
    # APRtools 自身の「パスと名前」を静的に見る（移行で壊れたのは全部そこ）
    try:
        import subprocess as _sp
        _r = _sp.run([sys.executable, os.path.join(HERE, "lint.py")],
                     capture_output=True, text=True)
        _sum = next((l for l in _r.stdout.splitlines()
                     if l.startswith("SUMMARY ")), "SUMMARY NG=? warn=?")
        _kv = dict(kv.split("=", 1) for kv in _sum.split()[1:])
        line(OK if _r.returncode == 0 else NG,
             f"apr/lint.py            NG {_kv.get('NG')} / warn {_kv.get('warn')}"
             f"（{_kv.get('files')} ファイル）")
        if _r.returncode != 0:
            print("       python3 " + os.path.join(HERE, "lint.py") + " で詳細")
    except Exception as _e:                       # lint 自体で止めない
        line(WARN, f"apr/lint.py            回せなかった: {_e}")

    print("\n--- 1. フロアプラン ---")
    print(f"       TOP_CELL_NAME     {cfg.TOP_CELL_NAME}")
    print(f"       N_ROWS            {cfg.N_ROWS}")
    print(f"       CORE_WIDTH        {cfg.CORE_WIDTH_TRACKS} トラック x {cfg.TRACK_PITCH}"
          f" = {cfg.CORE_WIDTH_UM} um")
    print(f"       CH_HEIGHTS        {cfg.CH_HEIGHTS}")
    print(f"       配置パラメータ    PAD_WEIGHT={cfg.PAD_WEIGHT}"
          f"  PLACE_SEED={cfg.PLACE_SEED}"
          f"  restarts={cfg.PLACE_RESTARTS}"
          f"  order_passes={cfg.PLACE_ORDER_PASSES}")
    _ovr = [k for k in ("PAD_WEIGHT", "PLACE_SEED", "PLACE_RESTARTS",
                        "PLACE_ORDER_PASSES", "PLACE_BALANCE_TOL")
            if os.environ.get("APR_" + k) is not None]
    if _ovr:
        line(WARN, f"環境変数が config.py を上書きしている: "
                   + ", ".join("APR_" + k for k in _ovr))
    _, stack_h = cfg.row_y()
    print(f"       行スタック総高    {stack_h} um（圧縮前）")
    gaps = [round(b - a, 3) for a, b in zip(cfg.TAP_X, cfg.TAP_X[1:])]
    print(f"       TAP_X             {cfg.TAP_X}")
    print(f"       TAP 間隔          {gaps}  最大 {max(gaps) if gaps else 0}"
          f" / 上限 {cfg.TAP_PITCH}")
    if gaps and max(gaps) <= cfg.TAP_PITCH + 1e-6:
        line(OK, f"TAP 列 {len(cfg.TAP_X)} 本で TAP_PITCH に収まる")
    bbox_max = cfg.CORE_WIDTH_UM + 2 * rules.NWELL_OVERHANG_X
    line(OK if bbox_max <= rules.FRAME_OPENING_UM else NG,
         f"コア bbox 最大 {bbox_max} <= 開口 {rules.FRAME_OPENING_UM}")
    print(f"       CORE_OFFSET_X（公称） {cfg.CORE_OFFSET_X_NOMINAL}"
          "   ※実際は native bbox の中心で決まる")

    print("\n--- 2. 入力 ---")
    for name in ("LIB_LEF", "LIB_GDS", "LEF_PATH", "CELL_GDS", "LIBERTY",
                 "CELL_INFO", "NET_PATH", "LOGO_BITMAP", "FRAME_GDS"):
        p = getattr(cfg, name, None)
        if p is None:
            line(WARN, f"{name:12s} 未設定")
        elif os.path.exists(p):
            line(OK, f"{name:12s} {p}")
        else:
            line(NG, f"{name:12s} が無い: {p}")

    print("\n--- 3. stdcell が設計リポジトリの lef/ とバイト一致か ---")
    pairs = [("TR-1um_cells.lef", cfg.LIB_LEF), ("TR-1um_STDCELL.gds", cfg.LIB_GDS),
             ("TR-1um_PNR.lef", cfg.LEF_PATH), ("TR-1um_PNR.gds", cfg.CELL_GDS),
             ("tr1um_typ_5v0_25c.lib", cfg.LIBERTY)]
    for base, newp in pairs:
        oldp = os.path.join(cfg.ROOT, "lef", base)   # lint: ok 設計の写しと STDCELL 正本を突き合わせる検査そのもの
        if not os.path.exists(oldp):
            line(WARN, f"{base:24s} 設計側に無い（比較省略）")
        elif not os.path.exists(newp):
            line(NG, f"{base:24s} APRtools 側に無い")
        elif md5(oldp) == md5(newp):
            line(OK, f"{base:24s} 一致")
        else:
            line(NG, f"{base:24s} **不一致** old={md5(oldp)[:8]} new={md5(newp)[:8]}")

    print("\n--- 4. PDK ---")
    try:
        line(OK, f"pdk_root()        {cfg.pdk_root()}")
        for fn in ("pdk_tech_python", "pdk_frame_gds", "pdk_spice_models",
                   "pdk_drc_deck", "pdk_lvs_deck"):
            p = getattr(cfg, fn)()
            line(OK if os.path.exists(p) else NG, f"{fn+'()':18s} {p}")
        kind, fpath = cfg.frame_source()
        up = cfg.pdk_frame_gds_upstream()
        label = {"env": "APR_FRAME_GDS で明示指定",
                 "pending-upstream": "pdk/pending-upstream（上流 PR 待ち）",
                 "pdk": "PDK"}[kind]
        line(OK if kind == "pdk" else WARN, f"使用中のフレーム: {label}")
        print(f"       {fpath}")
        if os.path.exists(up) and os.path.abspath(fpath) != os.path.abspath(up):
            same = md5(fpath) == md5(up)
            if same:
                line(OK, "PDK 版と内容一致 -> pdk/pending-upstream/ は消してよい")
            else:
                line(WARN, "PDK 版とは別物（docs/07_frame_issue.md / U19）")
    except SystemExit as e:
        line(NG, f"PDK が解決できない: {e}")

    print("\n--- 5. 成果物の置き場 ---")
    for name in ("PLACEMENT_JSON", "SQUEEZED_GDS", "FINAL_GDS", "CHIP_CORE_GDS"):
        p = getattr(cfg, name)
        line(OK if os.path.exists(p) else WARN,
             f"{name:16s} {'既存' if os.path.exists(p) else '未生成'}  {p}")

    print()
    if _bad:
        print(f"NG {_bad} 件。上を直してから place.py を回すこと。")
        return 1
    print("すべて OK。次:")
    print("  export PYTHONHASHSEED=0")
    print(f"  python3 {HERE}/place.py && python3 {HERE}/route.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""apr_path.py -- 設計リポジトリのルートを sys.path に足す。

`apr/` のスクリプトは**設計ルートから**実行する:

    cd <設計>; python3 $APRTOOLS/apr/route.py

このとき sys.path[0] はスクリプトのあるディレクトリ（= apr/）なので、
設計ルートの `config.py` が見つからない。各スクリプトは

    sys.path.insert(0, HERE)      # 元からある
    import apr_path               # noqa: F401  <- これを足す
    import config as cfg          # noqa: E402

の順で書く。`APR_DESIGN_ROOT` で明示もできる。

**末尾に足す**（先頭ではない）ので、設計側に同名ファイルがあっても
`apr/` のモジュールを隠さない。

★ **規約を破ったときに何が起きるかまで面倒を見る**（U57）。APRtools 直下で
  回すと、以前は `ModuleNotFoundError: No module named 'config'` とだけ出て
  止まっていた。**規約を知らない人には直しようがない**メッセージなので、
  理由と直し方を出すようにした。`sys.exit` はしない — `selfcheck.py` は
  「config.py が読めない」を**自分で NG として報告する**作りなので、
  例外のまま渡して途中で殺さない。
"""
import os
import sys

DESIGN_ROOT = os.path.abspath(os.environ.get("APR_DESIGN_ROOT", os.getcwd()))
CONFIG_PATH = os.path.join(DESIGN_ROOT, "config.py")
HAS_CONFIG = os.path.exists(CONFIG_PATH)

if DESIGN_ROOT not in sys.path:
    sys.path.append(DESIGN_ROOT)

# ★ **設計の config.py は「道」ではなく「ファイル」で読む**（2026-09-18、U94）。
#   上の `append` は sys.path の**末尾**なので、`config` という名前が
#   **ほかの場所にもある**とそちらが勝つ。実際に踏んだ:
#     仮想環境（`.venv`）に pip の `config` パッケージが入っていると、
#     `import config` がそれを掴み、
#       AttributeError: module 'config' has no attribute 'SYN_TOP'
#       AttributeError: module 'config' has no attribute 'ROW_HEIGHT_UM'
#     と出る。**「無い」ではなく「別物」**なので ModuleNotFoundError の
#     案内（下の `_ConfigHint`）にも掛からない。
#   設計ルートに `config.py` があるなら、**その 1 本を名指しで読み込んで**
#   `sys.modules["config"]` に入れる。曖昧さを残さない。
def _load_design_config():
    import importlib.util
    m = sys.modules.get("config")
    if m is not None and getattr(m, "__file__", None) and \
            os.path.abspath(m.__file__) == CONFIG_PATH:
        return                                   # すでに正しいものが入っている
    spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["config"] = mod                  # config.py 自身の import より前に置く
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        del sys.modules["config"]
        raise


if HAS_CONFIG:
    _load_design_config()


def _message():
    src = "APR_DESIGN_ROOT" if "APR_DESIGN_ROOT" in os.environ else "カレントディレクトリ"
    return (
        f"設計の config.py が無い: {CONFIG_PATH}\n"
        f"  （{src} を設計ルートとみなした）\n"
        "\n"
        "  apr/ のスクリプトは**設計ルートから**実行する:\n"
        "      cd <設計>                     # config.py がある所\n"
        "      export APRTOOLS=<APRtools>\n"
        "      export PYTHONPATH=$APRTOOLS/apr\n"
        "      python3 $APRTOOLS/apr/<script>.py\n"
        "\n"
        "  別の場所から回すなら APR_DESIGN_ROOT=<設計> を渡す。\n"
        "  設計に依らない道具（rules.py だけ要るもの）は apr_path を import しない。"
    )


class _ConfigHint:
    """`config` が**どこにも無かったとき**にだけ、読めるエラーへ差し替える。

    `sys.meta_path` の**末尾**に置くので、本物の `config.py` が見つかる限り
    ここには来ない（通常の finder が先に解決する）。
    """

    @staticmethod
    def find_spec(name, path=None, target=None):
        if name != "config" or path is not None:
            return None
        raise ModuleNotFoundError(_message(), name="config")


if not HAS_CONFIG:
    sys.meta_path.append(_ConfigHint())


class _GdstkHint:
    """`gdstk` が**入っていないとき**に、読めるエラーへ差し替える（U59）。

    `apr/` の **11 本**（`mklef` / `mkleffrm` / `cellinfo` / `mkcellinfo` /
    `gds_extract` / `verify_placement` / `pin_grid_check` /
    `normalize_prboundary` / `plot_corridors` / `plot_layout` /
    `check_cell_spice` + `macro/` 2 本）は `gdstk` で GDS を読み書きする。
    **道具ごと `klayout.db` へ移す案は見送った**（U59）。

    ★ ただし **`place` と `route` は 2026-09-17 に外れた**（U90）。
      `route.checks()` は bbox を 1 つ取るためだけ、`place.write_gds()` は
      配置 GDS を書くためだけに `gdstk` を import していて、**流れの本体は
      どちらも `klayout.db` だけで動いていた**。この 2 箇所を置き換えたので、
      **配置からチップ・`src/` まで `gdstk` 無しで回る**。
      残り 11 本はセル情報 / LEF / 抽出 / 作図で、流れの本体ではない。

    ★ **依存は隠さず、無いときに何をすればよいかを言う。** いまは関数の中で
      `ImportError: No module named 'gdstk'` が出るだけだった。

    ★ GDS を**読んで比べるだけ**なら `apr/gdsread.py`（依存なし）で足りる。
    """

    @staticmethod
    def find_spec(name, path=None, target=None):
        if name != "gdstk" or path is not None:
            return None
        raise ModuleNotFoundError(
            "gdstk が入っていない。\n"
            "  apr/ の 11 本（mklef / cellinfo / gds_extract / plot_* …）は\n"
            "  GDS の読み書きに gdstk を使う。\n"
            "  ★ place / route は gdstk 無しで回る（U90）。\n"
            "\n"
            "      pip install gdstk\n"
            "\n"
            "  ★ 手元の Linux でビルドできないことがある。その場合は\n"
            "    **Mac（フローを回す機械）で流す**こと。\n"
            "  ★ GDS を**読んで比べるだけ**なら apr/gdsread.py（依存なし）で足りる:\n"
            "      python3 apr/gdsread.py <古い.gds> <新しい.gds>",
            name="gdstk")


try:
    import gdstk as _gdstk           # noqa: F401
except ImportError:
    sys.meta_path.append(_GdstkHint())


class _NoConfig:
    """設計の `config.py` が無いときの代役（`soft_config()` が返す）。

    **設計に依らない値だけ**を持つ。設計固有の値を聞かれたら、何が足りなくて
    どうすれば良いかを言って止まる — `AttributeError` を素通りさせない。
    """

    ROOT = DESIGN_ROOT

    @staticmethod
    def disp(path):
        return path

    @staticmethod
    def show(path):
        return path

    @staticmethod
    def pdk_root():
        v = os.environ.get("TR1UM_PDK")
        if v:
            return v
        raise SystemExit(
            "PDK の場所が分からない。TR1UM_PDK を渡すか、設計ルートから実行する。")

    # ★ **設計に依らないライブラリ側の事実だけ**を通す許可制（U37、2026-09-17）。
    #   STDCELL は APRtools のもので、設計ディレクトリの外でも決まる
    #   （`area_estimate.py` が `cell_area.json` を読むのに必要）。
    #   ★ `config_base` を丸ごと素通しにはしない。設計固有の値にも既定値が
    #   あるので、黙って配ると**別設計の値で動いたように見える**
    #   （決定 22 / U25 / U26 / U36）。
    _PASS = ("STDCELL", "ROW_HEIGHT_UM", "SITE_UM")

    @staticmethod
    def stdcell_dir():
        """設計が `STDCELL` を上書きしていないときの正本の置き場。

        ★ `config_base.stdcell_dir()` は呼べない。あれは `_g()` 経由で
          **設計の名前空間**を読むので、`finalize(globals())` を通っていない
          ここでは止まる。モジュール既定（`APR_STDCELL` は反映済み）から組む。
        """
        import config_base
        return os.path.join(config_base.APR_ROOT, "stdcell", config_base.STDCELL)

    @classmethod
    def stdcell_file(cls, name):
        return os.path.join(cls.stdcell_dir(), name)

    def __getattr__(self, name):
        if name in self._PASS:
            import config_base
            return getattr(config_base, name)
        raise SystemExit(
            f"`{name}` は**設計の config.py にしかない値**。\n"
            f"  いまは設計ルートの外で動いている（{DESIGN_ROOT}）。\n"
            "  cd <設計> するか、APR_DESIGN_ROOT=<設計> を渡すか、\n"
            "  その値に当たる引数（--gds / --top など）を明示する。")


def soft_config():
    """`config` があれば本物、無ければ代役を返す。

    `--gds` のように**入力を引数で全部もらえる道具**は、設計の `config.py` が
    無くても動けた方がよい（U57）。標準セルの DRC を見るのに設計ディレクトリへ
    移らせるのは理屈が通らない。
    """
    if HAS_CONFIG:
        import config
        return config
    return _NoConfig()

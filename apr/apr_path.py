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

    def __getattr__(self, name):
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

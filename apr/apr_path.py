"""apr_path.py -- 設計リポジトリのルートを sys.path に足す。

`apr/` のスクリプトは設計ルートから実行される:

    python3 tools/APRtools/apr/route.py

このとき sys.path[0] はスクリプトのあるディレクトリ（= apr/）なので、
設計ルートの `config.py` が見つからない。各スクリプトは

    sys.path.insert(0, HERE)      # 元からある
    import apr_path               # noqa: F401  <- これを足す
    import config as cfg          # noqa: E402

の順で書く。`APR_DESIGN_ROOT` で明示もできる。

**末尾に足す**（先頭ではない）ので、設計側に同名ファイルがあっても
`apr/` のモジュールを隠さない。
"""
import os
import sys

DESIGN_ROOT = os.path.abspath(os.environ.get("APR_DESIGN_ROOT", os.getcwd()))
if DESIGN_ROOT not in sys.path:
    sys.path.append(DESIGN_ROOT)

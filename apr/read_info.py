#!/usr/bin/env python3
"""read_info.py -- `info.yaml` を読んで CI の出力変数を組み立てる。

**GDS は一切読まない。** `gds` / `lvs` / `mdp` / `pdk` の 4 セクションから
必須キーを取り、派生するファイル名（`<top>.gds` / `<top>.<lvs_ext>` /
`<top>.lyrdb` / `<top>.extracted`）を作って `$GITHUB_OUTPUT` に
`key=value` を追記する。

    python3 read_info.py [--info info.yaml]

★ **GitHub Actions のステップ用。** `GITHUB_OUTPUT` が無いと必ず失敗するので、
  手元で `info.yaml` を覗く道具ではない。
★ `lvs_flag` は `true` のみ真（`yes` / `1` は空文字になる）。
★ `click` と `PyYAML` に依存する。
★ `export_mpw.py` が「CI と同じ決め方」と言っているのはこのファイルのことだが、
  **ロジックは向こうが独自に持っている**（二重定義）。
"""
# ----- ------ ----- ----- ------ ----- ----- ------ -----
# OpenSUSI
# LICENSE: Apache License Version 2.0, January 2004
# http://www.apache.org/licenses/
# ----- ------ ----- ----- ------ ----- ----- ------ -----

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import click
import yaml


def fail(message: str) -> None:
    raise click.ClickException(message)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"info.yaml not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"Invalid YAML structure in: {path}")

    return data


def require_section(data: dict[str, Any], section_name: str) -> dict[str, Any]:
    section = data.get(section_name)
    if not isinstance(section, dict):
        fail(f"Missing or invalid section: '{section_name}'")
    return section


def require_value(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        fail(f"Missing key '{key}' in section '{section_name}'")
    value = section[key]
    if value is None or (isinstance(value, str) and not value.strip()):
        fail(f"Empty key '{key}' in section '{section_name}'")
    return value


def build_outputs(data: dict[str, Any]) -> dict[str, str]:
    gds = require_section(data, "gds")
    lvs = require_section(data, "lvs")
    mdp = require_section(data, "mdp")
    pdk = require_section(data, "pdk")

    top_cell = str(require_value(gds, "top_cell", "gds")).strip()
    gds_ext = str(require_value(gds, "extension", "gds")).strip()
    lvs_ext = str(require_value(lvs, "extension", "lvs")).strip()
    lvs_flag = "true" if str(require_value(lvs, "netlist_only", "lvs")).strip().lower() == "true" else ""
    mdp_file = str(require_value(mdp, "file", "mdp")).strip()
    pdk_repo = str(require_value(pdk, "repo", "pdk")).strip()
    pdk_ref = str(require_value(pdk, "ref", "pdk")).strip()
    pdk_dir = str(require_value(pdk, "dir", "pdk")).strip()

    return {
        "top_cell": top_cell,
        "layout": f"{top_cell}.{gds_ext}",
        "circuit": f"{top_cell}.{lvs_ext}",
        "report": f"{top_cell}.lyrdb",
        "extracted": f"{top_cell}.extracted",
        "mdp_file": mdp_file,
        "lvs_flag": lvs_flag,
        "pdk_repo": pdk_repo,
        "pdk_ref": pdk_ref,
        "pdk_dir": pdk_dir,
    }


def write_github_output(outputs: dict[str, str], output_path: Path) -> None:
    with output_path.open("a", encoding="utf-8") as f:
        for key, value in outputs.items():
            f.write(f"{key}={value}\n")


@click.command()
@click.option(
    "--info",
    "info_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("info.yaml"),
    show_default=True,
    help="Path to info.yaml",
)
def main(info_path: Path) -> None:
    data = load_yaml(info_path)
    outputs = build_outputs(data)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        fail("GITHUB_OUTPUT is not set")

    write_github_output(outputs, Path(github_output))

    for key, value in outputs.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
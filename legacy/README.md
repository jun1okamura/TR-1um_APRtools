# `legacy/` — 移植原本（read-only）

**改名しない・整形しない・動かさない。** 原本の同一性を保つのが目的で、
`apr/` のアルゴリズムがどこから来たかを後から追えるようにするためだけに置いてある。

| ディレクトリ | 出所 | 中身 |
|---|---|---|
| `async_i2c/` | `TR-1um_Async_I2C/script/` | `.py` / `.sh` 82 本 + `SCRIPTS.md` / `design_notes.md` / `README.md` / `logic_cells_mapping.md`。**全ての原本**（v9 / v10 世代） |
| `sclk_spi/` | `TR-1um_SCLK_SPI/scripts/` | `i2c_ref/` 33 本（無改変コピー）+ `port_i2c_scripts.py` / `port_rules.py` / `PORTING.md` / `SCRIPTS.md` |
| `i2c_2026/` | `TR-1um_I2C_2026/scripts/pnr/from_async_i2c/` | 9 本 |

生成された中間 JSON（Async_I2C の `net_shapes_nrow_fm_v8*.json` など 129 本）は入れていない。

## 移植方式について

SCLK_SPI までは「**原本 + 置換ルール**」方式だった:

```
i2c_ref/（無改変 23 本） + port_i2c_scripts.py（パス・名前の置換）
                         + port_rules.py（コード片の丸ごと差し替え）
```

「原本を書き換えない＝移植の監査証跡を切らない」という安全策としては正しかったが、
実態としては既に 5 点のロジック変更が入り、`gen_lvs_spice_v9/v10.py` は置換を諦めて
書き直されていた。APRtools ではこの方式をやめ、**引数化されたライブラリ本体 +
設計ごとの設定ファイル**に昇格させる（`docs/90_improvement_notes.md` §2-1）。

後方互換は確認済み: **`n_rows == 4` / `protect_y` 空 で原本と完全同一挙動**になる。

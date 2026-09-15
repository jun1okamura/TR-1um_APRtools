# `pending-upstream/` — 上流にまだ入っていない PDK データ

**ここに置くのは「PDK に PR を出したが、まだマージされていないもの」だけ。**
マージされてタグが切られたら**ファイルを消す**。それだけで
`apr/config_base.pdk_frame_gds()` が自動的に PDK 側を見に行く。

`pdk/` にデータを置かないという原則（`../README.md`）の**唯一の例外**で、
理由は「上流に存在しないので参照できない」。

## いま置いてあるもの

| ファイル | 内容 | 上流 |
|---|---|---|
| `TR-1um_frame_25x25_GIO.gds` | `OSS_DRV` を TD4 / I2C_2026 がテープアウトした版に差し替えたフレーム | **PR 準備済み**（下記） |

正規化 md5 `08fd3bd6b1a3` / 189,282 B / 29 セル。
`OSS_FRAME_GIO` を含む GIO パッド版。

### PR の状態

| | |
|---|---|
| リポジトリ | `OpenSUSI/TR-1um` |
| ベース | `dev`（`6afbd91`） |
| ブランチ | **`fix/oss-drv-gio-frame`**（ローカルにコミット済み `4932b5e`） |
| 対象 | `libs.tech/klayout/libraries/TR-1um_frame_25x25_GIO.gds` |
| 本文 | [`../PR-TR-1um-OSS_DRV.md`](../PR-TR-1um-OSS_DRV.md) |
| push | **未**（この環境に SSH 鍵が無いため設計機から） |

```sh
cd ~/Dropbox/91_OpenPDK/TR-1um
git push -u origin fix/oss-drv-gio-frame
# -> https://github.com/OpenSUSI/TR-1um/compare/dev...fix/oss-drv-gio-frame?expand=1
```

## マージされたら

1. PDK を `git pull`（該当タグが切られていれば `info.yaml` の `pdk.ref` をそれに固定）
2. **このディレクトリのファイルを消す**
3. `apr/selfcheck.py` を回して `pdk_frame_gds()` が PDK を指すことを確認
4. `docs/07_frame_issue.md` と `docs/90_improvement_notes.md`（U19 / U22）を解決済みに

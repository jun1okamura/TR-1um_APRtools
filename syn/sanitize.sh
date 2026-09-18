# ログの仮名化。**`syn.sh` と `sta.sh` の両方が読む 1 本**（U94: 写しを置かない）。
#
#   . "$APRTOOLS/syn/sanitize.sh"      # ROOTDIR と APRROOT を先に決めてから
#   sanitize_file <ファイル>
#
# 生成ログに**その機械の置き方を焼き付けない**（U35 / `config_base.disp()` と同じ規約）:
#   設計の下       -> 相対パス
#   APRtools の下  -> $APRTOOLS/...
#   それ以外のホーム配下 -> $HOME/...
# 端末に出す間は絶対パスのまま（人がそのまま開ける）。**落とし切ってから**書き換える。
#
# ★ **黙って失敗させない**（2026-09-18）。以前は
#   `sed ... > $t && cat $t > $1` だけで、`sed` が落ちると `&&` で止まり
#   **元のファイルがそのまま残る**。ログに不正な UTF-8 が 1 バイト混ざった
#   だけで macOS の `sed` がバイナリとみなして拒否し、**ホームパスが 11 箇所
#   焼き付いたまま**のログが出来た（U93 の防壁がまるごと無効になった）。
#   -> `LC_ALL=C` でバイト列として扱い、落ちたら声を上げ、最後に**数える**。
sanitize_file() {
  [ -f "$1" ] || return 0
  t=${TMPDIR:-/tmp}/tr1um_san.$$
  if LC_ALL=C sed -e "s#${ROOTDIR:-/dev/null/none}/##g" -e "s#${ROOTDIR:-/dev/null/none}#.#g" \
      -e "s#${APRROOT:-/dev/null/none}#\$APRTOOLS#g" -e "s#$HOME/#\$HOME/#g" \
      "$1" > "$t" 2>/dev/null; then
    cat "$t" > "$1"
  else
    echo "** $1 の仮名化に失敗した（ホームパスが残る）。不正なバイトが混ざっていないか見ること" >&2
  fi
  rm -f "$t"
  # 残っていないことを**数えて**確かめる（U93。「0 件」と書くなら数える）
  n=$(LC_ALL=C grep -c -e "$HOME/" "$1" 2>/dev/null || true)
  [ "${n:-0}" -eq 0 ] || echo "** $1 にホームパスが $n 行残っている（U93）" >&2
}

# Codex Cloud の Harmony A 検証と限定取得の実測

確認日：2026-10-26。私有結果から状態・件数・時間のみを要約し、ゲーム資材、MOD 実体、認証情報、生ログ、私有パスは含めない。

## 既存ホストによる A 検証（5ff1a52）

| 項目 | 実測 |
|---|---|
| 対象 | Harmony、Workshop ID `2009463077`、PackageId `brrainz.harmony` |
| 入力取得 | R2 の対象 MOD prefix の16ファイル、8,306,239 bytes。旧 CLI の全 scope で取得したもので、更新版の限定取得の実績ではない |
| ゲーム資材 | 既存の2,672ファイルのスナップショットを全 SHA-256 照合して再利用。ゲームの追加ダウンロードなし |
| 構成 | Linux x64、RimWorld `1.7.4985 rev1269`、同梱 `.NET 10.0.13-waylithclr.dev`、Core、English |
| 要求 | A のみ。対象を外した baseline と対象入りを実行。baseline キャッシュ不使用 |
| 判定 | `passed / completed / qualified`、理由コードなし |
| A の観測 | engineInit、globalInit、staticConstructorsEarly、loadPlayData、lateLoadActions 完了 |
| ロード順 | Core → Harmony、要求と実際が一致 |
| 診断 | 対象で増えた error/warning 0件、翻訳エラー0件、翻訳診断の欠落なし |
| プロセス | baseline・target とも終了コード0、停止理由なし |
| 時間 | baseline 6.442秒、target 6.257秒、全体12.847秒 |

明示的な Def 等の期待値は0件。これは実ローダーと公式の Def 検査・差分診断による A の結果で、任意の MOD 機能の assertion が通ったという意味ではない。B/C/D、マップ、ほかの言語・DLC・OS、Harmony パッチの効果、長時間プレイは未検証。

当時の `_safe_private` は sandbox の保護用 `.git` を checkout と誤認した。通常のファイルシステムで checkout 外を確認して実行した。現在のブランチでは `34fc533` 以降にこの判定の修正がある。

## 更新版の限定取得経路（59dde4d）

非公開索引 → メタデータ照合 → 1.7 向け必要ファイル → 既存ホスト、という更新後の経路を確認した。

- Python 3.12.14、`compileall` 成功。
- `python3 -m unittest discover -s tests -v`：144件中143件成功、Windows 専用 GUI の1件スキップ。sandbox 内で終了コード0。
- `fetch-mods --target Harmony --language English`：既定の索引 GET で `blocked`、CLI 終了コード2。
- 切り分けの認証付き HEAD：`Game-Linux/Version.txt` は成功、18 bytes。`PrivateIndex/rimworld-mod-index-2026-10-26.zip` は 404。
- 利用可能な私有領域にローカル索引 ZIP は見つからなかった。索引の照合、MOD の列挙・取得、ゲーム資材の取得、新たな Worker 実行は行っていない。

これは入力前提による `blocked` で、MOD の `failed` や Worker 実行後の `incomplete` ではない。対象索引を使った限定取得と実ゲーム処理の結合成功は未確認。上記の旧コミットでの A 成功とは区別する。

## 再開条件

正規の非公開索引 ZIP を既定の R2 キーへ配置するか、私有領域の ZIP を `--index-zip` に渡す。`AGENTS.md` に従い、索引を取得せず対象 ID を推測・代用しない。索引が利用可能になった後に既定の限定 scope で再実行し、必要な取得量と検証結果を記録する。

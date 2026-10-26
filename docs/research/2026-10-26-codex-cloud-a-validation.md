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

## 配置違いの解消と限定取得による A 検証

後続調査で `rimworld-mod-index` prefix の列挙により、R2 直下の `rimworld-mod-index.zip`（186,980 bytes）を発見し、その1オブジェクトを取得した。`PrivateIndex/` は空。バケット直下の delimiter 付き列挙は1ページのみで打ち切り、バケット全体や `Workshop/` 全体の再帰走査は行っていない。

索引279件から Harmony の名前・Workshop ID・PackageId を照合後、`59dde4d` の `fetch-mods` に取得済み ZIP を `--index-zip` で渡した。About を先に照合し、既定の `validation` scope で6ファイル・2,550,006 bytesを取得、10ファイルを除外。旧取得の8,306,239 bytesから約69%削減した。この比率は今回の Harmony のみの実測。

既存スナップショットを全 SHA-256 照合して再利用し、ゲームの GET は0件。`prepare` は `snapshotReused`。`validate` で Core / English / A の baseline と対象を新規実行し、以下を確認した。

| 項目 | 実測 |
|---|---|
| 判定 | `passed / completed / qualified` |
| 時間 | baseline 5.650秒、target 5.842秒、全体11.626秒 |
| ロード順 | Core → Harmony、要求と実際が一致 |
| 新規診断 | error/warning 0件、翻訳エラー0件 |
| スコープ | A の実ローダー・公式 Def 検査・差分診断。明示的な期待値0件。B/C/D・マップは未要求 |

ゲーム・OS・CLR は先の実行と同じ。索引を確認したと偽ったり、404 を無視して対象 ID を代用したりせず、実際の R2 索引で照合してから取得した。

## 既定キーの修正と検証

`r2_assets.PRIVATE_INDEX_KEY` を `rimworld-mod-index.zip` に変更し、`codex_workflow` は同じ定数を使用する。旧キーは明示指定の場合だけ引き続き許可し、任意のルート ZIP や prefix を許可しない。

合成 ZIP と AWS CLI 境界の偽応答を使った回帰テストを追加し、旧キーを送ることで失敗することを先に確認。修正後は取得・読み込み・Harmony 解決まで通過した。修正済みの既定キーによる索引 GET と279件の読み込みも実R2で確認した。限定取得と A 検証はこの既定キー変更前に `--index-zip` を明示して実施しており、確認経路を区別する。

修正後の Python 全テストは145件中144件成功、Windows専用1件スキップ。`compileall` 成功。R2 の書き込み・削除、ゲーム起動、第三者 MOD の公開、PR のマージは行っていない。

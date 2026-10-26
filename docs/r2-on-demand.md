# Cloudflare R2 のオンデマンド取得（ChatGPT / GitHub / Linux）

**既存の検証専用 Controller/Worker を変更せず**、入力資材のみを R2 から取得する。R2 接続は実ゲーム検証の合否を変えない。公式ゲーム実行ファイルは起動しない。

## 既存の R2 配置

| prefix | 内容 |
|---|---|
| `Game-Linux/` | Linux 版 RimWorld 1.7 のゲーム・CLR・Data |
| `Workshop/<数字ID>/` | Steam Workshop の MOD |
| バケット直下 | 誤ってアップロードされた Windows 版（このツールの取得対象外） |

既定バケット名は `rimworld-17`。2026-10-26 に Codex Cloud から `Game-Linux/Version.txt` の HEAD/GET が成功したとユーザーが報告。新しい統合CLIでの実MOD検証は未実施。正確なキーは読取権限のある環境で確認する。

## 認証

Cloudflare で **対象バケットのみ Object Read only** のトークンを作成し、Linux 環境に AWS CLI v2 と Python 3.12+ をインストールする。環境変数の形式：

```bash
export AWS_ACCESS_KEY_ID='(read-only ID)'
export AWS_SECRET_ACCESS_KEY='(read-only secret)'
export AWS_DEFAULT_REGION=auto
export R2_ENDPOINT='https://ACCOUNT_ID.r2.cloudflarestorage.com'
export R2_BUCKET='rimworld-17'
```

上の値は例示。**本物のキーを ChatGPT、Issue、PR、ログ、公開リポジトリに貼らない。** シェル履歴にも秘密を残さない方法で入力する。Claude Code Web の設定は GitHub Actions へ自動転送されない。

GitHub Actions で使う場合、`Settings → Secrets and variables → Actions` に以下を登録する。

- **Secrets**：`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`
- **Variables**：`R2_ENDPOINT`（上記形式の HTTPS S3 endpoint）
- バケット名：`rimworld-17`（workflow / CLI の既定値）

## 必要なファイルだけを取得

```bash
# 正確なオブジェクトキーだけ。List API は使わない。
python3 tools/r2_assets.py file \
  --key 'Game-Linux/Assembly-CSharp.dll' --dest /private/refs

# 対象 MOD の About 以下の XML/TXT だけ（対象数・容量を先に確認）
python3 tools/r2_assets.py mod \
  --workshop-id 1234567890 --scope about \
  --dest /private/mods/1234567890 --dry-run

# 対象 MOD の XML のみ（複数バージョンも同じ ID の範囲内で選択）
python3 tools/r2_assets.py mod \
  --workshop-id 1234567890 --scope xml \
  --dest /private/mods/1234567890

# DLL も必要になったら指定 MOD 一式
python3 tools/r2_assets.py mod \
  --workshop-id 1234567890 --scope all \
  --dest /private/mods/1234567890

# 実ゲーム処理の検証に限りゲーム一式
python3 tools/r2_assets.py game \
  --scope all --dest /private/rimworld-linux
```

**Workshop ID は例示値**。実際の MOD 名・ID は索引や About.xml などで特定し、推測しない。MOD 索引の生成／MOD名からの解決は今回の実装には含まれない。

`file` は取得先に `Game-Linux/...` または `Workshop/<ID>/...` の相対パスを保つ。`mod` / `game` は指定 prefix 内を List した上でフィルターし、該当ファイルだけを GET する。既定の `mod` scope は `about`、`game` scope は `xml`。**`--scope all` は明示する。**

1 回に 5,000 ファイルまたは 3 GiB を超える列挙取得は拒否する。同じサイズのファイルはローカルキャッシュから再利用するが、**同サイズ更新は見逃し得る**ため、更新済みファイルを確実に読み直すには `--refresh` を指定する。

`--dry-run` の `mod` / `game` は指定 prefix の List API のみ実行する（無料操作ではない）。`file --dry-run` はキーの存在確認すらしない。いずれも接続成功・ファイルの存在確認を意味しない。

## 検証専用ホストに接続

実物の A/B 検証が必要な場合のみ、取得した Linux 一式を用いて従来どおりスナップショットを準備する。ビルドのハッシュと WaylithClr/Adapter の適格性は従来の仕様で判定する。

```bash
dotnet build worker/RimWorldValidation.Worker -c Release -o worker/bin
python3 tools/validation_host.py prepare-game \
  --source /private/rimworld-linux --snapshot /private/rw-snapshot
python3 tools/validation_host.py run \
  --snapshot /private/rw-snapshot --request /private/request.json \
  --out /private/results/run-001
```

依存 MOD や Harmony は **個々の Workshop ID を調べて**必要なものだけ `mod --scope all` で取得する。B の検証には XML だけでなく DLL 等が必要。ゲームのビルドが変化すると適格化が失効しうる。詳細は [検証ホストの使い方](validation-host.md)。

## ChatGPT プロジェクト / GitHub Actions

`.github/workflows/r2-on-demand.yml` は **手動の `workflow_dispatch`**。GitHub の Actions → R2 on-demand asset lookup → Run workflow から `file` または `mod` を指定する。既定は `dry_run=true`。取得したファイルは GitHub ランナーの一時私有領域にのみ置かれ、Artifacts、ログ、コミット、公開リポジトリに保存されない。ログには件数・容量だけ出す。

**このワークフロー自体は MOD ビルドや検証ホストの実行をしない。** その操作が必要なら、別途権限を管理した Linux 環境で取得済み資材を使う。公開の PR 検証ジョブにはゲーム本体や第三者 MOD を持ち込まない。

ChatGPT の GitHub 連携からコードの調査・修正・PRは可能だが、この会話の GitHub ツールには任意の Actions workflow_dispatch を直接起動する操作がない。GitHub Actions を UI から実行するか、起動に対応する Codex/Work 等から使う。**Actions で取得した私有バイナリが ChatGPT の会話コンテキストへ自動投入されるわけではない。**

R2の利用量とトークン消費を抑えるため、ゲーム本体・Workshop全件の再取得は常用しない。

## Codex Cloudとの統合

[Codex用の設定・検証コマンド](codex-cloud.md) を参照。新しい `tools/codex_workflow.py` は非公開索引の検索、対象MODの取得、対応Linuxゲーム資材の準備、既存検証ホストの実行を補助する。`AGENTS.md` はCodex向け共通指示。

プライベート索引ZIPに限り、`PrivateIndex/rimworld-mod-index-2026-10-26.zip` の**正確なオブジェクトキー1件**を読み取れるようにした。公開GitHubには索引の中身を置かない。Codexで継承された存在しない`AWS_PROFILE`はAWS CLIの子プロセスに限って除去する。

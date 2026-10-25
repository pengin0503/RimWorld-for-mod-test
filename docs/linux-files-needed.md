# 追加で必要なファイル

対象は **RimWorld 1.7 ベータ（unstable）の Linux x86_64 版**。Windows 版の実行ファイル・ネイティブ DLL では代用しない。

## 現在の不足

- `Rim_Data.zip` は今回の作業環境へ転送されなかった。まず再添付してほしい。内容は未確認なので、名前だけから必要な Data が揃っているとは判断していない。
- 現在利用できる二つの ZIP に、Linux 起動用の一式、公式 `Data/`、`Rendering/Shaders/`、`Assets.zip` は確認できていない。
- `RimWorld by Ludeon Studios.zip` は設定・セーブのフォルダだった。これは再送不要。

## 送ってほしいもの

ゲームを更新している途中でコピーせず、**同じ時点のインストールフォルダ**からまとめる。

| 場所 | 必要な内容 | 理由 |
|---|---|---|
| インストール直下 | `RimWorld` など拡張子なしの Linux 実行ファイル、`RimWorld.dll`、`RimWorld.runtimeconfig.json`、`RimWorld.deps.json`、同じ場所にある DLL・SO・付属ランタイム一式 | 元の apphost と WaylithClr を使うため |
| ランタイム・ネイティブ用サブフォルダ | 存在すればフォルダ構造を保って同梱 | ルートの `.so` だけを抜き出すと依存先を失う可能性があるため |
| `Rendering/` | `Shaders/` を含む全体 | キャッシュではなく元のシェーダーが必要 |
| `RimWorld_Data/` | 存在する場合は全体 | インストール構造を保つため |
| `Data/` | Core と所有する Royalty・Ideology・Biotech・Odyssey。Defs・Patches・Languages・About 以外も含む全体 | 本物の XML、言語、アセット読み込みのため |
| アセットパック | インストール直下の `Assets.zip` と、所有 DLC 側に存在するアセットパック | 欠損を MOD エラーと誤判定しないため |
| 付属ファイル | `steam_appid.txt`、存在すればバージョン情報・マニフェスト | 起動条件とビルドの識別のため |

`libcoreclr.so`、`libclrjit.so`、`libhostfxr.so`、`libhostpolicy.so`、`libsteam_api.so`、音声用ライブラリなどは確認対象の例。Linux 版の実際の配置はまだ未確認なので、例に載っていないファイルも削らず、直下と関連サブフォルダを保持してほしい。

Linux 版の実行ファイルは ELF 形式である必要がある。`RimWorld.exe` の拡張子だけを消しても Linux 版にはならない。ZIP 化で実行権限が失われた場合は、展開後に正しい実行ファイルへ実行権限を付け直す。

Data とアセットは Windows 版と共通の可能性があるが、今回は未検証。同じゲーム更新時点であることを確認し、混在を見つけた場合は正式判定を出さない。

## 不要なもの

- `Saves/`、`Config/`、`ShaderCache/`、`BundleCache/`、クラッシュダンプ、個人ログ。
- Steam のアカウント情報、ログイン情報、Steam クライアントの個人設定。
- Anomaly。所有していない DLC は有効化しない。
- 最初の Core 起動確認には一般の MOD 群は不要。Harmony と検証対象 MOD は後の段階で用意する。

ファイルを分割する場合は、元の相対パスを保持し、どの ZIP がどの範囲か分かる名前にする。ゲームファイルの置き場所は公開リポジトリの外にする。

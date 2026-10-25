# 追加で必要なファイル

必要な範囲の一覧はこのページに、ファイル受け入れ後の順序と同一ビルドの扱いは [詳細な手順](../notes/linux-files-needed.md) に記載しています。

対象は **RimWorld 1.7 ベータ（unstable）の Linux x86_64 版**。Windows 版の実行ファイル・ネイティブ DLL では代用しない。

## 現在の不足

- 分割 Data の ZIP 3 個は受領・検査済み。Core、Royalty、Ideology、Biotech、Odyssey のデータと DLC アセット 4 個がある。元の `Rim_Data.zip` や確認済み部分の再送は不要。詳細は [追加調査](research/2026-10-25-split-data-audit.md)。
- Linux 起動用の一式と Core 用アセットパックは未受領。分割 Data の GLSL 225 個は `Core/Shaders/` にあり、受領 DLL の起動時参照先 `Rendering/Shaders/` は満たしていない。内容の同等性を確かめずに移動しない。
- `RimWorld by Ludeon Studios.zip` は設定・セーブのフォルダだった。これは再送不要。

## 送ってほしいもの

### 次の小容量の調査用データ

Core の `bake.manifest`、`textures.info` に加え、`Resources/Backstories/`、`Resources/Text/`、`Resources/Fonts/` を含む `Resources.zip` も受領・静的検査済み。13 実ファイルは全件で manifest のハッシュと一致し、Arial の別名を含む 15 論理パス分の内容を確認した。この範囲の再送は不要。詳しい検査と限界は [受領結果](research/2026-10-25-core-small-resources-audit.md) にある。

画像と音声は手元で保管する。Linux の実行ファイル・ランタイムがない段階で、起動用の最小画像・音声集合は確定できないため、今回新たな個別ファイルの追加送付は求めない。完全な Core アセットを受領したことや、起動成功を意味するものではない。

### 基準起動に必要な一式

ゲームを更新している途中でコピーせず、**同じ時点のインストールフォルダ**からまとめる。

| 場所 | 必要な内容 | 理由 |
|---|---|---|
| インストール直下 | `RimWorld` など拡張子なしの Linux 実行ファイル、`RimWorld.dll`、`RimWorld.runtimeconfig.json`、`RimWorld.deps.json`、同じ場所にある DLL・SO・付属ランタイム一式 | 元の apphost と WaylithClr を使うため |
| ランタイム・ネイティブ用サブフォルダ | 存在すればフォルダ構造を保って同梱 | ルートの `.so` だけを抜き出すと依存先を失う可能性があるため |
| `Rendering/` | `Shaders/` を含む全体 | キャッシュではなく元のシェーダーが必要 |
| `RimWorld_Data/` | 存在する場合は全体 | インストール構造を保つため |
| `Data/` | Core と所有する Royalty・Ideology・Biotech・Odyssey は受領済み。Linux 一式と同じ更新時点か照合し、不足や不一致がある場合のみ差し替える | 本物の XML、言語、アセット読み込みのため。完全性は未確定 |
| アセットパック | 未受領の Core 用パック。ルートの `Assets.zip` またはそのビルドでの同等リソースを構造ごと保持する。DLC 側の 4 個は検査済み | Core の欠損を MOD エラーと誤判定しないため |
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

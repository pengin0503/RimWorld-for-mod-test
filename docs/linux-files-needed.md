# 検証用ファイルの現状と必要性の確認方針

最新の [検証専用ホスト設計](superpowers/specs/2026-10-25-test-only-host-design.md) は、公式ゲーム実行ファイルを製品から起動せず、独立ホストから必要な DLL 処理を呼ぶ案です。旧方式の「まず Linux の完全な公式起動一式を必須とする」という一律の前提は、今回の製品設計では採用しません。**対応する Linux の CLR/native 依存も不要になった、という意味ではありません。**

今回は仕様・設計だけを更新し、追加ファイルの一律再送は依頼しません。実装が許可された後、工程別の依存を調べて、実際に不足するものを指定します。[旧基準起動向け一覧](../notes/linux-files-needed.md) は開発用の比較実験の参考資料として残します。

## 受領済みと未確認

| 分類 | 現状 | 扱い |
|---|---|---|
| Windows インストール直下相当 | Rim_Dll_All.zip。managed DLL、Windows apphost/native、runtimeconfig/deps 等を静的確認 | 実行 OS/CLR をまたぐ互換性は未確認。Windows の native DLL は Linux 用として使わない |
| Data 分割 ZIP 3 個 | Core、Royalty、Ideology、Biotech、Odyssey。DLC の Assets.zip 4 個を検査 | 元の大 ZIP や確認済み範囲は再送不要。全インストールとのビルド互換性は未確認 |
| Core 管理情報 | bake.manifest、textures.info | 受領・照合済み。実画像・音声の内容を持つものではない |
| Core の小容量資材 | Resources.zip の Backstories/Text/Fonts。13 実ファイル、別名込み 15 論理パス | 再送不要。詳細は [受領結果](research/2026-10-25-core-small-resources-audit.md) |
| Core アセット全体 | 完全なパックの受領・検査は未完了 | 必要な検査範囲を決めずに「素材なしで全項目合格」としない |
| GLSL | Core/Shaders に 225 個 | DLL の既知参照先 Rendering/Shaders との同等性・配置は未確認。勝手に移動して満たしたことにしない |
| Linux の CLR/native | 未受領・実配置未確認 | stage ごとの必要性を調べ、必須なら不足を blocked とする |
| Harmony | 実行用の対応 MOD は未確認 | B の前提。版/hash/期待 patch を固定する |
| ユーザーデータ ZIP | RimWorld by Ludeon Studios.zip は Config/Saves/cache 等 | ゲーム資材の代替ではない。通常の個人セーブは検証入力に不要 |

Data の詳細は [分割 Data の調査](research/2026-10-25-split-data-audit.md)、管理情報は [Core 管理情報の調査](research/2026-10-25-core-asset-metadata-audit.md) を参照してください。

## 検証範囲ごとの必要性

| 段階 | 必要なもの | 不足時の結果 |
|---|---|---|
| S：現在の静的検査 | 対象の XML/About/ロード設定等。現コードは executable 存在確認も残る | 静的検査の failed/incomplete。実処理は notRun |
| A：実ローダー | 同一対応ビルドの managed DLL、対象 Core/DLC の Data、言語、その呼出しが実際に必要とする資材とランタイム | 実行前は blocked、実行後の欠落は incomplete。素材を fake 成功で代用しない |
| B：DLL/Harmony | A の必要前提、対象 MOD と依存、対応 Harmony、同等性を確認できる CLR/Adapter | B を合格にしない。列挙だけなら期待値不明とする |
| C：指定動作 | test ID と fixture が必要とする資材・native 依存。具体的な集合は成立性調査で固定 | 非対応範囲を明記。OS 固有のものを別 OS で保証しない |
| 開発時の比較実験 | 対応する公式インストールと別環境での比較結果 | 比較できない範囲は未適格のまま。製品が代わりに公式ゲームを起動する方式に変えない |

「headless だから音声ライブラリ不要」「C# DLL だから Windows 版が全て Linux でも動く」は前提にしません。WaylithClr の同等性と独立ホストでの初期化も調査対象です。

追加が必要になった場合は同じ更新時点の正規インストールから相対パスを保って用意し、ビルド識別と hash を照合します。別ビルドを混ぜて不足だけ埋めないでください。画像・音声は必要な範囲が確定するまで手元に保持してください。

## 検証用に不要な個人情報

通常の Saves、個人ログ、クラッシュダンプ、キャッシュ、Steam のアカウント/ログイン情報を追加で求めません。Anomaly と所有していない DLC は対象外です。ゲーム資材・結果原本は公開リポジトリの外へ置きます。

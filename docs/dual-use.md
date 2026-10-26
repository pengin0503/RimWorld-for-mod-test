# AI に任せる検証と Windows での事前検証

**最新の目標は [独立した検証専用ホスト](superpowers/specs/2026-10-25-test-only-host-design.md) です。** iPad から AI に依頼して Linux で検証する用途と、Windows で自分がプレイ前に検証する用途を同じ処理・判定で扱います。ゲームとして遊べる機能は持たせません。

主用途は、ユーザーが PC を操作できなくても、iPad から依頼した AI が Linux 上で検証・MOD 修正・再検証を進め、後で導入して遊ぶための MOD と報告を受け取れることです。Windows PC の起動や遠隔接続、手動のゲーム内確認を通常フローの必須条件にはしません。Windows 版は利用者が自分で検証する追加用途です。

## 現在使える範囲（2026-10-25）

| 機能 | Linux x86_64 | Windows |
|---|---|---|
| 実ゲーム処理による検証（A：実ローダー、B：DLL・Harmony）。[使い方](validation-host.md) | 実装済み。1.7.4985 rev1269＋WaylithClr で `qualified` | 未対応（`run` は `blocked`） |
| 静的な事前検査（`mod_preflight.py check`） | 実装済み | 実装済み |
| C：指定動作テスト | 未実装（`blocked`） | 未実装 |

以下は静的な事前検査の説明です。静的検査はゲームコードを実行せず、DLL は識別用にハッシュするだけです。結果は常に `gameVerification=notRun` で、実ゲーム処理による検証の代わりにはなりません。

| 検査 | 現在の範囲・制約 |
|---|---|
| 有効 MOD | Core の先頭、空欄・重複・欠損・曖昧な取得元を検出。無効 MOD の Defs は検査しない |
| Steam 別名 | `_steam` は通常名で候補が一意のときだけ解決 |
| メタデータ | supportedVersions、依存、競合、forceLoadBefore/After。通常 loadBefore/After は推奨表示。自動修正・並べ替えはしない |
| ロードフォルダ | root/Common/明示版、対応した LoadFolders 条件のみ。未知の代替選択・条件は incomplete |
| XML | 選択 Defs/Patches の構文。実際のパッチ適用・継承・型変換・参照解決は未検証 |
| DLL / Harmony | hash のみ。DLL ロード・MOD 初期化・Harmony は未実施 |
| 翻訳・画像・音声 | 読み込み・デコード・実動作は未確認 |
| 速度 | 経過秒のみ。通常起動との速度比較は未計測 |

## 現在の CLI

```bash
python tools/mod_preflight.py check --profile profiles/ai.local.json --output preflight-results/check.json
```

終了コードは `0=事前検査通過`、`1=問題あり`、`2=検査が不完全`。JSON の diagnostics、auditStatus、coverage で修正・再検査できます。静的検査通過を「ゲームで動いた」と報告しないでください。

プロフィール例は [example.json](../profiles/example.json)。現在の実装の Linux 用例：

```json
{
  "schemaVersion": 1,
  "gameDir": "/private/RimWorld",
  "saveDataDir": "/private/player-profile",
  "modRoots": ["/private/Mods"],
  "gameVersion": "1.7"
}
```

OS 上に実在するパスを指定します。相対パスはプロフィールの親から解決します。`saveDataDir` は `Config/ModsConfig.xml` のあるフォルダの親で、検査だけなら個人セーブは不要です。追加 MOD 検索先は MOD フォルダが直下に並ぶディレクトリを指定します。gameDir の Data/Mods は自動検索です。

公式実行ファイルの存在は必須ではありません（あれば変更検出用にハッシュします）。Windows ファイルを Linux でデータとして読むことと、実行できることは別です。ファイル名を変更して OS 対応を偽装しないでください。

## 現在の Windows 画面

`Start-Windows.cmd` は、ゲームの描画で作った検証用 GUI（W2、`tools/gui_host.py launch`）を開きます。設計は `docs/superpowers/specs/2026-10-26-windows-gui-w2-design.md` を参照してください。以前の Tk 画面（`mod_preflight.py desktop`）は 2026-10-26 に削除し、`desktop` は移行のためのエラーを返すだけです。静的事前検査は `mod_preflight.py check` で引き続き使えます。

画面のゲーム起動ボタンと CLI の `play` は 2026-10-25 に削除しました。`play` は移行のためのエラーを返すだけです。遊ぶときは、ツールとは別に通常どおりゲームを起動してください。

## 保存と既存の制約

プロフィールは `profiles/*.local.json`、結果は `preflight-results/` などゲーム・保存先・MOD の外へ保存します。どちらも Git から除外しています。結果には私有パスが含まれるため、公開用には内容確認か集計が必要です。

出力は字面・実パスを保護し、原本領域やプロフィールへの上書きを拒否します。検査は読み取り専用で、単一ファイル 64 MiB、累積 512 MiB、fingerprint 100,000 ファイル、各検索先 10,000 子項目の上限があります。読出しエラー・symlink/junction 経由の内容は検査不能にします。これらは厳密なプロセスメモリや CPU の制限ではありません。

hash は検査対象の変更検出用であり、全リソースの完全性やゲーム互換性の保証ではありません。現在の上限や schema は静的検査の契約です。将来の動的検証契約へ勝手に流用しません。

## これから作るもの

Windows での Worker 実行と画面からの実ゲーム検証、C の指定動作テストは [製品計画](superpowers/plans/test-only-host-product.md) の残りタスクです。遊べる画面、対話入力、無期限 tick、通常起動は提供しません。

「標準 .NET で実行できた」「Linux で通った」「ロードできた」は、それぞれゲームとの CLR 同等性、Windows 固有挙動、未実行のプレイ中機能を保証しません。

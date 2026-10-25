# AI に任せる検証と Windows での事前検証

**最新の目標は [独立した検証専用ホスト](superpowers/specs/2026-10-25-test-only-host-design.md) です。** iPad から AI に依頼して Linux で検証する用途と、Windows で自分がプレイ前に検証する用途を同じ処理・判定で扱います。ゲームとして遊べる機能は持たせません。今回の更新は文書のみです。

## 現在使える範囲

現在の実装は静的な事前検査です。ゲームコードは実行せず、DLL は識別用にハッシュします。A/B の実ロードや指定動作テストはまだありません。結果は常に `gameVerification=notRun` です。

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

**現コードには公式名の executable が存在することの確認が残っています。** これは静的検査の本質的な必要条件ではなく、新仕様の移行時に外す対象です。Windows ファイルを Linux でデータとして読むことと、実行できることは別です。ファイル名を変更して OS 対応を偽装しないでください。

## 現在の Windows 画面

Python 3.12+ を Tcl/Tk・Python Launcher 付きで用意し、`Start-Windows.cmd` を開きます。ゲーム/保存先/追加 MOD 検索先を設定し、静的事前検査、プロフィール保存、結果保存を使えます。単体 EXE 配布ではありません。

**画面のゲーム起動ボタンと CLI の `play` は、旧設計で作った機能が現コードに残ったものです。新仕様の検証専用機能には含めず、将来削除します。** 今回は実装を変更していないため、既に削除・無効化済みとは扱わないでください。本書では検証用の操作として案内しません。

## 保存と既存の制約

プロフィールは `profiles/*.local.json`、結果は `preflight-results/` などゲーム・保存先・MOD の外へ保存します。どちらも Git から除外しています。結果には私有パスが含まれるため、公開用には内容確認か集計が必要です。

出力は字面・実パスを保護し、原本領域やプロフィールへの上書きを拒否します。検査は読み取り専用で、単一ファイル 64 MiB、累積 512 MiB、fingerprint 100,000 ファイル、各検索先 10,000 子項目の上限があります。読出しエラー・symlink/junction 経由の内容は検査不能にします。これらは厳密なプロセスメモリや CPU の制限ではありません。

hash は検査対象の変更検出用であり、全リソースの完全性やゲーム互換性の保証ではありません。現在の上限や schema は静的検査の契約です。将来の動的検証契約へ勝手に流用しません。

## これから作るもの

独立 Worker が実物 DLL の読み込み・参照解決・初期化・Harmony と指定動作を検証し、終了する構成が主案です。遊べる画面、対話入力、無期限 tick、通常起動は提供しません。Windows で検証した後に遊ぶ際は、利用者がツールとは別にゲームを起動します。

「標準 .NET で実行できた」「Linux で通った」「ロードできた」は、それぞれゲームとの CLR 同等性、Windows 固有挙動、未実行のプレイ中機能を保証しません。対応範囲と成立性を調べる [未実行の計画](superpowers/plans/2026-10-25-test-only-host.md) を先に進める設計です。

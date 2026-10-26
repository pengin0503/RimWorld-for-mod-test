# RimWorld-for-mod-test

RimWorld を通常起動できない環境でも、作成した MOD を実物のゲーム処理で検証するための**検証専用ツール**を目指すプロジェクトです。ゲームとして遊べる機能は提供しません。

- **主用途：iPad → AI → Linux**：ユーザーが PC を操作できなくても、AI が Linux 環境のツールで実物のゲーム処理による検証・MOD 修正・再検証を進め、後でゲームへ導入して遊べる状態を目指す。ユーザーの Windows PC の起動・遠隔接続・手動テストを通常の検証フローの前提にしない。
- **追加用途：Windows で自分で検証**：同じ検証を自分で実行し、問題を直してからゲームは別途通常の方法で起動して遊ぶ。検証の待ち時間短縮を目指す。

## 最新の仕様と現在の状態

**最新の方針は [検証専用ホストの仕様・設計案](docs/superpowers/specs/2026-10-25-test-only-host-design.md) です。** 独立したホストからゲーム DLL の必要な処理を呼ぶ方式で、公式ゲーム実行ファイルは起動しません。2026-10-25 に Linux で成立を確認し、A（実ローダー）と B（DLL・Harmony）を実装しました。**使い方は [実ゲーム処理による MOD 検証](docs/validation-host.md)** です。

| 項目 | 現状 |
|---|---|
| 実ゲーム処理による検証（`tools/validation_host.py` と C# Worker） | **Linux x86_64 で実装済み**。RimWorld 1.7.4985 rev1269＋同梱 WaylithClr で `qualified`。XML パッチ失敗、未解決参照、Mod 初期化例外、期待した Harmony パッチの欠落、パッチの副作用（公式の Def 検査エラー）を実物の処理で検出 |
| 公式 headless との比較（開発用） | 自作 fixture 9 ケースで、エラー・警告と読込結果（Def 値、翻訳、MOD 順序、Harmony 登録）が一致。[適格化の記録](docs/research/test-host-qualification.md) |
| 実際の MOD | Harmony 3.0.1 と Vanilla Expanded Framework で実行。VEF は Core・全 DLC 英語で passed、全 DLC 日本語では公式翻訳の注入先を消すパッチのため翻訳エラーの警告が 3 件増えて failed。公式 headless と同じ結果。2026-10-26 に索引から選んだ Vanilla Psycasts Expanded（VEF 依存、Harmony 登録 86 件）と TD Enhancement Pack（登録 180 件、うち transpiler 27 件）も Core・全 DLC 英語・全 DLC 日本語で passed、公式 headless と一致。[実 MOD 検証](docs/research/real-mod-validation.md) |
| Windows での実ゲーム検証 | 未対応（`run` は `blocked`）。Linux の結果を Windows の保証にしない |
| 標準 .NET での実行 | 実験扱い（常に `incomplete`）。WaylithClr との実害のある差を確認済み |
| マップ生成（`map`） | Linux x86_64 で実装・適格化済み。ロード後に一時的なワールドとマップを 1 枚生成し、模式図の画像・内容・期待値の判定を出す。このビルドのマップ生成は同じ種でも毎回少し違う（公式も同じ）ため、公式 quick test と各 5 回の分布で比較。[マップ生成の適格化](docs/research/map-qualification.md) |
| C：指定動作テスト | 新規 Bill の材料表示候補/許可状態のみ実装（Linux 非描画・experimental、適格化未完了）。[契約](docs/contracts/mod-validation-v1.md#c製造指示の材料候補非描画experimental) |
| D：ゲーム開始後・tick | 未実装 |
| 入力監査 CLI | 実装済み。ZIP・XML 構文・manifest を検査 |
| MOD 事前検査 CLI / Windows 画面 | 実装済み。静的検査のみ（`gameVerification=notRun`） |
| 既存の通常起動機能 | **削除済み**。CLI `play` は移行エラーを返すだけ。画面の起動ボタンも削除 |
| 速度 | 準備込みの実測あり（[性能](docs/research/test-host-performance.md)）。公式の通常（GUI）起動との比較は未計測 |

AI の通常の検証先は Linux、Windows は利用者自身の検証先として維持します。Windows 向け開発や自作テストの CI は別途行いますが、ユーザーの Windows PC への遠隔接続を製品方式には採用しません。成果物は修正した MOD と検証結果です。「遊べる状態」は MOD 側の目標であり、ツール自体を遊べる形にすることではありません。

現在の静的検査は `gameVerification=notRun` を返します。これを MOD の実動作検証成功に読み替えません。Linux で検証できた結果も、Windows 固有の動作保証にはなりません。

## 仕様・使い方・次の計画

- [検証専用ホストの仕様・設計案](docs/superpowers/specs/2026-10-25-test-only-host-design.md)：原意、方式比較、プレイ不可、検証範囲、OS/CLR の同等性、判定、速度測定。
- [実ゲーム処理による MOD 検証の使い方](docs/validation-host.md) と [要求・結果契約](docs/contracts/mod-validation-v1.md)。
- [製品実装計画と実施状況](docs/superpowers/plans/test-only-host-product.md)、[成立性調査の計画](docs/superpowers/plans/2026-10-25-test-only-host.md)。
- 調査：[依存と必要資材](docs/research/test-host-dependencies.md)、[呼出し経路と終了点](docs/research/test-host-entrypoints.md)、[適格化](docs/research/test-host-qualification.md)、[性能](docs/research/test-host-performance.md)。
- [二つの用途と現在使える静的検査](docs/dual-use.md)：現在の実装と将来の仕様を区別。
- [入力監査 CLI](docs/offline-input-audit.md)：Python 3.12+、外部パッケージ不要。
- [資材の現状と必要性の確認方針](docs/linux-files-needed.md)：Linux 一式を待つことと、工程別の不足を調べることを区別。

実装済みの範囲は A：Defs・XML パッチ・選択言語・参照解決・公式の Def 検査、B：DLL 初期化と期待した Harmony 登録です。C：指定動作テストは後段、D：一時世界・限定 tick は別の将来設計です。ロード成功や Harmony 登録だけで、MOD の全機能が正しいとは判定しません。

## 受領資料と調査記録

- [受領ファイルの調査](docs/research/2026-10-25-input-audit.md)と[識別メタデータ](docs/research/input-inventory.json)。
- [分割 Data の追加調査](docs/research/2026-10-25-split-data-audit.md)。Core・Royalty・Ideology・Biotech・Odyssey のデータ、DLC アセット 4 個を確認。元の大 ZIP の再送は不要。
- [Core の管理情報](docs/research/2026-10-25-core-asset-metadata-audit.md)と[小容量リソース](docs/research/2026-10-25-core-small-resources-audit.md)。Core アセット本体を完全に受領した結果ではない。
- [起動・読み込みの静的調査](notes/2026-10-25-source-audit.md)と[調査 JSON](notes/2026-10-25-source-audit.json)。MOD 自動回復、DLC の追加・ソート、遅延初期化、言語、ログ上限等。
- [以前の引き継ぎ](notes/handoff-2026-10-25.md)と[以前の試運転報告](notes/headless-spike-report.md)。今回の成功実績として扱わない。

2026-10-25 に Linux 版一式（WaylithClr、native 依存、Data、Assets.zip、GLSL を含む）を受領し、依存を確認しました（[依存と必要資材](docs/research/test-host-dependencies.md)）。以前の Windows 版とはゲーム DLL がバイト単位で同一です。資材不足を MOD の失敗や検証成功に変換しません。

`RimWorld by Ludeon Studios.zip` は設定・セーブ・キャッシュなどのユーザーデータで、インストール一式の代わりにはなりません。

## ゲームファイルの扱いと旧資料

ゲーム DLL、実行ファイル、ランタイム、Data、アセット、逆コンパイル本文、個人設定・セーブ・生ログは公開しません。正規の利用者が用意したファイルを私有領域で使います。Anomaly は対象外。公開 CI は自作 fixture に限定します。

[旧 headless 設計](docs/superpowers/specs/2026-10-25-headless-validation-design.md)と[旧二用途設計](docs/superpowers/specs/2026-10-25-dual-use-design.md)は経緯の記録です。公式実行ファイルを製品から起動する方針と、通常起動の入口を作る方針は最新仕様で取り消しています。旧資料の判断を新しい要件として復活させないでください。

## Cloudflare R2 からのオンデマンド資材取得

[Cloudflare R2 のオンデマンド取得](docs/r2-on-demand.md) を参照してください。`tools/r2_assets.py` は読み取り専用で、`Game-Linux/` の必要なファイルと `Workshop/<ID>/` の指定 MOD だけを取得します。既存の検証ホストおよび判定契約は変更しません。GitHub Actions の手動ワークフローはプレビュー／限定取得のみを行い、ゲームファイルをログや Artifacts には出力しません。Codex Cloud からの接続は確認済みですが、GitHub Actions 側の Secrets 設定・実接続は別途確認が必要です。

## Codex Cloud での R2 参照・MOD 検証

[Codex Cloud の接続・実行手順](docs/codex-cloud.md) と [Codex 向け作業規約](AGENTS.md) を追加しました。ユーザーの非公開 MOD 索引（ZIP）は公開リポジトリに置かず、Codex の私有領域で Workshop ID の解決に利用します。`tools/codex_workflow.py` は索引検索、指定 MOD の R2 取得、Linux ゲームスナップショットの準備、既存検証ホストの実行を補助します。

2026-10-26 にコミット `5ff1a52` で Harmony の A 検証が `passed / completed / qualified`。その後、R2 直下の `rimworld-mod-index.zip` を取得し、索引照合・1.7 向け限定取得を経た Harmony の A 検証も `passed / completed / qualified`（6ファイル・約2.55 MB、ゲーム再取得なし）。既定の索引キーも実配置へ修正しました。[Codex Cloud の実測記録](docs/research/2026-10-26-codex-cloud-a-validation.md) に成功範囲と残作業を分けて記録しています。

限定取得はゲームの有効ロードフォルダ・条件・版別依存に合わせて計画し、判断できない場合は `blocked` にします。VPE と Harmony・VEF、Core＋Royalty・英語の A 検証で、限定取得と全取得のロード順・実フォルダ・Def 数・診断が一致しました。[限定取得の比較記録](docs/research/2026-10-26-limited-fetch-parity.md)を参照してください。

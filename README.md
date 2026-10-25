# RimWorld-for-mod-test

RimWorld 1.7 ベータの MOD を、Linux 上の AI に検査させる使い方と、Windows の PC で自分がプレイ前に検査する使い方の両方へ対応させるプロジェクトです。

## 現在の状態

**入力監査 CLI、有効 MOD の事前検査 CLI、Windows 用の画面と明示的な通常起動の入口を利用できます。** 公式 headless によるロード検証の本体・観測 MOD・リリースはまだありません。

[二つの使い方と現在の検査範囲](docs/dual-use.md)を参照してください。Windows では `Start-Windows.cmd`、AI は `python tools/mod_preflight.py check --profile ...` を入口にします。両方で同じ検査処理と結果 JSON を使います。

Linux のゲーム一式がなくても、[入力監査 CLI](docs/offline-input-audit.md) で ZIP・XML 構文・manifest を検査できます。Python 3.12 以上、外部パッケージ不要です。`auditStatus=passed` とゲームの検証成功は別で、`gameVerification` は常に `notRun` です。

最初の対象は、次の二つです。

- A：実ゲームの読み込み処理を通した Defs・XML パッチ・選択言語の読み込み検証。
- B：MOD DLL の読み込みと、期待した対象メソッドへの Harmony パッチ登録の検証。

マップ生成、tick、実プレイ中の挙動は初期版の対象外です。パッチの登録確認だけでは、パッチ後の挙動の正しさは証明できません。

## 資料

- [受領ファイルの調査結果](docs/research/2026-10-25-input-audit.md)：今回直接確認した事実、引き継ぎ情報、未確認事項を区別しています。
- [ファイル識別用のメタデータ](docs/research/input-inventory.json)：ZIP の整合性、SHA-256、主要 DLL の識別情報。
- [分割 Data の追加調査](docs/research/2026-10-25-split-data-audit.md)：追加受領した ZIP 3 個、DLC アセット、XML 構文、残る不足。
- [Core アセット管理情報の調査](docs/research/2026-10-25-core-asset-metadata-audit.md)：収録表とテクスチャ管理表の照合、フォントの別名、次の小容量の受領範囲。
- [Core の小容量リソースの受領結果](docs/research/2026-10-25-core-small-resources-audit.md)：Backstories・Text・Fonts を受領し、13 実ファイルのハッシュを照合。
- [追加で必要なファイル](docs/linux-files-needed.md)：ゲーム本体のフォルダとユーザーデータのフォルダの違いも説明しています。
- [設計案](docs/superpowers/specs/2026-10-25-headless-validation-design.md)：ランチャー、検証用 MOD、判定・レポート、実行手順。


追加の IL 調査では、MOD 失敗時の自動回復、`-mod=` による公式 DLC の追加・自動ソート、翻訳と static constructor の遅延処理、DevMode による検査範囲の違いを確認しました。

- [起動・読み込み処理の追加調査](notes/2026-10-25-source-audit.md)と[機械可読の結果](notes/2026-10-25-source-audit.json)。
- [詳細な受け入れ・基準試験の手順](notes/linux-files-needed.md)。
- [以前の引き継ぎ資料](notes/handoff-2026-10-25.md)と[以前の試運転報告](notes/headless-spike-report.md)。今回の実行結果とは区別しています。

## 実起動をまだ検証できない理由

分割された `Rim_data_1.zip`〜`Rim_data_3.zip` は受領できました。Core と Royalty・Ideology・Biotech・Odyssey のデータ、および DLC の `Assets.zip` 4 個を確認し、外側・内側の ZIP の CRC 検査を通過しました。元の `Rim_Data.zip` の再送は不要です。

受領済みの DLL 一式は `win-x64` 向けで、Linux の実行ファイル・同梱ランタイム・ネイティブ依存関係は引き続き不足しています。Core 用アセットパックも未受領です。GLSL 225 個は `Core/Shaders/` にありますが、受領 DLL が参照する `Rendering/Shaders/` への配置・同等性は未確認です。**Data 全体の完全性・同一ビルド互換性・ゲーム起動成功はまだ確認できていません。**

`RimWorld by Ludeon Studios.zip` は設定・セーブ・キャッシュなどのユーザーデータで、ゲームのインストール一式の代わりにはなりません。

## ゲームファイルの扱い

ゲームの DLL、実行ファイル、Data、アセット、逆コンパイルしたゲームソース、個人の設定・セーブ・ログはコミットしません。利用者自身の正規インストールを非公開の作業領域に置く方針です。Anomaly は対象外です。

`.gitignore` は取り込み事故を減らす補助です。公開前に変更ファイルを個別確認し、`git add -f` でゲームファイルを追加しないでください。

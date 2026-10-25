# Offline Input Audit Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution. Track completion below.

**Goal:** Linux のゲーム一式なしで受領ファイルの静的検査を再実行する。

**Architecture:** Python 標準ライブラリの読取専用 CLI。ZIP とメタデータの検査結果はゲーム検証から独立した JSON にする。

**Tech Stack:** Python 3.12+、unittest、zipfile、Expat、GitHub Actions。

**Spec:** [入力監査の設計](../specs/2026-10-25-offline-input-audit-design.md)。ユーザーが実行可能な作業の選定・続行を依頼したため、補助 CLI を自分で実装する。

## Global Constraints

- ゲームの起動・コード実行・抽出・独自ロードをしない。
- 元ファイルを変更せず、ゲームファイル・本文をコミットしない。
- `gameVerification=notRun` を固定。入れ子パック・フォント・画像の動作は未検査。
- Python 3.12+ の標準ライブラリのみ、CI は合成 fixture のみ。

## Review Focus

- CRC 破損と未対応圧縮を区別する。
- Unicode・大小文字の衝突、危険なパス、リンクを見逃さない。
- サイズ・診断上限到達後に合格を返さない。
- 同一内容による別名カバーと実ファイルの改変を区別する。
- CLI エラー・入出力同一パスで入力を壊さない。

### Task 1: ZIP と manifest の静的検査

Files: `tools/audit_inputs.py`、`tests/test_audit_inputs.py`。
Interface: `audit_zip(path, manifest=None, scopes=(), max_entry_bytes=..., max_total_bytes=..., max_entries=...) -> dict`。

- [x] 合成 ZIP で正常 XML、壊れた XML、CRC 破損、危険なパス・リンク・衝突、上限、未対応圧縮、同一内容の別名、改変ファイルを検査する失敗テストを書く。
- [x] `python -m unittest discover -s tests -v` を実行し、未実装による失敗を確認する。
- [x] 入力監査を実装し、テスト全件の通過を確認する。

### Task 2: metadata、CLI と出力

Files: 同上。Interface: `audit_metadata(manifest_path, textures_path) -> dict`、CLI の `zip` / `metadata`。

- [x] メタデータの不正行・重複・集合不一致、CLI 終了コード、JSON、入力上書き拒否の失敗テストを書く。
- [x] 失敗を確認し、実装後に全テストを通す。

### Task 3: 実入力確認・ドキュメント・CI

Files: `docs/offline-input-audit.md`、`README.md`、`.github/workflows/offline-audit.yml`。

- [x] 合成 fixture のみの CI と使用例・検査範囲を追加する。
- [x] 受領済み Resources、Data ZIP、管理情報を読み取り専用で実行し、集計と既知の結果を照合する。
- [x] 差分・入力非変更・公開対象をレビューする。既存 PR へは検証済みツリーをコミット後に反映する。

## Execution ledger

Ruling: Linux 基準起動前でも独立して検証できる入力監査のみを前倒しする。headless ランチャーと観測 MOD は既存設計のレビュー・Linux 実測待ち。入力監査の成功をゲーム検証へ読み替えることが最大の誤用リスクなので JSON と文書で区別する。

Tasks 1–2: complete。初回の未実装失敗、追加 CLI/境界テストの失敗を確認後、25 件を通過。実入力 5 ケースの集計は実行記録へ保存。

Final review: 独立した読取専用レビューを 1 回実施。未知の XML 文字コード、元 ZIP 名の NUL、非正規パス・親ファイル衝突、過小な宣言サイズによる偽の CRC 成功を再現テスト RED→GREEN で修正。最終スイート 30 件が通過。

Ruling: LZMA の例外を追加で捕捉するだけでは、宣言サイズによる切捨てを独立に検出する保証がない。Stored/Deflate を独立に検査し、それ以外は `incomplete` とする。代償は LZMA/Bzip2 等の受領検査が未対応になること。今回の実入力の外側 ZIP は検査できる。

Final: minor (deferred): 「正常な別名の実体がある一方、別名先の物理ファイル自体は改変されている」組合せ専用の追加テスト。コードは物理ファイルが存在して hash が異なる場合に `hashMismatch` とする。既存の改変・別名テストとは別の組合せ拡充として保留。

Final: Ruling: Windows と remote CI はローカルレビューでは未実行なので、Actions の実行結果を別に確認する。ゲーム・実素材デコードは初版の検査対象外で `notRun` を維持する。未観測の環境結果を成功と記載しない。

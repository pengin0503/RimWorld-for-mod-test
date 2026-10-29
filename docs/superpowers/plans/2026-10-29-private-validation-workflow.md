# 私有検証workflow常用化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Implement task-by-task; avoid per-task agent dispatch.

**Goal:** 最新mainからsuiteを選び、準備を重複せず有限検証を再実行できるようにする。
**Architecture:** 固定suite registryと、秘密付き準備/秘密なし実行/再検証済み公開の3境界を作る。PR27の実験helperを再利用する。
**Tech Stack:** Python3.12+、C#/.NET10、GitHub Actions、Linux（必要な部分だけ）。
**Spec:** [共通設計](../specs/2026-10-29-linux-validation-next-design.md)。実装は[PR30](https://github.com/pengin0503/RimWorld-for-mod-test/pull/30)。main統合・手動実物受入は未完了。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用、索引でMODを照合、必要なpayloadのみ。同一jobのsnapshotは1回準備して再利用。
私有資材/生ログ/識別子/秘密情報を公開しない。未適格・中断をpassedにしない。
設計書の共通制約をすべて適用する。実装前に最新main/AGENTS/PR27の状態を再確認する。

## Review Focus

- 不正suite/refのためにR2へ接続しない。
- allでも1snapshot、cow単独ではゲーム取得0。
- 比較不合格・途中結果・古いsummaryを全体成功にしない。
- サマリーを通じた任意識別子や例外本文の漏えいを防ぐ。
- timeout/失敗時にも独立suiteの状態と後片付けを残す。

### Task 1: 固定suiteと安全なsummary

**Files:** create tools/private_validation.py、tests/test_private_validation.py。既存helpersはtests/integration/run_fixture_matrix.py、run_bill_ingredients.py、run_event_choice.py、run_bounded_tick.py、PR27のexperiments/official-comparison/compare_ticks.py、experiments/cow-measurement/measure.py。
**Interfaces:** smokeの固定caseは `ok,harmony-ok,map-ok`。`resolve_suites(name: str) -> tuple[str,...]`、`public_summary(raw: dict) -> dict`。CLIは `python tools/private_validation.py run --suite <enum> --private-root <private-dir> --worker worker/bin` と `publish --private-root <private-dir>`。

- [x] テストを先に書く: `resolve_suites('cow') == ('cow',)`、不正値はValueError、allはsmoke/c-regression/d-regression/d-compare/cowの重複なし。summaryにPRIVATE文字列/任意exception名/NaN/古いrunIdを入れても出力しない。D比較incompleteをqualification=qualifiedにしない。
- [x] `python -m unittest discover -s tests -p test_private_validation.py -v`で未実装の失敗を確認する。
- [x] 上記APIと固定enum・runId/commit SHA結合・数値型/固定コード検証を実装する。公開時にもJSONを読み直して同じvalidatorを通す。
- [x] 同じコマンドが成功し、欠けたsuite/重複/未完了からokを生成しないことを確認してcommitする。

### Task 2: 資材・実行・workflow境界

**Files:** create .github/workflows/linux-private-validation.yml、tests/test_private_validation_execution.py。modify tools/private_validation.py、docs/codex-cloud.md。既存branch専用workflowは移行完了後に廃止する。
**Interfaces:** `run_suites(suites: tuple[str,...], snapshot: Path | None, out: Path, worker: Path) -> dict`。prepareは既存codex_workflow.pyを別stepから使用する。

- [x] 偽R2/合成子プロセスを境界にしたテストを先に作る: cowのprepare回数0、ゲーム複数suiteのprepare回数1、実行環境のAWS/R2資格情報0、失敗後の独立suiteを継続、timeout後の子回収、summaryのcommit不一致拒否。実際の子プロセスの終了とファイルを検査する。
- [x] `python -m unittest discover -s tests -p 'test_private_validation*.py' -v`のREDを確認する。
- [x] workflow_dispatch/main限定/固定choice/default smoke/45分上限を追加する。GitHub inputはenv経由でparserへ渡し、shellのコマンド文字列へ埋め込まない。cow用Btrfsは専用一時imageだけをmountし、always cleanupする。
- [x] Python全suiteと既存Worker合成検査を実行する。秘密なし公開CIでGREENを確認してPR化する。mainへの統合はユーザー指示を待つ。
- [ ] main統合後に手動smoke、cow、c-regression、d-regressionを各1回、allを1回受入する。allのd-compareは現時点で不合格が見込まれるため、実行完了と独立適格化不合格を別記し、qualificationの成功を条件緩和で作らない。

**Stop:** PR27が未統合ならD比較/COW helperの接続を待つ。既存受入helperだけの合成検査は先行可能。secretを使うbranch previewの追加や私有cacheの外部保存へ黙って切り替えない。
**Expected:** 新しいdefault-branch手動入口から同一commitを再検証でき、cowのネット資材取得0、allのsnapshot準備1、私有情報公開0。

実装・検査の記録: [P2共通入口](../../research/2026-10-29-private-validation-workflow.md)。チェック済みは実装と公開合成検査の範囲。実物受入・C/Dの独立適格化・メモリ強制上限の完了を意味しない。

# 実用MOD回帰と性能測定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Implement task-by-task; avoid per-task agent dispatch.

**Goal:** 代表構成で、検出結果を保ったcache/COWの全体時間・メモリ効果を測る。
**Architecture:** 既存の限定取得とrun_validationを再利用し、入力解決/測定/公開を分ける。第三者MOD選定は実行時の非公開索引照合をゲートにする。
**Tech Stack:** Python3.12+、C#/.NET10、GitHub Actions、Linux（必要な部分だけ）。
**Spec:** [共通設計](../specs/2026-10-29-linux-validation-next-design.md)。本計画の機能は未実装。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用、索引でMODを照合、必要なpayloadのみ。同一jobのsnapshotは1回準備して再利用。
私有資材/生ログ/識別子/秘密情報を公開しない。未適格・中断をpassedにしない。
設計書の共通制約をすべて適用する。実装前に最新main/AGENTS/PR27の状態を再確認する。

## Review Focus

- rootの併用指定とloadAfter等の任意連携先を混同しない。
- 索引不明・予算超過時にゲーム/payloadを先に取得しない。
- cacheの速い失敗や未完了を成功標本へ混ぜない。
- warm cacheと初回取得を混ぜて高速化率を出さない。
- 名前/索引/私有パス/診断本文をpublic出力へ流さない。

### Task 1: profileの解決と取得予算

**Files:** create tests/integration/run_workload_regression.py、tests/test_workload_regression.py。modify tools/codex_workflow.py。reuse mod_load_plan.py、run_linux_regression.py。
**Interfaces:** `resolve_profile(name: str, index: dict, metadata_reader) -> dict`。CLIは `run_workload_regression.py prepare|run|publish --profile S|M --private-root R --worker W`。S/Mの候補名・予算は設計書P4の値。
既存 `fetch_mods(args)` は互換なkeyword-only上限 `max_selected_bytes=None, max_selected_files=None, max_mods=None` を追加し、metadata解決後・payload前に適用する。未指定時は従来の取得動作を維持する。

- [ ] RED: 曖昧ID/重複PackageId/循環/不明必須依存は停止、任意連携先は取得しない、SにTDを自動追加しない。Mの2rootの必要閉包だけを得る。選択ファイル合計256 MiB、5000 files、20 MODの境界と超過を検査する。
- [ ] `python -m unittest discover -s tests -p test_workload_regression.py -v`の失敗を確認する。
- [ ] 既存resolve_mod_graph/fetch_modsを利用する。Mでは明示root集合をprivate requestのtarget集合へ反映する。既存の「単一targetを返すfetch_mods」の結果をそのまま複数targetと呼ばない。
- [ ] メタデータ解決後・payload前に予算（cachedを含む選択ファイル合計で保守的に判定）を検査する。request/planを私有ファイルへ保存し、取得量とhashを記録。既存取得APIの上限引数について、未指定互換・cachedも含む選択サイズ・超過時payload GETゼロを検査する。
- [ ] GREENと、偽transportで不要prefixへの接続0を確認してcommitする。計画段階の候補名を照合済みMODとして報告しない。

### Task 2: 正しさを条件にした測定

**Files:** modify tests/integration/run_workload_regression.py、tests/test_workload_regression.py、P2 registry（workload追加）。create docs/research/real-mod-workload-measurement.md（実測後）。
**Interfaces:** `measure_profile(request: dict, snapshot: Path, out: Path, worker: Path) -> dict`、`public_summary(raw: dict) -> dict`。各runはcache mode/copy mode/秒/RSS/取得件数/cache利用/検証状態を別々に持つ。

- [ ] RED: failed/incomplete標本を中央値へ入れない、5成功未満なら測定incomplete。cache作成1回を再利用5回の中央値に混ぜない。不正数値/任意文字列/古い入力hashを公開しない。
- [ ] 同じunitコマンドの失敗を確認してから、無効5回・作成1回・再利用5回、copy/reflink比較各5回を実装する。対照の強制copyは実験内だけで製品のSHA256照合経路を共有する。
- [ ] Sから実施し、順序/実load folder/新規診断/Def期待値が全成功した場合にMへ進む。Bは明示期待patchのある既存fixtureで別途回帰する。
- [ ] 同一snapshotと入力を再利用し、英語/Core+RoyaltyのAから始める。mapを加える場合は別表とし、C/Dは混ぜない。初回ネット/準備を全体時間へ含める表と、検証だけの表を分ける。
- [ ] Btrfsのある環境でのみ実MODのCOWを測る。非対応ならfallback件数を記録し、そのprofileのCOW高速化は未計測とする。
- [ ] 合成テスト・公開CIとS/Mの実物結果を記録し、固定profile IDと数値だけ公開してPR化する。私有の正確な構成は再現に使うが公開しない。

**Expected:** 成功した検証に限った時間/メモリと効果の上限が分かる。S/Mが未成立なら結果をincompleteとして残し、大量MOD全体へ外挿しない。

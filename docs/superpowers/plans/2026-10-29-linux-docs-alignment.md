# Linux文書整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Implement task-by-task; avoid per-task agent dispatch.

**Goal:** 現行のLinux実装・資格・未統合状態を矛盾なく案内する。
**Architecture:** 既存の入口文書だけを更新し、過去の研究記録は当時の結果として残す。
**Tech Stack:** Python3.12+、C#/.NET10、GitHub Actions、Linux（必要な部分だけ）。
**Spec:** [共通設計](../specs/2026-10-29-linux-validation-next-design.md)。本計画の機能は未実装。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用、索引でMODを照合、必要なpayloadのみ。同一jobのsnapshotは1回準備して再利用。
私有資材/生ログ/識別子/秘密情報を公開しない。未適格・中断をpassedにしない。
設計書の共通制約をすべて適用する。実装前に最新main/AGENTS/PR27の状態を再確認する。

## Review Focus

- D実装済みをD適格化済みと書かない。
- 自作イベントケースを任意クエスト対応と書かない。
- PR27の実測とmainへの統合状態を混同しない。
- 39.8%と42%の条件を保持する。
- 凍結中のWindows作業を再開する表現にしない。

### Task 1: 入口文書を現行状態へ揃える

**Files:** README.md、docs/roadmap/finished-product.md、docs/dual-use.md、docs/validation-host.md。
**Interfaces:** consumes=mainのAGENTS/契約/実装・PR26/27の状態。produces=実装/資格/根拠/未完了が分かるLinux状態表。

- [ ] GitHubのmain SHA・PR27状態と、ControllerのADAPTERS/evaluate_*を読み、状態表を作る。
- [ ] Cを材料候補と自作eventの2ケースに分ける。Dを有限tick実装済み・独立適格化未完了とする。任意クエスト/描画/長期プレイは未対応と明記する。
- [ ] COWの実測完了とPR27未統合を別記する。PR27が先にマージ済みなら実際のmerge SHAへ根拠を更新する。
- [ ] 各「実装済み」「適格化済み」の根拠リンクとコードを手動照合し、相対リンクを存在確認する。過去文書のチェック欄だけで状態を決めない。
- [ ] `git diff --check`を実行し、意図したLinux文書差分のみでcommitする。文章の変更を検知するためだけのテストや私有ゲーム実行は追加しない。

**Expected:** D未着手/イベント全面未実装という古い現行説明がなく、C/D未適格とPR27の状態が正しい。Windowsコード差分0、私有資材取得0。

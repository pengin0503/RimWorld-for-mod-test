# Linux cgroupメモリ上限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Implement task-by-task; avoid per-task agent dispatch.

**Goal:** 委譲環境でWorkerと子孫全体のメモリ制限・停止・証拠保存を検証する。
**Architecture:** 環境成立性→低レベルlauncher/leaf→既存supervisor統合の順。環境がなければsoft監督を維持し、hard対応の完了とはしない。
**Tech Stack:** Python3.12+、C#/.NET10、GitHub Actions、Linux（必要な部分だけ）。
**Spec:** [共通設計](../specs/2026-10-29-linux-validation-next-design.md)。本計画の機能は未実装。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用、索引でMODを照合、必要なpayloadのみ。同一jobのsnapshotは1回準備して再利用。
私有資材/生ログ/識別子/秘密情報を公開しない。未適格・中断をpassedにしない。
設計書の共通制約をすべて適用する。実装前に最新main/AGENTS/PR27の状態を再確認する。

## Review Focus

- ro/非委譲/偽ディレクトリをhard対応と誤認しない。
- 起動と所属のraceでWorkerを未制限実行しない。
- setsid/forkした子孫を残さず、ControllerをOOM対象にしない。
- 正常exit直前のOOMや途中証拠を成功扱いしない。
- 制御対象外のcgroup/設定/利用者プロセスを変更しない。

### Task 1: G0 環境成立性ゲート

**Files:** create tools/linux_memory.py、tests/test_linux_memory.py、docs/research/linux-cgroup-readiness.md。
**Interfaces:** `probe_delegation(root: Path | None) -> dict`（read-only、available/reason/必要機能だけ）。CLI `python tools/linux_memory.py probe --root <explicit-delegated-path>`。

- [ ] RED: rootなし/read-only/通常ディレクトリ/symlink/namespace root/非委譲/必要controller欠落ではavailable=false。synthetic filesystemテストを実cgroup成立の証拠にしない。
- [ ] `python -m unittest discover -s tests -p test_linux_memory.py -v`の失敗を確認する。
- [ ] cgroup2 mountと委譲root・必要interface/権限をread-onlyで検査する。自動sudo/remount/上位subtree変更は実装しない。ここで実操作の成功を保証せず、Task2の実物検証を別に必要とする。
- [ ] 実装環境をprobeし記録する。現在のro環境なら受入をblockedとして止め、明示的に用意された委譲先が得られるまでTask2以降の実運用・完了主張をしない。

### Task 2: 起動前の制限とleafの生命周期

**Files:** modify tools/linux_memory.py、tests/test_linux_memory.py。create tools/linux_memory_launcher.py、tests/integration/run_linux_memory.py。
**Interfaces:** `create_leaf(root: Path, memory_bytes: int) -> MemoryLeaf`、`MemoryLeaf.start(command, cwd, env, stdout, stderr, pass_fds=())`、`MemoryLeaf.stats() -> dict`、`MemoryLeaf.kill()`、`MemoryLeaf.close()`。

- [ ] RED: 設定読戻し失敗でhard=false、root外/symlink変更拒否、同名leaf衝突、gate未許可時のWorker副作用0、失敗時launcher回収、自分以外のleafを削除しない。親processを移動しない。
- [ ] unit失敗を確認してからmemory.max/memory.swap.max/memory.oom.groupを設定するrun固有leafとlauncher gateを実装する。exec許可前に所属を確認する。`preexec_fn`で複雑な設定を行わない。
- [ ] 委譲環境で低レベル64 MiB/10秒の合成プロセスを使い、正常、mmap大量割当、fork子の割当、setsid子、親の早期exit、timeoutを試す。OOM counterの増加・Controller生存・populated=0・空leaf削除を確認する。
- [ ] kernelの一時超過やpage cacheを認め、厳密なpeak<=要求値だけを合否に使わない。単なるexit137をOOMの証拠にしない。実物未実行ならunitだけでhard対応完了としない。

### Task 3: supervisorと判定への統合

**Files:** modify tools/validation_host.py、tools/linux_memory.py、tests/test_validation_host.py、tests/test_linux_memory.py、docs/contracts/mod-validation-v1.md、docs/validation-host.md。modify P2 registry/workflow（memory追加）。
**Interfaces:** Controller専用環境変数 `RWMT_CGROUP_ROOT`、`RWMT_LINUX_MEMORY_MODE=auto|require-hard`。未設定はauto、Workerへこれらの運用設定を渡さない。既存request schemaのmemoryMiBを使用し、Windows経路は変更しない。

- [ ] RED: auto非対応は現行memoryHard=false、require-hard非対応は開始前blocked、不正mode拒否。OOM後に完了resultが残ってもincomplete、Controllerが上限設定に失敗したらhard=trueを出さない。
- [ ] RSS peakとcgroupPeakBytesを別に記録し、memory.eventsからkilledFor=memoryLimitを付ける。既存理由を使えない新規codeが必要なら理由辞書の互換性も同commitで維持する。case判定を緩和しない。
- [ ] Python全suiteと既存プロセス終了回帰を実行する。既存環境依存の失敗は名前を列挙し、今回の変更が原因か切り分ける。
- [ ] 合成受入成功後に同じsnapshotで実Workerの正常A、既存D memory-limitと途中checkpoint/子回収を試す。対応構成のみmemoryHard=true、非対応構成はsoftのままであることを確認してPR化する。

**Expected:** 委譲環境に限った、所属確認済みWorker子孫へのhard memory制限と明確な結果。委譲がなければG0のblocked記録までが成果で、P1〜P4の完了を止めない。

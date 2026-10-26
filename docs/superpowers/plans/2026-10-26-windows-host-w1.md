# Windows W1（実ゲーム実行）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tools/validation_host.py run` を Windows x64 の正規 RimWorld 1.7.4985 rev1269 で動かし、Linux と同じ要求・結果契約で A/B/C/map を判定する（描画なし、適格化前は experimental）。

**Architecture:** OS 依存部分だけを分ける。ゲーム構成の差は `validation_host.py` の platform 表、Windows のファイル操作は `tools/win_fs.py`、プロセス監視は `tools/win_job.py`（どちらも ctypes＋標準ライブラリのみ、Windows 以外では import しない）。判定ロジックは共有のまま。

**Tech Stack:** Python 3.12+（`_winapi.CreateJunction`、junction を辿らない `shutil.rmtree`）、ctypes（kernel32/ntdll）、.NET 10 Worker（`win-x64` apphost）。

**Spec:** `docs/superpowers/specs/2026-10-26-windows-host-design.md`（2026-10-26 ユーザー承認）

## Global Constraints

- 要求・結果の JSON 契約は Linux と同一。新しい値は追加のみ。
- `('windows-x64', 'waylith')` は Adapter の `qualified` に入れない（適格化前は必ず `experimental`）。
- 公開リポジトリと CI にゲームファイルを入れない。CI はゲームなしの偽 Worker で試す。
- シンボリックリンクを Windows で要求しない（管理者権限・開発者モード不要）。
- Windows のメモリ上限は Job Object によるハード上限で `memoryHard=true`。
- 既存の Linux の挙動・指紋（fingerprint）・テストを変えない。

## Review Focus

1. スナップショットと実行ディレクトリが別ドライブ → ハードリンク不可でも、複製へ落として動くこと（`test_cross_volume_falls_back_to_copy`、Task 2）。
2. 実行後の削除で、読み取り専用のスナップショット本体が書き込み可能に変わらないこと（`test_cleanup_keeps_snapshot_read_only`、Task 2）。
3. Worker が子プロセスを残して終了・時間切れ・Ctrl+C → 子も必ず止まること（`test_timeout_kills_descendants` ほか、Task 3）。
4. Linux 用スナップショットを Windows で使う（または逆）→ `platformMismatch` で blocked（Task 1）。
5. メモリ上限で Worker が自分で落ちた場合も `killedFor='memoryLimit'` と記録されること（Task 3）。

---

### Task 1: ゲーム構成の platform 対応

**Files:**
- Modify: `tools/validation_host.py`（`REQUIRED_GAME_FILES`・`IDENTITY_FILES` 周辺、`prepare_game`、`load_snapshot`、`run_validation` の platform 判定）
- Test: `tests/test_validation_host.py`

**Interfaces:**
- Produces: `BUILD_FILES: dict[str, dict]` … `{'linux-x64': {'host': 'RimWorld', 'native': ('libhostfxr.so', 'libcoreclr.so'), 'coreclr': 'libcoreclr.so', 'workerExe': WORKER_NAME}, 'windows-x64': {'host': 'RimWorld.exe', 'native': ('hostfxr.dll', 'coreclr.dll'), 'coreclr': 'coreclr.dll', 'workerExe': WORKER_NAME + '.exe'}}`
- Produces: `detect_build_platform(files: Iterable[str]) -> str | None`、`required_game_files(platform) -> tuple`、`identity_files(platform) -> tuple`（linux は現行の `IDENTITY_FILES` と同一順）。snapshot.json に `buildPlatform` を追加（旧スナップショットは manifest から推定）。

- [ ] Step 1: テスト `test_windows_build_is_recognised`：Windows 構成の偽ゲーム（`RimWorld.exe`・`hostfxr.dll`・`coreclr.dll`、`RimWorld.deps.json` の runtimeTarget `win-x64`）を `prepare_game` → `buildPlatform == 'windows-x64'`、Linux の偽ゲームは `'linux-x64'`、Linux の fingerprint が変更前の計算と一致。両方の native を欠くゲームは `missingGameFiles`。
- [ ] Step 2: テスト `test_snapshot_platform_must_match_the_host`：`run_validation(..., platform='windows-x64')` に Linux スナップショット → `status=blocked`、`reasons[0].code == 'platformMismatch'`（逆も）。`platform` が `osx-arm64` なら従来どおり `platformUnsupported`。
- [ ] Step 3: 失敗を確認 → 実装 → `python -m unittest tests.test_validation_host` 全通過 → commit。

### Task 2: Windows の実行ディレクトリ（`tools/win_fs.py`）

**Files:**
- Create: `tools/win_fs.py`
- Modify: `tools/validation_host.py`（`build_run_dir` のリンク作成、実行ディレクトリ削除）
- Test: `tests/test_win_fs.py`（Windows 以外は skip）、`tests/test_validation_host.py`

**Interfaces:**
- Produces: `link_file(src: Path, dst: Path) -> str`（`'hardlink'` か、`OSError`（別ボリューム等）時 `'copy'`）、`link_dir(src: Path, dst: Path) -> None`（`_winapi.CreateJunction`）、`remove_tree(path: Path) -> None`（junction は辿らず外す。読み取り専用ファイルは `SetFileInformationByHandle(FileDispositionInfoEx=21, flags=DELETE 0x1|POSIX_SEMANTICS 0x2|IGNORE_READONLY_ATTRIBUTE 0x10)` で属性を変えずに消す）。
- `build_run_dir`：Linux は現行の `os.symlink`。Windows はゲーム直下のファイルを `link_file`、ディレクトリと `Data/<official>` を `link_dir`。結果の `process` に `linkModes`（`{'hardlink': n, 'copy': m, 'junction': k}`）を追加。

- [ ] Step 1: `tests/test_win_fs.py`：`test_hardlink_shares_content`、`test_cross_volume_falls_back_to_copy`（`os.link` を `OSError(EXDEV 相当)` に mock）、`test_junction_is_removed_without_touching_target`、`test_cleanup_keeps_snapshot_read_only`（読み取り専用の元ファイルへのハードリンクを `remove_tree` → 元ファイルが残り、`os.stat(src).st_file_attributes & FILE_ATTRIBUTE_READONLY` のまま）。
- [ ] Step 2: 失敗を確認（Windows CI）→ 実装 → 通過 → commit。

### Task 3: Job Object による監視（`tools/win_job.py`）

**Files:**
- Create: `tools/win_job.py`
- Modify: `tools/validation_host.py`（`supervise`、`worker_command`、`worker_environment`）
- Test: `tests/test_validation_host.py`（`RunTests` の監視系）

**Interfaces:**
- Produces: `class Job` … `Job(memory_limit_bytes: int)`、`.start(command, *, cwd, env, stdout, stderr) -> subprocess.Popen`（`CREATE_SUSPENDED|CREATE_NEW_PROCESS_GROUP` で起動 → `AssignProcessToJobObject` → `ntdll.NtResumeProcess`。割り当て前に子が動かない）、`.poll_messages() -> set[str]`（完了ポートの `JOB_OBJECT_MSG_JOB_MEMORY_LIMIT`=10 → `'memoryLimit'`、`ACTIVE_PROCESS_ZERO`=4 → `'empty'`）、`.peak_memory() -> int`（`PeakJobMemoryUsed`）、`.active_processes() -> int`、`.terminate()`、`.close()`。上限は `JOB_OBJECT_LIMIT_JOB_MEMORY|KILL_ON_JOB_CLOSE`。
- Produces: `worker_command(host: Path, request_path: Path) -> list[str]`（Linux は現行、Windows は `host / 'RimWorldValidationWorker.exe'`）。テストはこれを patch して偽 Worker を `sys.executable` で起動する。
- `supervise` の Windows 分岐：時間・ログ超過と終了時の残存は `Job.terminate()`。`enforcement = {'timeout': 'TerminateJobObject', 'memory': 'Job Object JOB_MEMORY (committed bytes) + DOTNET_GCHeapHardLimit', 'memoryHard': True, ...}`、`peakRssBytes` には `PeakJobMemoryUsed` を入れ、`memoryMeasure: 'jobCommit'`（Linux は `'groupRss'`）を追加。
- `worker_environment` の Windows：`PATH`・`SystemRoot`・`SystemDrive`・`windir` だけ引き継ぎ、`USERPROFILE`・`APPDATA`・`LOCALAPPDATA`・`TEMP`・`TMP` は `run_dir` 内。

- [ ] Step 1: 既存の監視テスト（timeout＋子プロセス、ログ上限、メモリ上限、Ctrl+C）を platform 共通にする。生存確認ヘルパー `pid_alive(pid)` は Linux が `/proc`、Windows が `OpenProcess`＋`WaitForSingleObject(0)`。Windows ではメモリ上限で `memoryHard is True`、Linux では従来どおり False。
- [ ] Step 2: 失敗を確認（Windows CI）→ 実装 → 通過 → commit。

### Task 4: 実行テストを Windows CI で有効化し、文書を更新

**Files:**
- Modify: `tests/test_validation_host.py`（`Fixture(platform=...)`、`RunTests`・`MapTests` の skip 条件を `linux-x64`/`windows-x64` に）
- Modify: `docs/validation-host.md`、`docs/contracts/mod-validation-v1.md`（blocked 条件に Windows を追加、`platformMismatch`、`linkModes`、`memoryMeasure`）、`docs/roadmap/finished-product.md`（現在地）、spec（Worker の在 Job 確認を「停止状態で起動して割り当て」に置換、`mod_load_plan` の大文字小文字は照合で守る旨）

- [ ] Step 1: Windows CI で `RunTests`・`MapTests` が通る（偽 Worker）。Linux の結果は変わらない。
- [ ] Step 2: commit → push → CI 6 ジョブ成功を確認。

### Task 5: ユーザーの PC での実ゲーム確認（ユーザーが手順書どおりに実行。2026-10-26 の指示で Remote Control は使わない）

結果（2026-10-26）：fixture 22/22・C 6/6 が期待どおりで、判定は Linux と同じ。`docs/research/2026-10-26-windows-w1-real-game.md`。公式との比較による適格化は未実施。

- [ ] PC の Python・.NET SDK・Windows 版 RimWorld の場所を確認（なければ導入の可否をユーザーに聞く）。
- [ ] Windows 版の実際のファイル構成（`BUILD_FILES['windows-x64']` の `RimWorld.exe`・`hostfxr.dll`・`coreclr.dll`、deps.json の runtimeTarget、runtimeconfig）を、ユーザーの正規版で確かめる。
- [ ] `prepare-game` → Worker を `-r win-x64` でビルド → fixture 行列・C fixture・小麦粉 MOD を実行し、Linux の結果と比べた表を研究記録に残す。公式 `RimWorld.exe` の headless 比較が使えるかを確かめ、適格化の可否を判断する。

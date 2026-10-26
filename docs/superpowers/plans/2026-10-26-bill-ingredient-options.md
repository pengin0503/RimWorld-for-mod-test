# Bill ingredient options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Linux の非描画 C ケースで、新規 Bill の材料表示候補と許可状態を観測する。

**Architecture:** Controller が固定ケースと型付き期待値を検証し、Worker が実ロード後の RecipeDef・ThingDef・新規 Bill とゲームのツリー表示判定を読む。C の観測とケース適格性を分離し、既存 A/B の資格を流用しない。

**Tech Stack:** Python 3.12+, .NET 10, reflection adapter; private RimWorld 1.7.4985 rev1269.

**Spec:** docs/superpowers/specs/2026-10-26-crafting-material-options-design.md (2026-10-26 user approved)

## Global Constraints

- Linux 版は画面を描画しない。
- 固定したケース ID `bill-ingredient-options.v1`。任意メソッド RPC を作らない。
- ゲーム/第三者 MOD/索引/逆コンパイル本文/生ログは公開しない。既存スナップショット再利用。
- 既存 A/B は後方互換。C は対象 run のみ、baseline は A の診断比較を維持。
- 新規 Bill のみ。Def/フィルターを書き換えて期待値に合わせない。
- C はケース固有の正例・故障例・参照証拠が揃うまで experimental/incomplete。
- Windows 描画、イベント、クエスト、tick、既存セーブ移行は実装しない。

## Review Focus

- false 期待値がカテゴリ欠損・固定材料 pane・未定義 Def で偶然合格しない。
- Worker の欠落/重複/別材料の観測を完全と誤認しない。
- A/B が qualified でも C を自動的に qualified にしない。
- baseline に対象専用レシピ期待値を送らない。
- ツリー走査の循環/過大深度、未知 API、特殊フィルターの非表示を区別する。

---

### Task 1: Controller contract and result evaluation

**Files:** Modify `tools/validation_host.py`; Create `tests/test_bill_ingredients.py`; update old unsupported-C cases in `tests/test_validation_host.py` and private matrix.

**Interfaces:** `expectations.billIngredients`: 1–128 distinct `(recipe, thing)` objects, each exactly `recipe`, `thing`, `visible`, `allowed`; names match existing DEF_NAME (1–128 ASCII name chars), booleans strict. `tests` must equal `["bill-ingredient-options.v1"]` for C, empty otherwise. Worker emits `checks.billIngredients[]` each with caseId/expected/actual/outcome; actual has paneEligible/categoryReachable/categoryVisible/itemVisible/visible/allowed/reasons. Missing or invalid observations => incomplete.

- [x] Write request tests for valid case and malformed/duplicate/unbounded inputs; evaluation tests for missing/partial/duplicate/error/mismatch/unqualified observations, including false expectation with invalid context; baseline dispatch test.
- [x] Run `python -m unittest tests.test_bill_ingredients -v`; observe missing feature failures.
- [x] Implement validation, dispatch and independent Controller boolean comparison. Remove blanket C block. Keep C feature fidelity experimental explicitly (`cNotQualified`) until evidence reviewed.
- [x] Run focused tests and full suite; expect green with existing Windows-only skip.
- [x] Commit contract and tests.

### Task 2: Fixed Worker observer and private behavioral cases

**Files:** Create `worker/RimWorldValidation.Worker/BillIngredientOptions.cs` and `BoundedCategoryTree.cs`; public game-free C# harness `tests/worker/CategoryTree/`; modify `Checks.cs`; create self-made `tests/fixtures/validation-mods/billingredients` and private runner `tests/integration/run_bill_ingredients.py`.

**Interfaces:** `BillIngredientOptions.Write(json, expectations)` reads loaded game state only. Case runs post-load within existing checks/main thread/watchdog bounds. Reflection bound to fixed type/member names. New Bill through recipe MakeNewBill; tree root chosen by actual filter UI; special filters and category/item predicates from actual listing. Explicit `contextUnavailable`, `defMissing`, `paneNotEditable`, `categoryMissing`, `apiUnavailable`, `observationError` outcomes stay incomplete.

- [x] Create XML fixture recipes with editable, all-fixed and special-filter-hidden ingredients plus control recipe; runner asserts explicit positive/negative outcomes and no Def mutation. Run against old Worker to observe missing checks.
- [x] Implement observer with constructor invocation, exact API binding, bounded category traversal (depth 128, nodes 20000) and structured components/reasons. No drawing and no synthetic UI stub.
- [x] Build Release; run private fixture cases against cached snapshot (no download). Positive/fault/missing/fixed-context outcomes expected and recorded; remain experimental unless independent reference supports qualification.
- [x] Commit source/fixtures/runner only.

### Task 3: Evidence, docs and final review

**Files:** Update `docs/contracts/mod-validation-v1.md`, `docs/validation-host.md`, `AGENTS.md`, roadmap, spec and audit; create sanitized research record.

**Interfaces:** Public contract and scope describe only implemented non-rendered case and actual qualification state.

- [x] Record observed build/runtime, fixture inputs, exact outcomes and remaining private-MOD validation scope without private paths/logs/assets.
- [x] Run full Python suite and Worker Release build; inspect diff for private data.
- [x] Independent whole-change review; fix important findings with RED→GREEN regressions.
- [x] Commit, push specified branch to PR #9, update PR summary. Do not merge.

## Execution ledger

User approved the design and explicitly instructed implementation/progress; execute inline without another plan approval pause. Existing user-selected branch/checkout is retained. Source-built user's Flour MOD and R2 dependencies are a follow-up if this first case is experimental; no unverified substitution or game payload download is needed to implement/verify the generic observer.

## Review resolutions and implementation decisions

- Existing specified branch and inline implementation retained after explicit design approval; no extra approval round or worktree.
- Real Bill construction requires a fresh temporary Game/UniqueIDsManager. Restore Current.Game, use initial discovery state, no map/start/tick/render/save. This is not an existing-save UI context; map/start-dependent behavior can remain unobserved.
- Whole C requests remain experimental/incomplete until independent reference qualification; six fixture cases are implementation evidence only. Flour MOD compatibility is not established by these fixtures.
- Missing API can block C after A has executed. Preserve executionStatus, so consumers must inspect stage and execution status rather than assume every blocked result never ran.
- Windows rendering, events/quests, ticks, crafting completion and migration remain excluded; their bugs are not covered. Scope metadata was corrected accordingly without implying extra coverage.
- Observer code changes no Def allowances to force results. MOD constructors can change process globals; no universal absence of their side effects is asserted.
- Fresh reviewer found two Important issues: preflight raw categories before recursive game predicates/root resolution, and require context/filter/reason evidence in Controller. Both fixed with regressions; no Critical/deferred Minor findings. The reviewer did not independently repeat the full suite/build/private runs; implementer directly ran them and inspected results.

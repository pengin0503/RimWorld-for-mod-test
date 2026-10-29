# Cケース別独立適格化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Implement task-by-task; avoid per-task agent dispatch.

**Goal:** 材料候補と自作イベントを別々の参照経路で評価し、証拠が揃ったケースだけ資格を付ける。
**Architecture:** C0で公式参照の文脈/APIを実証してから、別実装のprobeとControllerのケース別資格を接続する。片方の不成立を他方の実行の停止理由にしない。
**Tech Stack:** Python3.12+、C#/.NET10、GitHub Actions、Linux（必要な部分だけ）。
**Spec:** [共通設計](../specs/2026-10-29-linux-validation-next-design.md)。独立probe/資格は未実装。C0の[調査状況](../../research/c-reference-entrypoints.md)を記録。対応DLLの正常取得・署名確認が未完了のため、後続は未着手。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用、索引でMODを照合、必要なpayloadのみ。同一jobのsnapshotは1回準備して再利用。
私有資材/生ログ/識別子/秘密情報を公開しない。未適格・中断をpassedにしない。
設計書の共通制約をすべて適用する。実装前に最新main/AGENTS/PR27の状態を再確認する。

## Review Focus

- Workerの同じhelperを両側のoracleにしない。
- freshGameNewBillとゲーム開始後のBillを同じ文脈にしない。
- 物の自然生成の絶対個数とイベント報酬deltaを混同しない。
- 空/欠落/不正なfalseや、正例不成立のmutation拒否を成功にしない。
- 片方のC資格、A/B/map資格、古いcacheを他ケースへ流用しない。

### Task 1: C0 参照経路の成立性ゲート

**Files:** create docs/research/c-reference-entrypoints.md。read worker/RimWorldValidation.Worker/BillIngredientOptions.cs、EventChoice.cs、既存2fixtureと対応buildの私有DLL。
**Interfaces:** outputはケースごとのAPI署名/呼出順序/初期化文脈/採取点/有限停止方法/成立・blocked理由の記録。公開するのはAPI名と調査結論だけ。

- [ ] 既存DLLとsnapshotのゲーム/CLR hashを照合して再利用する。必要な型・メソッドだけを調査し、逆コンパイル本文は私有領域に置く。
- [ ] 材料は公式ロード後のfresh Game/new Billで実フィルターUIのツリーへ到達できる入口と、可視/許可の独立採取点を確定する。現在のWorkerの判定式を複写するだけなら成立としない。
- [ ] イベントは公式MapGenerator.GenerateMapの完了点とGame.FinalizeInit前の文脈を確定し、TryExecute/Activateと実mapのstack採取を設計する。fixtureのRewardCountをoracleにしない。
- [ ] 署名・文脈・取得可能な証拠が揃ったケースだけTask2へ進む。署名を推測してコードを先に書かない。成立しないケースはblockedとして理由と必要なゲーム内確認を保存する。

### Task 2: 独立probeと比較行列

**Files:** create experiments/official-comparison/compare_c.py、tests/test_c_comparison.py、tests/fixtures/validation-mods-src/CReference/CReference.csproj / CReference.cs、tests/fixtures/validation-mods/creference/About/About.xml。modify P2 registry/workflow（c-compare追加）。
**Interfaces:** `compare_case(case_id: str, product: dict, reference: dict) -> dict`、CLI `compare_c.py --snapshot S --out O --worker W --harmony-dll H --case bill|event|all`。C0の署名・採取点に実装を拘束する。

- [ ] REDテスト: 正常な独立行はequivalent、空同士/重複/recipeやchoice違い/文脈違い/falseと未観測の混同は拒否。正例に対する値のmutationで不一致を検出。private文字列を入れた完全サマリーの出力にも含まれない。
- [ ] `python -m unittest discover -s tests -p test_c_comparison.py -v`で失敗を確認する。
- [ ] 独立fixtureを実装し、product Workerへの参照/import/判定関数共有を禁止する。公式実行は私有HOME・時間180秒・RSS2 GiB・ログ8 MiB・プロセス群回収付き。期待値は参照側の結果生成へ送らない。
- [ ] 既存材料6要求/イベント4要求を両側で実行。正例は各3独立プロセスで一致後、不一致例・不在例の判定感度を確認する。自然生成の個数や座標は比較せず、固定条件と必要な差分だけを比較する。ケース完了までの診断差・例外・未分類も資格拒否にし、engineノイズは事前定義の完全一致だけを扱う。
- [ ] unit GREENと実物の一致/不一致/blockedをケース別の研究記録に残してcommitする。不成立なら資格変更をしない。

### Task 3: 証拠に限定した資格とcache

**Files:** create tools/case_qualification.py、tests/test_case_qualification.py。modify tools/validation_host.py、tests/test_bill_ingredients.py、tests/test_event_choice.py、tests/test_validation_host.py、docs/contracts/mod-validation-v1.md。ケース別research記録を作る。
**Interfaces:** `qualify_case(adapter: dict | None, platform: str, runtime: str, request: dict, *, runtime_verified: bool) -> dict | None`。返却はcaseId/version/context/evidenceと、実証したofficial/language/fixture制約。C評価関数へ `qualification=None` をkeyword-only引数として渡す。旧呼出しの既定値はexperimentalのまま。

- [ ] REDテスト: 同じbuildでも別case/CLR/文脈/言語/DLCは資格を得ない。材料だけの資格はevent/Dへ漏れない。証拠未登録はcNotQualifiedを維持。中断/欠落/不一致の既存判定を維持する。
- [ ] C資格がある場合の全体fidelity・stage C・qualificationEvidence・cNotQualifiedの整合をテストする。ADAPTERSのlevelsへ一括でCを加える実装は拒否する。
- [ ] baseline keyへcaseId・観測/資格仕様版・文脈を加え、旧A/C cacheは流用しないテストを作る。資格記録変更後に古いsummaryがpassed扱いされないよう再評価する。
- [ ] Task2で合格したケース/範囲だけを登録し、既存A/B/map/Dの回帰、全Python、Workerビルド・合成runnerを実行する。初期範囲はCore/Englishのみ。他の構成は引き続きexperimental。
- [ ] 対応buildの実ゲームで正例/不一致/欠落/中断を再実行してからPR化する。適格化が成立しなければ資格変更を含めずTask2の実験・調査記録だけでPR化し、独立適格化や資格の実装を完了扱いにしない。

**Expected:** ケース別に「適格化済みの範囲」または「実証された停止理由」が残る。C/D全体や任意MOD・実画面の合格へ拡張しない。

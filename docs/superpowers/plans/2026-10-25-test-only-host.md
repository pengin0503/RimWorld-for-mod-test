# 検証専用ホスト：成立性調査と設計確定の計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans when separately authorized to execute this plan. Steps use checkbox (`- [ ]`) syntax for tracking. 今回は文書だけ。以下の試作・製品コード変更・実行は未許可かつ未着手。ユーザーの「実装は行わない」を優先し、この文書を実装指示として実行しない。

**Goal:** 遊べない独立した MOD 検証ホストが Linux/Windows で成立する範囲を証拠で確定し、その後の製品実装計画を作れる状態にする。

**Architecture:** Controller は要求・監視・結果を管理し、別プロセスの検証用 Worker が対応する CLR とビルド別 Adapter を使って実物 DLL の必要な処理だけを実行する。公式ゲーム実行ファイルを起動する製品へフォールバックしない。まず不確かな実行 API/CLR/初期化を調査し、成立前に製品構造を実装しない。

**Tech Stack:** 現存補助は Python 3.12+ と標準ライブラリ。将来の Worker は C#/.NET 10 世代を候補とし、実際の CLR は適格化の対象。Linux x86_64 / Windows x64。

**Spec:** [検証専用ホストの仕様・設計案](../specs/2026-10-25-test-only-host-design.md)。本計画もレビュー用提案であり、実装承認ではない。

## Global Constraints

- 製品は公式ゲームの実行ファイルを起動しない。
- メインメニュー、対話的なコロニー操作、任意のセーブによる継続プレイ、無期限 tick、ゲームへの接続・引き継ぎ、通常起動ボタンを提供しない。
- ゲームファイル・ユーザー情報を公開リポジトリ、公開 CI、配布物へ含めない。
- Windows x64 と Linux x86_64 は別に成立性を確認する。
- `gameVerification=notRun` の既存静的検査結果を、動的検証成功へ読み替えない。
- 原本・通常の設定・セーブを変更しない。
- Anomaly は今回の対象外。
- 今回の依頼は文書作成のみ。試作・依存導入・製品コード変更・ゲーム実行は行わない。

## Review Focus

1. 探索用の標準 CLR で完走しても、未適格なら全体合格にしない：Task 1/4 の判定表で固定する。
2. 自動回復・DLC 追加・並べ替えで対象が消える場合、成功としない：Task 3/4 の故障ケースへ含める。
3. missing assets/音声・native 依存を stub で消した場合、その範囲を合格にしない：Task 2/3 の依存表と検証範囲へ含める。
4. timeout・stale report・子孫残留・対話ループへの進入は、有限な終了と incomplete を要求する：Task 1/3/5 の証拠にする。
5. 素材コピーを除いた秒数や狭い検査だけを高速化の証拠にしない：Task 4 の速度比較表で固定する。

---

## 0. 今回完了した文書作業と実行ゲート

- [x] ユーザーの原意・二用途・プレイ不可を新仕様に記載。
- [x] 独立ホスト、再実装、公式 headless ラッパーを比較し、主案と不採用理由を区別。
- [x] 既存の通常起動経路は不適合と明記。コードは変更しない。
- [x] builder check を 1 回実施。重要な未解決事項なし。成立性の不確定要素は後続の調査へ明示委譲。
- [x] 下記を未実行の計画として作成し、仕様への対応・用語・入出力を自己点検。

**実行ゲート：本仕様のレビューと、別の実装・試作の依頼を受けるまで Task 1 以降を実行しない。** 詳細な製品コード計画は Task 5 で、成立性の実測に基づいて作る。未確認のゲーム API を仮の型・メソッドとして実装者へ渡さない。

## 成果物の置き場所

以下は将来作成するファイルの設計で、現在は作成していない。

| ファイル | 責務 |
|---|---|
| `docs/contracts/mod-validation-v1.md` | 要求・結果・工程・判定と代表的な契約ケース |
| `docs/research/test-host-dependencies.md` | OS/CLR/ゲームビルド別の依存と必要資材 |
| `docs/research/test-host-entrypoints.md` | 正確な API、初期化順、完了観測、終了点 |
| `docs/research/test-host-qualification.md` | 故障 fixture、別環境の比較結果、適格化範囲と反証 |
| `docs/research/test-host-performance.md` | 条件別の全体時間、範囲差、速度の結論 |
| `docs/superpowers/plans/test-only-host-product.md` | 調査通過後に作る製品実装計画。正確なソース分割・API・テスト |
| 非公開の run 領域 | 実物・生ログ・結果・試作。公開成果物には自作コードと集計のみ |

### Task 1: 要求・結果契約と判定ケースを固定する

**Files:** Create `docs/contracts/mod-validation-v1.md`。将来の JSON Schema/実装はこのタスクに混ぜない。

**Interfaces:** 入力は本仕様 §6–9。出力は schemaVersion 1 の `modValidationRequest` / `modValidationResult`、`status` / `executionStatus` / `fidelity` と工程ごとの判定表。

- [ ] 要求の必須項目、未知フィールド・版の拒否、非空の検査範囲、A/B の依存関係、B の期待パッチ指定、C の test ID/上限を列挙する。
- [ ] 結果の runId/nonce/hash、実ロード順序、診断・打切り・測定値の必須性を定義する。未観測を `0` や空配列で代用しない。
- [ ] 契約ケースに「experimental 完走＝executionStatus completed / status incomplete」「期待 patch 不明＝incomplete」「起動前依存不足＝blocked」「qualified な assertion 不一致＋全体完了＝failed」を記載する。
- [ ] 「途中エラー＋timeout＝incomplete と確定診断を併記」「stale nonce＝incomplete」「要求なし＝blocked」「B 未要求＝notRequested」を追加する。
- [ ] ケースを本仕様の判定順序と照合し、S の結果 schema/終了コードと混同していないことをレビューしてコミットする。

**Done:** 全てのケースの期待 status を一意に説明できる。製品コードはまだ作らない。

### Task 2: 依存図と最小実行経路を静的に調べる

**Files:** Create `docs/research/test-host-dependencies.md`, `docs/research/test-host-entrypoints.md`。原 IL/逆コンパイル本文は公開しない。

**Interfaces:** 入力は識別済みの私有ゲーム一式と Task 1 の要求範囲。出力は `(gameBuild, OS, architecture, CLR, stage) -> requiredInputs / entrypoints / completionEvidence / blockers` の表。

- [ ] 既存の受領 hash・ビルド識別を再確認し、コピー/解析のツール版を記録する。未受領ファイルは存在を推測しない。
- [ ] Controller の起動位置に依存するゲームのパス解決、assembly redirect、binding、JIT、静的状態、実ローダーまでの呼出しを追跡する。
- [ ] A/B の初期化順と遅延処理、最終 MOD 順序、自動回復、エラー検査、翻訳、Harmony 観測の正確な候補 API と引数を実物に対応付ける。
- [ ] UI・描画・音声・Steam・asset pack の依存を各 stage に付ける。不要と確認したものと、未提供のため検証できないものを区別する。
- [ ] Linux/Windows、標準 CLR/WaylithClr の各候補を「利用可能／不足／未確認／非対応」で分類し、最小試作を実行できる組と停止理由を決める。
- [ ] 本物の処理と同じ順序を呼ぶ方法、対話的ゲーム状態へ入る前に止める方法が説明できるかをレビューしてコミットする。

**Done:** 未確認 API に製品実装を依存させず、次の有限な試作の呼出し・必要入力・観測点を具体化できる。できなければ証拠付きで停止する。

## Windows 実行基盤についての補足（2026-10-25）

Windows 版は引き続き正式な設計対象。iPad 利用を理由に Linux 版だけへ限定しない。Linux のこのセッションで Windows 用ソースを作成し、GitHub Actions の Windows runner でゲーム不要のビルド・テストを確認する経路を使える。既存の Windows 自作 fixture テストは成功済みだが、将来の C# Worker のビルドや実物 DLL の検証が済んだ意味ではない。

Task 2 の環境表には「Windows のゲーム不要 CI」と「私有資材を使う Windows 実行ホスト」を別行で持つ。Task 3/4 の実物 Windows 検証は、接続した Windows ホスト等を得た場合にだけ実施する。公開 runner へゲーム資材を投入しない。OpenAI の Remote 機能は利用可能なら選択肢だが、未設定のホストやアカウントへの提供を前提にしない。詳細と公式資料は [仕様 §7](../specs/2026-10-25-test-only-host-design.md) を参照。

Linux 版受領は依存確認・最小試作の材料が増えることで、製品実装の詳細が全て確定した意味ではない。共通契約・監視と Windows 用の開発準備は Linux 版入手と切り離せる。今回も文書補足のみで、試作・コード変更・CI 設定変更は行わない。

### Task 3: 有限な独立ホストの成立性を試す

**Files:** 将来の試作用 `experiments/test-host/`（自作ソースのみ）。結果集計は Task 2 の研究資料へ追記。ゲーム資材・実行出力は非公開領域。

**Interfaces:** Task 2 が固定した API と環境を使用。Task 1 のケースごとの結果と、各工程の開始/完了/差し替え/停止を出力する。試作 interface は Task 2 の確定後に定義し、現在は仮のゲーム API を書かない。

- [ ] Core の最小構成を新規 Worker で読み、実際の OS/CLR/入力 hash と工程を記録する。標準 CLR の実行成功を qualified にしない。
- [ ] 遅延処理・翻訳後半・static constructor・エラー検査の完了を観測し、コールバック一回や Def 数だけで済ませない。
- [ ] XML patch の意図的失敗、未解決参照、初期化例外、期待 Harmony 欠落の自作 fixture を一つずつ実行し、実物処理の失敗を検出できるか確認する。
- [ ] MOD 自動回復、順序変更、依存/素材不足、観測前のログ、途中書き結果、nonce 不一致を故障ケースとして追加する。
- [ ] timeout・ログ上限・プロセス子孫停止・対話ループ進入を自作 fixture で確認する。GUI を作らず終了し、原本の設定/セーブ/資材が不変であることを照合する。
- [ ] OS/CLR ごとの成立範囲と未対応箇所を記録する。主案が成立しなければ公式起動へ切り替えず停止し、判断資料を残す。

**Done:** 正常系だけでなく既知故障を観測でき、遊べない有限の検証経路が成立している。実行できない環境の欄は未確認のまま残す。

### Task 4: 同等性と速度を別々に評価する

**Files:** Create `docs/research/test-host-qualification.md`, `docs/research/test-host-performance.md`。

**Interfaces:** 入力は Task 1 の契約、Task 3 の証拠、開発時に別途得られる公式環境の比較結果。出力は OS/ビルド/CLR/Adapter/工程ごとの適格化表と、測定範囲付きの性能表。

- [ ] 正常、XML patch 失敗、cross-reference、翻訳、初期化、Harmony 登録、代表的な実メソッド呼出しの比較ケースと期待値を、結果を見る前に固定する。
- [ ] 開発用の別作業で本物の環境と照合する。製品から公式 executable を呼ばない。比較環境がなければ未適格として記録し、毎回ユーザーへ PC 起動を要求する仕様にしない。
- [ ] 起動順序と失敗検出に差が出るケースを調査し、未解決の差がある範囲を qualified から除外する。Linux の比較結果を Windows 欄へ転記しない。
- [ ] 同一条件で初回全体・再実行・Worker 単体を別計測する。各条件原則 5 回、中央値/範囲、cold/warm、比較ロード地点、追加検査の差を記録する。
- [ ] S のみを A/B の高速化に読み替える、コピー時間を隠す、未計測の倍率を出す、という誤った結論がないかレビューしてコミットする。

**Done:** 「何がどの環境で検証済みか」「実際にどれだけ待ち時間が短くなるか」を別々に説明できる。速度優位がなければその結果も残す。

### Task 5: 製品実装の詳細計画と移行判定を作る

**Files:** Create `docs/superpowers/plans/test-only-host-product.md`。Modify 新仕様と README の状態欄。**このタスクでも製品実装は別依頼**。

**Interfaces:** Task 1 の契約、Task 2 の正確な API、Task 3 の成立範囲、Task 4 の適格化/速度結果を受け取る。出力は未実行の TDD 実装計画と、進める/条件付き/主案不成立の判断。

- [ ] 成立した範囲だけに製品の最初の対応表を限定する。C のテスト interface は有限なケースとして設計し、D の一時世界/tick は別計画にする。
- [ ] Controller、Worker、Adapter、結果契約、監視の正確なソースパス・型・関数・入出力・受け入れテストを固定し、各タスクを失敗テスト→最小実装→成功テストで書く。
- [ ] 既存 `tools/mod_preflight.py` の `play` と `launch_command`、`tools/preflight_gui.py` の起動ボタン/呼出し、起動関連テストを廃止するタスクを入れる。`play` は移行エラーになり、どの入口も公式ゲームを spawn しないことを検査する。
- [ ] 静的検査の公式 executable 必須条件を外し、ゲーム資材と独立した検証 Worker を別入力にする計画を入れる。既存プロフィールの読み取り移行、通常設定を上書きしないことを検査する。
- [ ] Windows/Linux の CLI 同一契約、Windows の検証専用画面、JSON 保存、取消、非対応表示、原本保護、子孫回収、結果欠損と古い結果の拒否を受け入れテストへ対応付ける。
- [ ] CI は自作 fixture と公開可能なコードのみ、実物検証は私有領域とする。実物がない CI の成功を互換性検証と呼ばないチェックを含める。
- [ ] 仕様 R1–R7 と S/A/B/C の対応表を更新し、レビュー用として提出する。実装へ自動移行しない。

**Done:** 未検証の根幹を隠した実装計画にならず、別の実装依頼が来た時に進める範囲と停止条件が明確である。

## 今回の自己点検と引き継ぎ

R1/R2 は主仕様 §2/5/7 と Task 2–5、R3 は §6/7 と Task 2–4、R4 は §2/6/11 と Task 3/5、R5 は §10 と Task 4、R6 は §9 と Task 1/3/4、R7 は §8/11 と Task 2/3/5 に対応する。結果の status と fidelity は全タスクで同じ意味を使う。

詳細な製品コード計画を今書かないのは、独立ホストの成立と正確な呼出し経路が未確認だからである。これは未完の製品実装を完成と見せるものではなく、現在の依頼範囲である仕様・設計と、次に必要な調査を完成させるための段階分けである。

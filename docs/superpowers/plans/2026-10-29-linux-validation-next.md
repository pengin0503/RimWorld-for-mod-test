# Linux検証ホスト：次の5作業の全体計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline for each approved sub-plan. This file is a coordinator plan; implementation is not authorized by writing it.

**Goal:** 再検証の継続性、Cの信頼性、実用構成の効率、Linuxの資源制御、文書の正確さを順に改善する。
**Architecture:** 共通検証基盤を先に整え、C・実MOD・メモリの独立した実装PRへ分ける。Dの不合格を隠すための基準緩和や自動マージはしない。
**Tech Stack:** 現行Python/Worker/GitHub Actions/R2読取の構成を維持する。
**Spec:** [共通設計・制約・判断理由](../specs/2026-10-29-linux-validation-next-design.md)。提案段階、実装未着手。

## 実装着手時の追記（2026-10-29）

ユーザーが既存PRの全マージと実装開始を指示。PR27は2f5df30、PR28はb66bcf9でmainへ統合済み。以下の計画作成時の記述は履歴として保持する。P1から順次着手し、新規PRのマージは別途指示を待つ。

## 現状と前提（計画作成時）

2026-10-29のmainは6601383（PR26まで）。[PR27](https://github.com/pengin0503/RimWorld-for-mod-test/pull/27)は未マージ。
COWの専用Btrfs実測はPR27で完了。Dの60/600/600の実tick等は一致したが視点・診断差で独立適格化は不合格。
Cも2ケースとも独立適格化未完了。Linuxメモリ監督はsoft、現在のcgroupはro。
計画作成ではMOD索引やゲームを取得していない。候補MODは未照合で、作業開始時に索引で確定する。

## Global Constraints

Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能は対象外。
R2は読取専用。必要ファイルだけ段階取得、同じsnapshotは再利用。私有資材/生ログ/索引/秘密情報は非公開。
未適格・不明・中断の判定を保持し、実物未実行を適格化済みとしない。PRマージは別途ユーザー指示を必要とする。

## Review Focus

各子計画に、失敗条件とそれを検査するテスト/実物受入を配置している。
特に資格の一括拡張、秘密付き別ref実行、古いsummary、未完了を含む性能中央値、委譲なしのhard表示を拒否する。

## 順序と独立した成果

| 順 | 子計画 | 先行条件 | 完了の判定 |
|---|---|---|---|
| P1 | [文書整合](2026-10-29-linux-docs-alignment.md) | 現状確認のみ。先行可能 | 現行説明とコード/根拠/PR状態が一致 |
| P2 | [検証workflow常用化](2026-10-29-private-validation-workflow.md) | PR27 helperのmain統合。合成部分は先行可能 | mainの手動入口、選択suite、snapshot再利用、秘密なし実行、正しい集計 |
| P3 | [C独立適格化](2026-10-29-c-independent-qualification.md) | P2。最初にC0参照経路ゲート | ケースごとの独立証拠と限定資格、または成立しない理由を明記 |
| P4 | [実用MOD回帰・負荷測定](2026-10-29-real-mod-regression.md) | P2と実行時の索引照合。P3の成功は不要 | 正常な検証結果に限定した時間/メモリ/cache/COWの測定 |
| P5 | [Linuxメモリ強制上限](2026-10-29-linux-memory-hard-limit.md) | 明示された書込み可能な委譲cgroup。P2への接続は統合時 | 実物で子孫制限・OOM理由・回収を確認。環境なしならblockedを維持 |

基本はP1→P2→P3→P4。P5のG0環境確認はP2後に先行できるが、環境待ちでP3/P4を止めない。
P3の片方の参照が不成立なら、もう片方とP4を進める。Dの独立適格化の解決はこの5件の成功条件に追加しない。

## 実施チェックリスト（未実施）

- [ ] 各実装前にmain/AGENTS/PR27の更新を確認し、隔離branchを使う。
- [ ] P1の文書整合を独立PRにする。
- [ ] PR27が未統合ならhelper統合を待ち、P2の合成部分から進める。
- [ ] P2を実装・公開検査し、main統合後の手動受入を行う。
- [ ] P3のC0でケース別の参照経路を成立/blockedへ分類し、成立した範囲のみ比較と資格のcommitへ進む。
- [ ] P4で索引を照合し、S→Mの順で予算内の実用測定を行う。
- [ ] P5の委譲環境を確認し、利用できる場合だけlow-level→Workerの順でhard制限を実証する。
- [ ] 各PRで関連RED→GREEN、必要な全suite、実物受入、必要な独立レビューを行う。実装中に環境依存の既存失敗が出た場合も隠さず名前を記録する。
- [ ] 文書を実測結果へ更新する。blockedやincompleteを完了済みに書き換えない。

## 今回の成果と次の判断

今回はこの全体計画・共通設計・5つの子計画を作成しただけ。コード、workflow、R2設定、ゲーム/索引取得、実ゲーム実行は行っていない。
推奨は本人が順次実装し、各実装PRの最後に必要な独立レビューを行う方式。まずP1/P2を着手単位にする。
今後の実装で追加の環境や参照経路の設計が必要になった場合も、該当ゲートで止め、他の独立作業は継続する。

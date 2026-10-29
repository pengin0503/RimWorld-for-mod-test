# Linux共通私有検証入口（P2）

追記: PR29/30/31はmain統合済み。[main手動受入の確定記録](2026-10-29-private-validation-acceptance.md)を参照。以下の未マージ・受入前という説明は実装時点の記録。

2026-10-29。基準main `b66bcf932110184c726dffe1b6a623a604d4862d`。
既存PR27/28は統合済み。P1文書整合は[PR29](https://github.com/pengin0503/RimWorld-for-mod-test/pull/29)、
本実装は[PR30](https://github.com/pengin0503/RimWorld-for-mod-test/pull/30)。新規2件は未マージ。

## 実装範囲

main-only workflow_dispatch、固定suite、開始commitのcheckout、run/attempt/commit結合を追加した。
ゲームsnapshotは一度だけ準備。秘密付き準備と資格情報を引き継がないhelper実行を分ける。
cow単独にはゲーム・索引・MOD・R2・Workerビルドが不要。
ゲーム/Harmony/Btrfsの前提をsuite別に判定し、不足したsuiteをblockedとした後も独立suiteを試す。
全suiteのplaceholderを最初に保存し、開始前・helper実行中・完了時にcheckpointを更新する。
再公開は現runの最新checkpointから固定項目だけを構築する。古い成功・部分結果から全体成功を作らない。

実行状態、検証状態、資格状態と固定受入試験の成否を分ける。
C材料6＋自作イベント4、D自作fixture10の受入成功もC/Dをqualifiedにしない。
D独立比較60/600/600の視点・診断差は未解決。比較不合格は受入不合格のまま。
RSS4 GiB/ログ8 MiB/15分をhelper外側で監督し、合計実行40分・workflow45分。
RSSポーリングはhard memory制限ではない。

## 子回収の回帰

実Workerや公式比較はsetsidするため、helperのprocess groupだけをkillする方式では回収できない。
公開Linux CI [40864776703](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40864776703)で
`test_timeout_recovers_detached_descendant` と
`test_orchestrator_cancellation_recovers_detached_descendant` が実際に失敗した（332テスト、失敗2）。

既存Linux pidfd/subreaper guardianを外側に置き、停止時はguardianへSIGTERMを渡して実際の子終了を待つよう修正した。
終了コードはguardian自身の0ではなくhelperの結果から得る。生存した子を回収した場合もincompleteとする。
子孫全体のRSSを数え、別sessionの子も対象とする。kernel I/OでSIGKILLが遅れる場合、回収の完了も遅れる。
修正後の公開CI [40865102754](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40865102754)は全8ジョブ成功。
Linux Python 3.12では333テスト成功（Windows専用8件skip）、native回収5件も実行成功。

独立最終レビューではC#共有コンパイラーの常駐が正常helperを中断にする可能性をImportantとして指摘。
実SDKでの新規buildを回帰試験に追加し、公開CI
[40865649115](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40865649115)で
`test_fixture_build_finishes_without_background_compiler_descendants` の失敗を確認した。
実際のコンパイルはexit0だが常駐子が残り、中断扱いになる再現だった（Linux334テスト、失敗1）。
私有子環境に `UseSharedCompilation=false` を加え、固定自作プロジェクトのbuildへ継承する。
これは[MSBuildの環境プロパティ](https://learn.microsoft.com/en-us/visualstudio/msbuild/how-to-use-environment-variables-in-a-build)として扱われる。
既存のfixture/比較プロジェクトにはこのプロパティの上書きがないことも確認した。
修正後の[最終実装CI40865894252](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40865894252)は全8ジョブ成功。
Linux Python3.12/3.13は各334テスト成功（Windows専用8件skip）。SDK-backed buildとnative回収を実行し、修正を確認した。
最終レビューのCritical/Important未解決は0、Minor指摘は0。以後の変更は本記録だけ。
ローカルでは関連25テスト成功（native6件skip）、既存イベント9テスト成功、compileall・diff検査・文書相対リンク検査も成功。

## ローカル環境の制約

この環境ではプロセスAPIのPIDと `/proc/self` が一致しない。
新しい入口はこの状態を開始前に拒否する。native回収の証明にはこの環境でのskipを使わず、公開Linux CIを使用した。
ローカル全件試験も180秒で停止（exit124）。以下の既存試験が失敗またはerrorとなった。

- `test_gui_host.LaunchTests.test_closing_the_gui_stops_its_children`
- `test_gui_orphan.DetachedWorkerTests.test_interrupt_preserves_keyboard_interrupt_and_stops_gui`
- `test_gui_orphan.DetachedWorkerTests.test_memory_stop_does_not_report_success_exit_code`
- `test_gui_session_lock.SessionLockTests.test_guardian_crash_keeps_session_busy_while_detached_worker_lives`
- `test_gui_session_lock.SessionLockTests.test_supervisor_crash_stops_detached_worker_before_session_cleanup`
- `test_validation_host.RunTests.test_interrupted_supervision_kills_the_worker`

最後に実行中だったのは `test_validation_host.RunTests.test_memory_limit_stops_the_worker`。
これらを通過したというローカル全件成功の主張はしない。上記公開CIでは既存試験も通過した。
Windowsの製品コード・新機能は変更していない。

## 統合後に残すゲート

main手動smoke/cow/C回帰/D回帰を各1回、allを1回実施し、snapshot準備1回・cow取得0・公開私有情報0を確認する。
mainのbranch保護は無効であることを読み取り確認した。既存の書込権限境界とmain運用を前提とし、保護設定は変更していない。
branchへsecretを渡してこの受入を前倒ししない。旧branch専用workflowは手動受入完了後に廃止する。
ゲーム・第三者MOD・索引・生ログは今回取得しておらず、Artifacts/Cacheにも保存していない。

P3/P4はP2の統合・受入後に進む。P5に必要な明示的委譲先は未設定、cgroup v2 rootは書込不可と読み取り確認した。
これはG0実装やhard制限の証明ではなく、実物受入がblockedであるという現環境の記録だけである。
C/Dの適格化やLinuxのmemoryHard=falseは変更しない。

# 有限tick D：公式との独立比較（2026-10-29）

対象：Linux x86_64 / RimWorld1.7.4985 rev1269 / 同梱WaylithClr。PR27。
Dの独立比較を実行したが、まだ `qualified` へ変更しない。製品の `experimental / incomplete` と `dNotQualified` は維持する。

## 別経路で観測したこと

開発専用の `experiments/official-comparison/compare_ticks.py` と自作TickQualification MODを使用。
同じsnapshot・自作MOD構成で製品の有限実行と公式 `-headless -quicktest` の通常フレーム経路を別プロセスで動かす。
公式側のGame初期化やtickをWorkerで代用しない。別のHarmony probeでStartedNewGameと実DoSingleTickの前後を観測し、
既存GameComponentのCounter、実tick番号、初期化イベント、設定、視点を記録する。
公式側だけ有限終了ガードを置く。製品が余分なtickを呼んだ場合は抑え込まず、追加観測として不合格にする。
実時間120秒・RSS2 GiB・ログ8 MiBを監督し、プロセスグループを終了後にも回収する。対話・セーブは作らない。

最初の[40825630608](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40825630608)は双方60tickに到達したが観測・診断が異なった。
自作の依存宣言を直した[40826261984](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40826261984)でも、
実tick、Counter、開始通知、初期化イベント、world/map設定は一致した一方、視点と診断の違いで適格化を拒否した。
依存先のIDだけでなく取得URLが必要な点は、実ゲームのメタデータ検査から確認し、自作Aboutを修正済み。

## 同じseedで固定視点が一致しない

このビルドは[既存のマップ適格化](map-qualification.md)の時点で同じseedでも生成結果が変動すると分かっている。
Dは実コードでPlayerStartSpotを見せる固定視点を使うので、生成した開始地点が違えば座標も変わる。
上の第2ジョブでは製品が x134.5/z139.5、公式が x116.5/z124.5。
双方とも画面1365×768、rootSize24で、0/60で視点は動かなかった。設定やtickだけの一致を、視点依存の挙動の一致へ拡張しない。
座標差を無視したり、観測結果を正規化して一致したことにする処理は加えていない。

両側でTexture/graphicsに関する診断があり、公式にはさらにgraphics診断があった。
[A/Bの既存記録](test-host-qualification.md)にはheadlessのDrawTextureスタブ警告が共通して存在するとあるが、
今回の診断を単語だけでその既知警告とみなして除外しない。描画系の実ゲーム確認が必要な停止条件として残す。

## 必須条件と持ち越し

- 開始通知1回、相対0/60/600で実tick差分と独立Counterが一致、初期化イベントが残らず、要求の後に余分な製品tickがない。
- Worker最終結果、終了コード、独立probe全行が揃う。途中の1回だけの成功、同じ空記録、途中停止は全体成功にしない。
- 設定と視点の比較条件を事前に固定する。次の適格化には、自然生成の変動と分離できる開始条件、または開始地点に対する相対視点のどこまでを同等と呼べるかの別設計が必要。
- 描画/フレームの診断を実コードと照合して、tickに影響しないと限定できるものと、実ゲーム確認が必要なものを分ける。警告の文字列に `graphics` があるだけでは許容しない。
- 必須APIや資材不足はblocked、開始後の欠落・例外・上限停止はincomplete。未比較の視点依存MOD、任意イベント、長期実行、60000全値の保証へ広げない。
- 期待不一致・未知ID・probe不在・例外・時間/メモリ/ログ上限・途中証拠・子回収は[PR26の実ゲーム受入](2026-10-29-bounded-tick.md)で確認済み。今回の公式比較で再適格化した意味にはしない。

## レビューと公開検証

別レビューで、任意の診断識別子が公開サマリーへ入る点と、既知ノイズを含む単語だけで診断を除外する点を修正。
完全なサマリー作成経路の非公開識別子テスト、既知語を含む本物のエラーを保持するテストをRED→GREENで確認。
サマリーは固定項目・固定分類と数値だけ。Steamの既知診断は対応ビルドの完全なメッセージハッシュ・レベル・カテゴリで限定し、
終了時のNativeAllocation警告も完全一致・レベル・カテゴリ・終了観測後だけに限定する。

新規Python13件と既存D11件は成功、比較fixtureは警告0/エラー0でビルド。
ローカル全体suiteは180秒で打切り（exit124）。既存の
`test_closing_the_gui_stops_its_children`、`test_interrupt_preserves_keyboard_interrupt_and_stops_gui`、
`test_memory_stop_does_not_report_success_exit_code`、`test_guardian_crash_keeps_session_busy_while_detached_worker_lives`、
`test_supervisor_crash_stops_detached_worker_before_session_cleanup`、`test_interrupted_supervision_kills_the_worker`で失敗/エラー、
`test_memory_limit_stops_the_worker`で停止した。ローカル全体成功とは報告しない。
レビュー修正後の[公開CI40827112925](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40827112925)は全8ジョブ成功。
Linux Python3.12は309件実行・8件skip。最終実装SHAは `7606ac82f35a7620145538e31905fb490bc48cb3`。

## 最終の有限境界比較

[私有実測40827107028](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40827107028)で全3回を実行した。
D実行経路は双方とも完走したが、独立比較ジョブは適格化拒否としてfailureで終了。公開CIの成功と区別する。

| 回 | 要求tick | 製品と公式の実tick/Counter | StartedNewGame | 初期化イベント残存 | 視点差 | 診断数（製品/公式） | 独立適格化 |
|---|---|---|---|---|---|---|---|
| 1 | 60 | 0/60で0/60に一致 | 1回 | なし | x/z | 1/4 | 拒否 |
| 2 | 600 | 0/60/600で0/60/600に一致 | 1回 | なし | x/z | 1/4 | 拒否 |
| 3 | 600 | 0/60/600で0/60/600に一致 | 1回 | なし | x/z | 1/4 | 拒否 |

全3回でworld/map設定・ロードMOD順序・画面1365×768・rootSize24は一致し、各実行中に視点は移動しなかった。
製品の視点は順にx/z=118.5/112.5、114.5/109.5、118.5/112.5、公式は全3回107.5/141.5。
公式はそれぞれ17.579/26.531/26.431秒、全回exit0。製品D段階も全回completed。
診断数はエラーと警告の合計で、エラー件数を意味しない。最終の厳密な除外後には、描画関連のほか公式に未分類2件も残った。
未分類を無害と推測して除外しない。比較サマリーの `sensitivity=true` はCounterを1ずらした記録も拒否した意味に限り、
基準比較が不成立な本実測から独立適格化の判別感度が証明されたとは呼ばない。

結論：COWの対応FS実測は完了。Dは実装と有限到達の独立観測を確認したが、独立適格化は未完了。
次の停止解除条件は、事前に定義した等価な開始視点の確保と、描画・未分類診断の実ゲームでの個別照合。
この文書追記後に実装コードは変更していない。

R2は読み取り専用。各私有CIではランタイム初回準備1回を全ケースで再利用し、実行にはクラウド認証を渡さない。
第三者MODを選定せず自作fixtureのみ。ゲーム資材・生ログ・逆コンパイル本文・索引・認証を公開しない。
Windows新機能、Cの独立適格化は対象外。

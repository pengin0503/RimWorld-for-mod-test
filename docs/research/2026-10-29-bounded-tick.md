# 有限tick D：実装と検証範囲（2026-10-29）

PR #26。対象：Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。
Dの独立適格化、Cの独立適格化、COW対応FSの性能、Windows新機能は本作業の完了条件に含めない。

## 呼出経路

既存のマップ生成はGame.InitNewGameのマップ生成部分で停止していた。
対応DLL（SHA-256 `0be7a7ea4b3111d4430f45b36c234a5e43287880b0514b23915f2ef9a0629e16`）を私有領域で調査し、
ゲーム開始処理と単一tickの経路を確認した。既存DLLのMD5/サイズはR2 Game-Linuxの同名オブジェクトと一致し、
R2 Version.txtは1.7.4985 rev1269。調査のためのゲーム再取得はしていない。

D専用の経路は、開始ポーンの思考付与、Game.FinalizeInit、単一マップの選択、Scenario.PostGameStart、
History初期化、開始研究、GameComponent.StartedNewGameを行い、初期化のwhen-finished処理後に観測する。
UI/環境音のマップ切替通知・カメラのフレーム更新/入力・pause-on-loadの追加tickは省略する。対話シーンや保存は作らない。
ゲーム内部のPlaying状態と「ユーザーが遊べる起動入口」は別であり、製品は有限実行後に終了する。

TickManager.DoSingleTickの実経路はゲームtick番号を更新し、世界・マップ・GameComponent等を処理する。
WorkerのHost.Tickはフレーム処理なので回数を到達証拠にしない。DはTicksGameの実差分と、ゲームが呼ぶ
fixture GameComponentのCounterを別に記録する。ゲームが捕捉してログへ変えた例外も完了にはしない。

最初の私有実行では開始通知とtick0まで到達したが、1tick目の
`GenTicks.GetCameraUpdateRate`からポーン/Thingの更新頻度計算がCameraDriverを参照して例外になった。
ゲームDLLの実装からこの依存を確認し、D限定で実CameraDriverへ実Camera・開始地点・既定ズーム24を設定した。
DriverはGameObjectへアタッチせず、Awake/Update/input/renderを登録しない。実際のInViewOf/CurrentZoom判定を
使用し、成功する代用関数には置き換えない。UI.ApplyUIScaleで得たランタイムの論理画面寸法も記録する。
この固定視点の影響を独立比較へ含めるまで、他の視点条件や任意MODの挙動を保証しない。

初期化イベント内ではゲームの待機判定が変わるため、tickはlong eventとwhen-finishedが空になった後の
メインフレームで進める。fixtureも全tickでこの前提を検査する。途中で新しいlong eventが必要なら、
そのケースはincompleteで止め、要求外のイベント処理へ進まない。

## ローカル検証

要求/証拠/キャッシュ/途中保存のPythonテスト、有限実行の合成C#ケース、Workerビルドを実施。
公開テストはゲームなしの契約・合成検査であり、実ゲームtickの証明に代用しない。
ローカル全体テストは180秒で打ち切り、全件成功とは報告しない。既存環境依存の
`test_closing_the_gui_stops_its_children`、`test_interrupt_preserves_keyboard_interrupt_and_stops_gui`、
`test_memory_stop_does_not_report_success_exit_code`、`test_guardian_crash_keeps_session_busy_while_detached_worker_lives`、
`test_supervisor_crash_stops_detached_worker_before_session_cleanup`で失敗/エラーがあり、
`test_memory_limit_stops_the_worker`で停止した。新規理由コードの辞書漏れは修正し、対象の同期検査は再成功。
既存GUIモデル36件は別途成功。公開CI [40812653139](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40812653139)
は全8ジョブ成功。Linux Python 3.12は296件実行・8件skip、Workerと合成runner、既存モデルも成功。
独立レビュー後、確実な途中不一致の保持、終了状態によるD完了制約、メモリ停止理由/子孫回収の検証を修正し、
固定視点修正の追加レビューで修正必須の指摘なし。

## 私有Linux受入

固定視点修正後の私有ジョブ [40812647946](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40812647946)
（実装SHA `f0b686edde9a18b4359fd3f244a3b0ab97a3c6c2`）で、Dの10ケースと既存C回帰が成功した。
60tickでは0/60、600tickでは0/60/600でゲームtickとprobe値が一致し、開始0・終了60/600・差分60/600。
再実行ではbaselineCached=trueを実測。期待値599に対して実値600ならD failed、未知ID/probe不在はD incomplete。
途中例外はtick61で停止し0/60の観測を保持。時間停止・memoryLimit・logLimitでも途中観測を保持し、
3つの停止ケースすべてで制御用子プロセスの回収を確認した。中断時のendTick/advancedは最後の確認値であり、
停止した瞬間のゲーム内tickを推測しない。全体は全ケースexperimental/incomplete。

初期化イベントを完全に抜けてからtickを進める最終版も、
[40813652506](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40813652506)
（SHA `66539da0ec688c3bffd2cd8a0b7fc1e3f2d645ed`）でD10ケースとC回帰がすべて成功。
probeは全tickで初期化イベントが残っていないことを検査した。60/600の到達とCounter一致、
不一致/未知ID/probe不在/途中例外、3つの上限停止と子プロセス回収を再確認した。
最終版の[公開CI 40813657945](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40813657945)も全8ジョブ成功。
イベントCの4ケース、材料Cの6ケースは同じスナップショットで回帰成功。これはCの独立適格化ではない。
資材準備だけにR2認証を渡し、Worker実行には渡さない。私有生ログ・資材・索引は公開しない。

## 適格化へ持ち越す条件

2026-10-29に[公式との独立比較](2026-10-29-bounded-tick-independent-comparison.md)を追加実行。
同じseedでも変わる開始視点と描画系診断の差が残るため、独立適格化は完了扱いにしていない。

- 公式Linuxの同じ開始条件と独立比較するまではDをexperimental/incompleteに保つ。
- 比較方法は、同じ自作probeを公式headless quicktestで読み、StartedNewGame直後を相対0とし、
  同じ0/60/600でprobe状態・実tick番号・開始通知を別経路で採取する。固定視点の位置・ズーム24・寸法も合わせる。追加のpause-on-load tickを区別し、
  境界前後の余分な進行と診断も比較する。製品から公式実行ファイルを起動する機能にはしない。
- 乱数で変わる自然物の個数を、厳密な一致や適格化の根拠にしない。
- 必須API/資材がなければblocked。開始後の初期化不足・tick不整合・例外・上限・観測欠落はincomplete。
  描画依存や任意MOD固有の状態が必要なら、そのケースを追加設計・実ゲーム確認へ持ち越す。
- 上限60000は入力の上限であり、全値・全構成で完走する性能保証ではない。

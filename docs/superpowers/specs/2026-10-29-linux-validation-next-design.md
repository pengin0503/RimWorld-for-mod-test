# Linux検証ホスト：次の5作業の設計・境界

2026-10-29。ユーザー依頼は「5件の作業の計画」。本書と各計画は提案であり、実装・適格化・環境変更を済ませた意味ではない。

## 基準と根拠

- 最新main: `6601383fc79a0aba29fc6b3d4ec97ad82eec041f`（PR26の有限tick実装まで）。
- PR27: open、未マージ。head `536ae436610629bec099e11763ff94815b4aaa1a`。COW実測とD独立比較の記録はこのPR側にある。
- PR27の公開CI40827979489は全8ジョブ成功。一方、独立D比較40827107028は視点・診断差により不合格。両者を同じ「検証成功」と扱わない。
- Cは `bill-ingredient-options.v1` / `event-choice.v1` が実装済み・未適格。現在のControllerはCを常にexperimental/incompleteとし、A/Bの資格はCへ拡張しない。
- Linux監督はRSSポーリング＋GC上限で `memoryHard=false`。本計画作成環境のcgroup v2はread-only。書込み可能な委譲先は未確認。
- `docs/roadmap/finished-product.md` のD未着手・イベント未実装という記述、READMEのC説明は現行AGENTS/コードと一致していない。

根拠: [AGENTS](../../../AGENTS.md)、[判定契約](../../contracts/mod-validation-v1.md)、[材料C](../../research/2026-10-26-bill-ingredient-options.md)、[イベントC](../../research/2026-10-27-event-choice-fixture.md)、[PR27](https://github.com/pengin0503/RimWorld-for-mod-test/pull/27)。

## 共通制約

- Linux x86_64 / RimWorld 1.7.4985 rev1269 / 同梱WaylithClr。Windows新機能・実機作業・描画UIは対象外。
- R2は読取専用。ゲームは `rimworld-17/Game-Linux/`、MODは `Workshop/<照合済みID>/`。第三者MODを選ぶ前に `rimworld-mod-index.zip` で名前・ID・PackageIdを照合する。
- 任意連携先は自動取得しない。明示したrootと必須依存の閉包のみ。About/LoadFoldersを先に確認し、必要payloadだけ取得する。
- ゲームsnapshotは同一ジョブ内で1回準備し再利用する。別の一時runnerには永続性を仮定しない。私有ゲームをGitHub Cache/Artifactsへ置く方式は採らない。
- 公開は固定項目・固定分類・数値のサマリーだけ。ゲーム・第三者MOD・索引・生ログ・私有パス・逆コンパイル本文・資格情報は公開しない。
- R2資格情報は準備stepのみに渡す。Worker・公式比較・MOD処理には渡さない。`pull_request_target`でPRコードを秘密情報付き実行しない。
- 公式実行ファイルは開発専用の有限比較だけ。製品へ公式起動・プレイ・セーブ・無期限tickを追加しない。
- A/B/mapの既存資格を保つ。未適格ケースはexperimental/incomplete、未知要求はblocked。中断や証拠欠落をpassedにしない。
- 計画の作成は実装開始・PR27のマージ・後続PRのマージ許可を兼ねない。

## 方法の選択（計画作成者の提案）

1. **既存CLIとfixtureを共通の手動検証入口へまとめ、独立PRで段階実装する方式を推奨。** 資材の重複準備を減らし、C/実MOD/メモリを別々に評価できる。
2. 各ブランチ専用workflowを増やす方式は短期作業向けだが、mainから再実行しにくく、同じ資材の準備が重複するため採用しない。
3. 私有資材を長期保存する常設runnerへの全面移行は今回は扱わない。環境運用・費用の新規前提を増やすため。既存の安全な私有snapshotがある環境では再利用する。

実装は本人が同じセッションで順に行う方法を推奨。タスクごとの実装者/レビュー者の増殖はせず、各実装PRの最後に必要な独立レビューを1回行う。

## P1 文書の整合

README、roadmap、dual-use、現行操作手順のLinux部分を、実装済み・未適格・未実装・未マージで統一する。
過去の実測文書は当時の記録として残し、現状へのリンクを付ける。Cを「全イベント/クエスト対応」、Dを「数日プレイ確認済み」と書かない。
PR27が未マージなら、COWの実測完了とmainへの未統合を分けて記載する。

## P2 検証基盤の常用化

新設 `.github/workflows/linux-private-validation.yml` をmainの `workflow_dispatch` 入口とし、既存branch専用workflowを段階的に置き換える。
smokeは既存fixture行列の `ok,harmony-ok,map-ok` だけを選ぶ。既存helperへの固定argvをregistryに置き、呼出元が引数を追加できないようにする。
初期suiteは `smoke` / `c-regression` / `d-regression` / `d-compare` / `cow` / `all`。defaultは `smoke`。
`all` はこの6選択肢中の個別5suiteを実行する意味。後続P3/P4/P5が実装された時点で `c-compare` / `workload` / `memory` を明示登録し、allの内容を文書にも更新する。
未登録suiteや不正入力はR2接続前に拒否する。任意のコマンド、ファイルパス、R2 prefix、外部リポジトリを入力として受け付けない。
main refのみ受け付け、起動時のcommit SHAを固定して全stepで同じcheckoutを使う。PRのpreviewは秘密なしの合成検査で行い、実物受入は許可されたmainの手動実行で行う。
mainの保護/書込権限は運用前提として確認する。別refからsecretを使う必要が生じたら入力制限を外さず、別途運用設計を行う。

- `cow` はR2・ゲーム・索引・Workerビルドを不要とする。専用一時Btrfsを準備してPR27の実験を呼ぶ。
- ゲームsuiteをまとめた同一job内で準備は1回。資格情報のある準備stepと、資格情報のない実行stepを分離する。allでもsuiteごとの開始・終了・終了コードを保存する。
- default timeoutは既存各helperの有限上限を維持し、workflow全体は45分。allでは失敗しても残りの独立suiteを上限内で試し、最終集計を必ず出す。
- サマリーは `executionStatus`（completed/interrupted/notStarted）、`validationStatus`（passed/failed/blocked/incomplete）、`qualificationStatus`（qualified/experimental/notRequested）を別々に持つ。比較不一致をworkflow成功に変換しない。
- サマリー再公開時も再検証する。古いsuccessファイル、例外メッセージ、任意のクラス/メソッド名、unknownキーは公開しない。
- baseline/hash cacheは私有job内に限る。同じhash・言語・DLC・要求・observer版でだけ再利用。中断と未完了証拠を正常cacheへ入れない。

## P3 Cの独立適格化（ケース別のゲート）

先に参照経路の成立性を調べる。C材料の文脈は `freshGameNewBill`、イベントは `freshGeneratedMap`。公式のゲーム開始後の状態を無条件に同じ文脈とは呼ばない。
CReferenceという開発専用fixtureを公式側へロードし、WorkerのC実装・反射helper・評価関数を共有しない。Controllerの期待値を参照側の値生成に渡さない。

- 材料: 実Bill/実フィルターUI経路を通した表示判定と許可状態を、fresh Game・未発見状態・同じrecipeの条件で採る。実際に表示ツリーへ到達したことも証明する。Workerと同じ判定式のコピー、親Allowsだけによるvisibleの推定を参照にしない。
- イベント: 公式map生成完了直後のhookで実IncidentWorker.TryExecuteとDiaOption.Activateを通す。fixtureのRewardCountを答えにせず、実map上のstackの前後を別実装で採取する。自然物の絶対個数や座標の完全一致は比較しない。
- 材料の正常/非表示/未許可/固定pane/カテゴリ外/Def不在、イベントの正常/数量違い/品目違い/fixture不在を、既存ケース行列から再利用する。正常比較は独立プロセスで各3回。正常比較が成立してから期待値だけを変え、判定感度を確認する。
- ケース観測完了までの診断も比較する。事前定義した完全一致のengineノイズ以外の差・例外・未分類診断があれば、そのケースの資格を止める。描画に関する単語があるだけでは除外しない。
- API/参照文脈を作れないケースだけ止める。例えば材料の独立UI経路が不成立でも、成立するイベントの独立比較は進められる。各ケースに独立した研究記録と資格を持たせる。
- 最初の資格候補はCore/English/対応build・CLR・ケース版・文脈だけ。DLC/他言語・任意イベント/クエスト・既存Bill/セーブ・描画レイアウト・実際のクラフトへ拡張しない。
- 証拠が揃ったケースだけ、後続の別commitでケース別資格判定を導入する。`qualified.levels`へ単にCを足さない。全体fidelity、C段階、理由、cache版を一緒に更新し、A/B/map/Dとの混同を検査する。

## P4 実用MODの回帰・負荷測定

既存 `run_linux_regression.py` はVPE＋必須依存、A/英語/Core+Royaltyの5実行を持つ。この実績を出発点にし、ゲーム全体の操作や大規模全MOD取得へ広げない。
計画時点では索引を未取得・未照合であり、次は候補名だけ。候補はVPE、TD Enhancement Pack、その明示的な併用。実施時に現行索引とAboutからID・PackageId・必須依存を確定する。
候補のいずれかが欠落/曖昧なら、そのprofileをblockedとし代替IDを推測しない。

- S: VPEと必須依存。M: VPE+TDを明示選択し、それらの必須依存閉包。C/Dは性能試料へ混ぜず、Aのロード/順序/診断と必要時のmapに範囲を固定する。Bは明示された期待patchがある既存fixtureでのみ別途回帰する。
- 初回payload予算はprofileごと選択ファイル合計256 MiB・5000ファイル・選択/必須依存合計20 MODまで（cachedも含む保守的な上限）（ゲーム初回runtimeは除外）。不足時は停止して必要量を記録し、勝手に全取得へ切り替えない。payloadの合計を取得前に列挙メタデータから確認する。
- 同一入力でcache無効5回、cache作成1回、再利用5回。順序を交互にし、中央値と範囲を出す。OS cacheは消さずwarmと明記。
- Aの期待範囲が完了しない実行は性能の成功標本に入れない。エラーを隠して「高速化」としない。
- 準備/取得時間、検証時間、RSS peak、取得ファイル/bytes、baseline再利用、hash再利用、copy/reflink件数を分離して記録する。
- 実MODのCOW比較は同一Btrfs上に入力・実行MODを置き、製品のverified-copy経路を用いて各5回、copy/reflinkを交互に測る。Btrfsがない場合は通常FSのcache比較だけを完了し、実MODのCOW測定は未実施と記録する。
- 39.8%は自作入力の複製部分、以前の42%はcacheの効果。足し合わせず、実MODの全体時間で再評価する。S/Mの結果を数百MODへ外挿しない。

## P5 Linuxメモリ強制上限（環境条件付き）

前提ゲートは、memory controllerが有効な書込み可能・明示的に委譲されたcgroup v2子階層。現在のro環境では実物受入はblocked。
ホストの再mount・root階層変更・上位制限変更・委譲の自動獲得を製品が行わない。条件がなくてもP1〜P4は進められる。

- defaultはauto。委譲先なしでは既存RSS/GC監督と `memoryHard=false` を維持。require-hard指定時はゲーム開始前にblockedにし、fallbackを強制上限と表示しない。
- 明示された委譲先の下にrun固有leafだけを作り、memory.max=要求MiB、memory.swap.max=0、memory.oom.group=1を設定・読戻しする。必要ファイルや権限が不足ならhardとしない。
- Controllerはleaf外。信頼済みlauncherをgate待機させ、leaf所属確認後にだけWorkerへexecする。Popen後のWorkerへ遅れてPID移動する方式は採用しない。
- fork/setsidした子も同じleafに留め、停止はcgroup.killで子階層まで回収する。cgroup.eventsのpopulated=0を確認した後に自分の空leafだけ削除する。
- OOM理由はmemory.eventsのoom_kill等の増加から判定する。exit codeだけでmemoryLimitと断定しない。中断時はincomplete、Dの途中証拠は保持。
- RSSとcgroupのメモリ会計を混同しない。既存peakRssBytesはRSSのまま、cgroupPeakBytes・OOMカウンターを別項目にする。memory.maxは一時超過があり得るため、測定peakが要求値以下だったことだけを合否基準にしない。
- 同一権限の悪意あるMODに対するセキュリティsandboxではない。権限分離・ネットワーク隔離は今回の機能に含めない。

一次資料: [GitHub手動workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)、[Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)。memory.max、memory.oom.group、cgroup.kill、delegationを確認している。

## Dの持ち越し（5作業とは別の追跡）

PR27の視点x/z差、描画診断、公式側の未分類診断2件は未解決のまま。P2は再測定と明確なサマリーを可能にするが、Dが適格化できるという保証ではない。
Cの資格が得られてもDへ流用しない。別に開始視点の等価条件と診断照合を定めるまで、Dのexperimental/incompleteを維持する。

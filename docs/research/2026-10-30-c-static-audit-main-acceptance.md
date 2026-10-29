# C参照API静的監査：main上の初回受入

2026-10-30（日本時間）、main commit `f582d034dd127dc2de71a9edf1b8d225618d12d7` で [Private Linux C metadata audit #1](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40969021737) を手動実行した。

## 実施結果

- workflow実行は成功、33秒。固定8入力のversion/hashが一致し `binaryVerified=true`。
- 取得42,811,570 bytes、再利用0 bytes、準備5.376秒。Data・Workshop・MOD索引は取得していない。
- scannerは秘密情報を受け取らずに終了し、再検証した固定項目のみを公開した。Artifactsは作成していない。
- **静的結果は `staticAuditStatus=incomplete`、`c0Passed=false`。** workflowの成功は静的調査の完了やCの独立適格化を意味しない。
- メモリ制限はポーリングであり `memoryHard=false`。強制上限ではない。

## 公開可能な観測

固定型9件はすべて見つかった。読み取れた直接呼出の例は次の通りで、offsetは該当メソッド内のIL位置を示す。

- `Verse.Game.InitNewGame` は `MapGenerator.GenerateMap`（328）、`Game.FinalizeInit`（404）、`LongEventHandler.ExecuteWhenFinished`（478）を直接呼ぶ。
- `Game.FinalizeInit` は `ExecuteWhenFinished`（88）を直接呼ぶ。
- `Dialog_BillConfig.DoIngredientConfigPane` は `get_HiddenSpecialThingFilters`（189）と `ThingFilterUI.DoThingFilterConfigWindow`（245）を直接呼ぶ。
- `Listing_TreeThingFilter.Visible` は4 overloadが確認された。各署名と可視性は実行summaryを参照。

上記は存在と直接呼出位置の証拠であり、イベントのキュー実行順序、同一のfresh Game/new Billでの実UI到達、独立した材料候補・報酬差分の採取を証明しない。

`MapGenerator.GenerateMap`、`LongEventHandler.QueueLongEvent`、`ThingFilterUI.DoThingFilterConfigWindow`、`BillUtility.MakeNewBill`、`IncidentWorker.TryExecute` の署名には、公開用の固定型集合では再構築できないものがあり `unreadable` とされた。未知型を自動許可したり、件数だけを成功扱いにしたりしない。

## 後続ゲート

未読署名の固定入力hashと型を私有環境で確認し、必要な型を公開してよいと判断できる場合は別の設計変更と検証を行う。材料ケースは実フィルターツリーへの到達と独立した表示・許可状態、イベントケースは生成後のqueued処理とFinalizeInitの関係および同一freshGeneratedMapでの独立delta採取が確認できるまで、それぞれC0通過にしない。例外、未分類の診断差、観測欠落、有限停止不成立も当該ケースの停止条件となる。

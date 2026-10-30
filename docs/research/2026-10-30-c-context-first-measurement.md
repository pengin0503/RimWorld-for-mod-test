# C0動的参照経路：初回実測

## 静的入口

[監査 #7](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41004600759)（main `e8712bc50cb7b9f0d0931aa40985fbe657788384`）でフィルターUIの署名を読取できた。DoThingFilterConfigWindowはRect、入れ子UIState、2つのThingFilter等を受け取り、Listing_TreeThingFilterの実constructorをIL offset661で直接呼ぶ。
実行行の入口DoThingDefは `instance private System.Void (Verse.ThingDef, System.Int32, Verse.Map)`。残る未読は未使用QueueLongEvent overload token100664992だけ。8入力42,811,570 bytesのversion/hash一致、準備4.503秒、再利用0 bytes。静的結果はincomplete、C0=false。

## 動的入口の実測

[Private Linux validation #7](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41005559878)（main `3d003eb2173406c01d429dc6eb1784c6ab6b542a`、c-context）は私有ランタイムの準備・Worker/fixtureのbuildに成功し、2ケースを63.888秒で完了した。中断ではないが参照ゲートは未通過であり、workflowは失敗、validationStatus=incomplete、qualificationStatus=experimental。これをインフラ障害や製品Cの合格と読み替えない。

| ケース | 実測 | 停止条件 |
|---|---|---|
| event | 製品 generated→marker、公式 init→generated→finalize→marker | official.finalizedBeforeMarker。両側に未分類の診断/終了理由もある |
| material | pane/ui/listing/rowの入口回数がすべて0 | paneDidNotReturn/treeRowNotReached。pane進入前の準備不備とheadlessの制約はまだ区別できない |

公式の自然なFinalizeInitを遅らせたり、CをDの初期化後へ移動して一致させてはいない。今回のevent停止はこのqueued-marker方式が製品と同じpre-FinalizeInit文脈ではないことの証拠であり、別の独立参照方式すべての不可能性を証明しない。

材料はUI到達が未実証。初回結果から原因をnull参照やAPI不在と推測しない。次回はgame/bill/binding/hooks/dialog/pane/completeの固定準備段階と、固定例外分類、両側の終了コード・中断・診断件数/固定keyword分類を追加して原因を分離する。生の例外・私有パス・メッセージは公開しない。分類は診断を無視する規則ではなく、ゲートの拒否条件は維持する。

Cの独立probe/資格/cache登録はまだ行わない。固定APIの署名一致と同じ文脈での独立採取は別のゲートである。Windows新機能は対象外。

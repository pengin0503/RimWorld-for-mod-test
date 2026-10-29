# C0：独立参照経路の確認状況

> **2026-10-30追記:** 以下は10月29日の調査時点の記録。main限定の[静的監査受入](2026-10-30-c-static-audit-main-acceptance.md)では固定8入力の取得・ハッシュ確認に成功したが、一部署名が未読のため静的調査は未完了で、両ケースともC0未通過のまま。

2026-10-29、基準main `f223c514e4ee9c768cb0f819cfd8d9089e2450ff`。
P2の運用受入後、C材料候補と自作イベントの独立参照経路を調査した。
**現在は両ケースともC0未通過。取得経路がblockedであり、公式APIの不成立を実証した意味ではない。**
C/Dの資格、Controller、cache、Workerの動作は変更していない。

## 確認した範囲と取得記録

- 現在のcheckout外に再利用可能なAssembly-CSharp.dll/snapshotは見つからず、dotnet/ilspycmdも未導入。ローカルのR2資格情報も未設定。
- Cloudflareコネクターで、`rimworld-17/Game-Linux/Version.txt` を読み取り、`1.7.4985 rev1269` を確認した。対象サイズ18 bytes。
- 同じprefixのAssembly-CSharp.dllメタデータは15,632,896 bytes、ETag `35242f1a2f872909bb394181c5658cac`。ETagの存在を、ローカルDLLのhash照合成功とは扱わない。
- API署名と呼出順序を調べる目的で、このDLL単体のGETを1回試したが、コネクターが `Worker exceeded memory limit` で失敗した。正常保存0件、実転送量は未確認。15,632,896 bytesは要求対象サイズであり、取得完了量ではない。
- ゲーム全体・素材・第三者MOD・索引は取得していない。自作fixtureだけを読む調査なので、MOD選定用の私有索引は使用していない。
- ゲームと同梱CLRのローカルhash照合、公式メソッドの署名・IL・動的到達証拠は未取得。Version.txtや既存Workerの反射名だけでは代替できない。

## ソースから確認した製品側の文脈

### 材料候補

[BillIngredientOptions.cs](../../worker/RimWorldValidation.Worker/BillIngredientOptions.cs)は実Gameを新規作成し、Current.Gameを一時的に入れ替え、実BillUtility.MakeNewBillを呼ぶ。
recipeの固定フィルター、BillのingredientFilter、Dialog_BillConfig.HiddenSpecialThingFilters、追加のforceHiddenSpecialFiltersを用いる。
Listing_TreeThingFilterのThingDef/カテゴリのVisible、表示rootからの到達、hiddenItemsManager.Hiddenを観測し、最後に以前のCurrent.Gameを復元する。

これは製品側の観測経路の確認であり、公式UIを実際に通った独立証拠ではない。
既存の[調査記録](2026-10-26-planned-work-audit.md)には
`Dialog_BillConfig.DoIngredientConfigPane → ThingFilterUI.DoThingFilterConfigWindow → Listing_TreeThingFilter`
という経路がある。今回のDLLから署名を再確認できていないため、これらは参照候補として扱う。
WorkerのVisible合成式やカテゴリ探索を別fixtureへ複写しても独立参照にはならない。

必要な証拠は、同じfresh Game/new Bill・未発見状態で、実フィルターのツリー描画経路に対象ThingDefが到達したことと、実フィルターによる許可状態。
正常/非表示/未許可に加え、固定pane・カテゴリ外・Def不在を独立に分類する。画面のレイアウトや既存セーブのBillへ範囲を広げない。

### 自作イベント

[Host.QueueMap](../../worker/RimWorldValidation.Worker/Host.cs)は、非同期のMapStage.Generate後に同期の観測をキューへ登録し、その中でEventChoice.Observeを呼ぶ。
D要求がある場合のTickApi.Initializeは、その後の別キューにある。したがってCイベントをDのFinalizeInit/StartedNewGame後へ移すのは文脈変更になる。
[MapGeneration.cs](../../worker/RimWorldValidation.Worker/MapGeneration.cs)も、マップ段でGame.FinalizeInit等を実行しないことを明記している。

[EventChoice.cs](../../worker/RimWorldValidation.Worker/EventChoice.cs)は実IncidentWorker.TryExecuteとDiaOption.Activateを呼び、選択の直前/直後に実mapのItemをThingDef別に合計する。
報酬の値はmapItemStackDeltaであり、fixtureのRewardCountを答えとして読んでいない。
一方、発生・選択実行の一部証拠には自作fixtureのEventOccurred/ChoiceExecutedを使うため、参照fixtureで同じフラグを読むだけでは独立性の証明にならない。

公式MapGenerator.GenerateMapの完了点は参照候補だが、単なるpostfixで十分とは未確認。
生成後にキューへ登録される処理とGame.FinalizeInitの前後関係を対応DLLで調べ、WorkerのfreshGeneratedMapと同じ採取点を実証する必要がある。
自然生成されたSteel等の絶対個数や座標を比較せず、選択による差分を別実装で得る。
正常/数量違い/品目違い/fixture不在を分け、欠落をfalseや0へ補って一致扱いにしない。

[私有静的調査入口の設計案](../superpowers/specs/2026-10-29-private-static-c-audit-design.md)で、取得・非実行解析・公開境界・受入を具体化した。設計に基づく実装は進行中。

## ケース別ゲートと停止条件

| ケース | 確認できたこと | 未確認の必須条件 | 現在の状態 |
|---|---|---|---|
| bill-ingredient-options.v1 | 製品のfreshGameNewBillと観測部品、公式UIの過去の経路候補 | 対応DLLの正確な署名、実ツリー到達、独立採取、有限停止 | C0 blocked：調査資材の正常取得待ち |
| event-choice.v1 | 製品のFinalizeInit前のキュー位置、実map差分、自作fixtureのaction | 公式生成完了点の署名・キュー順序、同じ文脈への到達、独立採取、有限停止 | C0 blocked：調査資材の正常取得待ち |

次の作業は、main限定の私有静的調査入口を設け、既存の準備済みsnapshotから対応DLLとCLRのhashを検証し、対象メソッドの署名・呼出関係だけを取り出せるようにすること。
ゲームを実行しない調査では、runtime全件の再取得を前提にせず、必要DLLとビルド識別情報だけを対象にする。
逆コンパイル本文・DLL・生ログは私有領域に残し、公開はAPI名と確認結果だけにする。
branchへsecretを渡すpreview、公開ダウンロード用proxy、R2の公開化・権限変更で取得失敗を迂回しない。

署名や同一文脈を実証できるまでCReference/比較/資格判定を推測で実装しない。
片方だけ参照が成立すれば、そのケースは進める。表示経路未到達、初期化文脈違い、例外・未分類診断差、観測欠落、有限停止不成立はケースごとの停止理由として残す。
C0通過後も、各正常例3独立プロセスの比較と期待値mutation、診断照合が揃うまでqualifiedへ変更しない。

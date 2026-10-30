# C未読型の位置と入れ子構造の実物確認

2026-10-30、main `b9bb43c5d79f7ee81906a3a5d57d98476f074f4a` の[監査 #6](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41003991812)は成功した。8入力42,811,570 bytesのversion/hashが一致し、準備6.723秒、再利用0 bytes。staticAuditStatus=incomplete、C0=false。

未読2メソッド群の内訳は次の通り。

| 対象 | 位置と構造 | 結論 |
|---|---|---|
| QueueLongEvent token 100664992 | 第1引数、TypeReference、AssemblyRef、入れ子深度0 | 型名未特定。IEnumerator仮説は一致しなかった。製品が使用する別overloadの署名は監査 #5で読取済み |
| DoThingFilterConfigWindow token 100678184 | 第2引数、TypeDefinition、Module、入れ子深度1 | 固定候補filter-ui-stateと一致。Assembly-CSharp内のVerse.ThingFilterUI+UIStateの使用・定義・arityが固定hashに結合してmatched |

入れ子の宣言型を失うscannerの制約は自作DLLでRED→GREEN確認済み（PR #42）。今回、実物フィルターUIの未読原因がこの入れ子型であることを確認した。親型を省いた `.UIState` は許可せず、完全名 `Verse.ThingFilterUI+UIState` だけを公開atomへ採用する。

材料の実ツリー行へ到達したことを観測するため、固定調査メソッドにListing_TreeThingFilter.DoThingDefを追加する。署名や存在は再監査で確認するまで推測しない。キューの未使用overloadは名前の推測追加を続けず、使用overloadでの文脈確認を先行する。両ケースともC0は未通過のまま。

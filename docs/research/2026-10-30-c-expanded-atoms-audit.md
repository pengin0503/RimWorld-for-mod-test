# C署名公開範囲拡張後の実物監査

2026-10-30（日本時間13:12）、main `9beb0d9f4a782b73c293be42a739dce8662f43ce`（PR #40反映後）で[監査 #5](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41001622010)を実行した。workflowと全stepは成功したが、`staticAuditStatus=incomplete`、`c0Passed=false`である。

## 入力と境界

固定8入力、42,811,570 bytesのversion/hashが一致し、`binaryVerified=true`。取得42,811,570 bytes、再利用0 bytes、準備5.605秒。Data・Workshop・MOD索引は取得していない。R2は読取のみ。秘密情報は準備stepだけに渡し、scannerへの資格情報付与や私有資材のArtifacts公開は行っていない。`memoryHard=false`は変わらない。

## PR #40の効果

未読メソッド群は監査 #4の3件から2件へ減った。

| 対象 | 監査 #5の観測 |
|---|---|
| MapGenerator.GenerateMap | found。Action<Map>を含む1署名を読取 |
| LongEventHandler.QueueLongEvent | 2 overloadの署名を読取。残る1 overloadはunsupportedTypeAtom、token 100664992 |
| ThingFilterUI.DoThingFilterConfigWindow | unsupportedTypeAtom、token 100678184。読取済み署名なし |

GenerateMapの署名は `static public Verse.Map (Verse.IntVec3, RimWorld.Planet.MapParent, Verse.MapGeneratorDef, System.Collections.Generic.IEnumerable`1<Verse.GenStepWithParams>, System.Action`1<Verse.Map>, System.Boolean, System.Boolean)`。
QueueLongEventの読取済み2署名はAction<Exception>を含む。これらの完全名を公開できることと、参照assemblyの解決確認は区別する。固定候補照合は今回もbill/incident-parmsだけがmatchedであり、他候補の不在を証明しない。Nullable/ThingCategoryDefが残る署名に出現するかは今回も未確認。

## 次に調べること

同じunsupportedTypeAtomが残っているため、名前を推測して公開atomを追加する手順は繰り返さない。現行SignatureProviderはTypeDefinition/TypeReferenceをnamespaceとsimple nameから作り、入れ子の宣言型や参照scopeを署名名へ含めていない。これはコード上の制約であり、今回の2箇所の原因と確定したものではない。

次の診断設計では、未知の生名を公開せず、固定method/tokenに対して未対応型の位置（戻り値/引数index/型引数の経路）とmetadata handle種別を有限な構造で記録する。入れ子型と同名の別assemblyを自作fixtureで区別できること、未知文字列・不正scope・循環・過深度を拒否できることを先に確認する。候補を追加する場合は完全名・宣言型・assembly・arityを固定し、固定入力hashに結合して再監査する。単なる名前の表示許可をassembly照合の代替にしない。

## 後続の停止条件

静的監査の成功だけで独立probeや資格を実装しない。材料ケースは同じfresh Game/new Billから実フィルターツリーへ到達し、表示・許可を独立採取できることが必要。イベントケースは生成後のqueued処理とFinalizeInitの関係、同じfreshGeneratedMapでの独立delta採取を実証する必要がある。表示経路未到達、文脈違い、例外・未分類診断差、観測欠落、有限停止不成立はケースごとに停止条件とする。Windows新機能は対象外。

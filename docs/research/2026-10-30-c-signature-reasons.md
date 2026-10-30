# C署名の未読理由：実物確認

> 後続更新：末尾の「2型だけを採用」は監査 #3時点の判断。PR #40でユーザー承認により[固定4完全名の公開範囲を拡張](2026-10-30-c-atom-scope-expansion.md)した。[監査 #5の結果](2026-10-30-c-expanded-atoms-audit.md)を現在の状態として参照する。候補のassembly照合条件は変更していない。

2026-10-30、日本時間。main `94533150210b52075b4cca3f20b1726ec5faeb09` の[監査#2](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40976428615)は成功した。
8入力42811570 bytesのversion/hashが一致し、準備は6.167秒、workflowは29秒。取得対象や権限は変更していない。

GenerateMap、QueueLongEvent、DoThingFilterConfigWindow、MakeNewBill、TryExecuteの5メソッド群は、いずれも固定reason `unsupportedTypeAtom` だけが記録された。今回、invalidVisibility/invalidControlFlow/invalidCallsiteは検出されていない。初回summaryからの推測を、今回の理由分類で確認した。

静的結果はincomplete、C0はfalseのまま。未知型の完全名を公開summaryから確認したわけではない。

次の照合では候補をSystem.Action`1、System.Exception、System.Nullable`1、RimWorld.Bill、RimWorld.IncidentParms、Verse.ThingCategoryDefに固定する。Action/Exception/IncidentParmsは既存WorkerのAPI binding、BillはMakeNewBillの戻り型の候補、Nullable/ThingCategoryDefはフィルターAPIの調査候補であり、実DLLで確認済みとは扱わない。

照合は完全型名・assembly・generic arityを検査し、固定IDのみを記録する。参照元と定義元のmodule hashを確認し、定義欠落・重複・入替はmatchedにしない。候補一致だけでは型集合を自動追加しない。CoreLibは既存の固定8入力の一部をmetadataとして読むため、追加ダウンロードは不要。

## 候補照合の実物結果

[監査#3](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40977760070)（main17a0052）は33秒で成功。固定8入力のハッシュが一致し、billとincident-parmsの2候補がmatchedとなった。これは対象署名での使用とAssembly-CSharp内の定義・arityの一致を、固定入力hashに結合した結果である。

この2型だけを署名の公開atomへ追加する。他の4候補は公開atomへ追加しない。特に参照先assemblyの解決が確認できていないFramework型や未一致のフィルター型を、名前の推測だけで採用しない。候補の不一致は型が存在しない証明ではない。

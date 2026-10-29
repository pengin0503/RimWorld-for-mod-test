# C0 私有静的調査入口の設計案

2026-10-29。ユーザーは本設計に基づく実装を指示した。静的監査がC0の動的適格化を代替しないことは変わらない。
基準mainは `f223c514e4ee9c768cb0f819cfd8d9089e2450ff`。
[既存C0調査](../../research/c-reference-entrypoints.md)と[ケース別適格化計画](../plans/2026-10-29-c-independent-qualification.md)を補う。
この入口の完成はC0全体の通過やCの適格化を意味しない。

## 目的と範囲

対応ビルドの実DLLから、材料フィルターUIとイベント初期化のAPI署名・直接呼出関係を確認できるようにする。
Cloudflareコネクターで15,632,896 bytesのAssembly-CSharp.dll取得がメモリ上限に達したため、
既存のGitHub Actions上のR2 SDK取得を利用する。R2は読み取り専用、公開設定や認証権限を変更しない。

ゲームを起動せず、素材・Data・Workshop・索引を取得しない。Windows新機能、比較fixture、資格/cache変更は対象外。
DLLのAssembly.Load、Assembly.LoadFrom、Reflectionによるゲーム型の生成・メソッド呼出しを禁止する。
.NETのPEReader / System.Reflection.MetadataでPE・メタデータ・ILをデータとして読む。

静的調査が答えるのは、固定メソッドの存在・正確な署名・可視性・直接呼出位置まで。
実UIへの到達、実Gameの状態、キューの実行順序、報酬の観測、正常/不一致の判定感度は答えない。

## 方式の比較

| 案 | 利点 | 費用・制約 | 提案 |
|---|---|---|---|
| 専用main-only workflow | 静的調査の取得量と実ゲーム受入を分離。既存fixture入口を変えない | workflowを1件追加 | 推奨 |
| P2 registryへstatic-auditを追加 | 手動入口を共通化できる | 現在のneedsGame/Worker/Harmony分岐、allの意味、公開契約を変更する必要 | 初版では採らない案 |
| ローカル取得と手動解析 | runnerの運用追加が不要 | 現環境にDLL/SDK/資格情報がなく、コネクター取得も失敗 | 今回は成立しない |

以下は実装対象の専用main-only workflowを具体化した設計である。

## 処理の境界

1. **入口確認**：repository完全一致、ref=refs/heads/main、起動commitのcheckout一致、runId/attempt/commitを固定。入力はなし。固定C0調査だけを実行する。
2. **公開ツールのビルド**：Python3.12、.NET10、既存R2 SDKを準備し、ゲームを参照しないscannerを秘密なしでビルドする。
3. **私有資材の準備**：R2資格情報をこのstepだけへ渡す。checkout外のrun固有private directoryへ選定・取得・hash確認・manifest保存。ゲームは実行しない。
4. **静的解析**：資格情報を引き継がない子環境からscannerを有限実行する。生の解析結果・例外・パスは私有領域だけに置く。
5. **再検証した公開**：起動identity、入力hash、scannerの終了状態、出力schemaを再検証し、固定API項目だけをサマリーへ再構築する。

専用workflowは20分上限、scannerは120秒・合計RSS2GiB・ログ8MiBのポーリング監督を提案する。
プロセス回収は既存Linux pidfd/subreaperを再利用する。kernel I/Oで停止が遅れる限界とmemoryHard=falseを明記する。
成功・失敗時ともArtifacts/Cache/公開R2へ私有ファイルを保存しない。runner破棄後の永続性は保証しない。

## 取得する8ファイルと再利用

入力はvalidation_host.ADAPTERSの `rimworld-1.7.4985-rev1269` を唯一の期待値源とする。

| 対象 | 根拠 |
|---|---|
| Version.txt | 対応versionの完全一致（末尾改行のみ正規化） |
| Assembly-CSharp.dll、RimWorld.dll、Waylith.dll、UnityStubs.dll、Waylith.UnityCompat.dll | adapter.sha256の5件 |
| libcoreclr.so、System.Private.CoreLib.dll | Linux/waylithのruntimeSha256の2件 |

CLRファイルはビルド識別のために取得・hash確認するだけで、ロード・実行しない。
現行adapterに必要hashがない、またはfile集合が変わった場合は停止し、既存ビルドの期待値を黙って更新しない。
取得前に8つの完全キーを個別prefixで照会し、キー完全一致の項目だけ採用する。
`Game-Linux/`全件列挙・Data/素材の取得は行わない。duplicate、欠落、不正size、上限超過はGET開始前に停止する。
初版予算案は8ファイル・合計128MiB・1ファイル64MiBまで。実リストが予算を満たさなければ停止し、実装者判断で広げない。

既存snapshotが同じ環境にあれば、既存manifestの主張だけではなく各実ファイルのSHA256を再確認して再利用する。
再利用できる分は再取得しない。初版ではパスをworkflow入力にせず、既定private rootのgame-snapshot/gameだけを探索する。
symlink/checkout配下/期待外ファイルを解析対象にしない。取得後もmanifestへsize・SHA256・取得/再利用・時間を原子的に保存する。
途中失敗はverified=falseのまま残し、次回が古いverified=trueを流用しない。runの重複準備・重複実行も成功へ変換しない。

## 調査対象と出力

初版候補は以下の型・メソッド群。これは既存コード/過去調査の検索候補であり、今回のDLLで存在確認済みという意味ではない。

| 固定typeId | 型候補 | methodId候補 |
|---|---|---|
| game | Verse.Game | InitNewGame、FinalizeInit |
| map-generator | Verse.MapGenerator | GenerateMap |
| long-events | Verse.LongEventHandler | ExecuteWhenFinished、QueueLongEvent |
| bill-dialog | RimWorld.Dialog_BillConfig | DoIngredientConfigPane、get_HiddenSpecialThingFilters |
| filter-ui | Verse.ThingFilterUI | DoThingFilterConfigWindow |
| filter-listing | Verse.Listing_TreeThingFilter | .ctor、Visible |
| bill-factory | RimWorld.BillUtility | MakeNewBill |
| incident | RimWorld.IncidentWorker | TryExecute |
| dialog-choice | Verse.DiaOption | Activate |

検索は完全型名・完全method名。overloadは全件を保持し、最初の1件を勝手に採用しない。
型やmethodが不在ならmissingとし、似た名前・別namespaceへ自動で置き換えない。
識別できるcallback/closureの候補は私有解析へ残すが、名前だけから呼出時系列を断定しない。

私有出力は署名（戻り値、param型、generic、ref、static/instance、可視性）、IL offset付き直接call/callvirt/newobj、分岐と例外領域を保持する。
文字列リテラルや逆コンパイル本文を公開しない。間接call/delegate/外部methodの内部は未解決として明示する。
入力PEをロードしないため、悪意あるstatic constructorにも副作用を起こさせない。
破損PE、解釈不能なsignature/IL opcode、出力量超過は解析未完了として扱う。
初版の解析予算案は、対象method合計128件、1固定methodIdあたりoverload16件、1methodのIL64KiB、対象IL合計1MiB、命令10万件、callsite4096件。
署名はparameter64個、generic引数32個、型の再帰深度8まで。私有JSON4MiB、公開JSON512KiB、manifest64KiBを上限とする。
予算を超えたら切り詰めてcompletedにせず、budgetExceededとしてincompleteにする。
scannerは入力を読んだ同じbyte列でSHA256を計算してから解析し、hash確認後に別ファイルを開き直す方式を採らない。
結果には解析したhashと起動identityを結合し、publisherでも実ファイルのhashと照合する。これは同権限の悪意あるプロセスへのsandbox保証ではない。

公開schemaVersion=1の固定項目案：runId、commit、adapterId、binaryVerified、staticAuditStatus、c0Passed、types。
staticAuditStatusはcompleted/blocked/incompleteのみ。**c0Passedは常にfalse**。
types内は固定typeId/methodId、found/missing/unreadable、overload件数、正規化署名、固定対象間の直接呼出とoffsetのみ。
未登録名、例外本文、未知キー、私有パス、文字列リテラル、raw ILを出さない。
署名はscannerが返した文字列をそのまま転記せず、構造化した戻り値/parameter型/修飾をpublisherで検証・再構築する。正規化後の署名は1件2048文字まで。
型名はgrammar検査だけで許可しない。初版の固定type atomはSystemのprimitive型群、System.String/Object/Void、System.Action、System.Collections.Generic.List/IEnumerable、
表の対象型、および既存Workerが対応署名に使うVerse.ThingFilter/ThingDef/SpecialThingFilterDef/TreeNode_ThingCategory/RecipeDef/IntVec3/Map/MapGeneratorDef/GenStepWithParams、
RimWorld.QuickSearchFilter/Precept_ThingStyle、RimWorld.Planet.MapParent、UnityEngine.Rect/Vector2に限定する。
配列・generic構築・byref・pointer・generic parameterは、このatom集合と数値indexからのみ組み立てる。未知の型名は私有出力にだけ残し、公開はunreadableと不透明なmetadata tokenだけにする。
未知の型が見つかった場合は、固定された入力hash下のAPIであることを確認してから別の設計変更でatom集合を拡張する。自動追加しない。
不正enum、path文字、過長値、未登録type/method名、非有限数は拒否する。PRIVATE等の任意文字列を合法な型名の形にしても公開されない。
raw parser出力のcatは禁止。署名を安全に正規化できない場合、件数だけの成功へ劣化させず未完了とする。

## 判定とC0への持越し

binaryVerified=trueは固定8入力がversion/hash条件を満たしたことだけを表す。
staticAuditStatus=completedは、固定検索群を最後まで処理し、missingを含め結果を記録できたことだけを表す。
この両方がtrue/completeでも、公式APIが目的の文脈で動くことやCの資格を保証しない。

- 材料：fresh Game/new Billで実UIツリーへの到達と独立した表示/許可採取が証明できなければ停止。
- イベント：MapGenerator終了後のqueued処理とFinalizeInitの関係、同じfreshGeneratedMapでの独立delta採取が不明なら停止。
- どちらも例外、未分類診断差、観測欠落、有限停止不成立はケースごとの停止理由。片方の不成立で他方まで止めない。

## 必須検証と受入

| 境界 | 必須テスト |
|---|---|
| 取得 | 不正ref/repo/identityでR2接続0、完全8キー以外GET0、budget超過でGET0、size/hash/version不一致でverified=false |
| 再利用 | 正常snapshot再取得0、改変cache拒否、symlink拒否、途中失敗・重複・古いmanifestを成功にしない |
| 静的解析 | 自作PEのoverload/generic/ref/array/signatureとcall offsetが正確、文字列中のtokenをcallと誤認しない、破損/truncated/未知opcodeは未完了 |
| 非実行 | 自作PEのstatic constructorがファイル作成を試みても副作用0。Assembly.Loadを使わず読む |
| 公開 | PRIVATE文字列/私有パス/未知キー/古いidentity/不正enum/非有限数を混ぜても漏れず成功しない |
| 監督 | scannerにR2/GitHub tokenなし。timeout/cancel/ログ/RSS超過時に子孫回収、中断をcompleteにしない |

公開CIでは自作PEと偽R2のみを使用し、既存Python全suiteとWorker合成検査も通す。
ローカルPID/proc不一致やSDK欠落で実証できない項目はskipを証拠にせず、公開Linux CIの結果を使う。
実物受入は統合済みmainの手動実行1回。取得量記録、固定8入力のhash一致、対象APIの実際の署名/missing、秘密なし解析、再検証済み公開を確認する。
失敗時に別refへsecretを渡す・公開proxyを作る・R2権限を変える迂回は行わない。

## 実装の分割

実装単位は、(1)取得/manifest/publication境界、(2)PE metadata/IL scannerと自作PEテスト、(3)専用workflow接続とmain受入の3つ。
Python側は既存codex_workflow/private_validationの安全な資材・identity・Linux監督を再利用し、C# scannerはゲームDLLへのcompile-time参照も持たない。
ファイル候補はtools/private_static_audit.py、experiments/c-reference-audit/、tests/test_private_static_audit.py、tests/worker/CReferenceAudit/、.github/workflows/linux-private-c-audit.yml。
公開API契約の変更が必要になれば先に設計へ戻る。RED→GREEN実装手順は[実装計画](../plans/2026-10-29-private-static-c-audit.md)を参照。

128MiB予算・監督上限・公開範囲を実装条件とする。実物受入はmainへの統合後に実施し、静的結果だけで資格を更新しない。

## 設計確認の状態

設計提示後、ユーザーが実装と完了後のPRマージを指示した。
独立したbuilder checkは途中まで実施され、固定8入力とadapterの一致、非実行、C0=false、main限定の秘密境界は確認された。
確認担当が利用上限に達して終了したため、独立レビュー全体の完了とは扱わない。
その後、著者が解析予算、入力hashと解析byte列の結合、公開型名の固定許可集合を補足し、文書内の整合とリンクを自己点検した。

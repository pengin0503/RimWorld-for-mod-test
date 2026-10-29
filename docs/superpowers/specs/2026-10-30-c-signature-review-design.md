# C静的監査：未読理由の特定と署名型の追加設計

2026-10-30。設計・既存コードの合成検証まで。製品コードや公開型集合は変更していない。
基準main: `151368cb523cf4dcaf106d1b349d69618517d603`。
対象は[初回実物監査](../../research/2026-10-30-c-static-audit-main-acceptance.md)の未読署名。Windows、ゲーム実行、Cの資格更新は対象外。サブエージェントは使用していない。

## 検証で判明した前提の訂正

現行 `tools/private_static_audit.py:public_summary` は、署名型・可視性・metadata token・分岐/例外領域・呼出情報の検査で起きたValueError/TypeErrorを、同じunreadableへ集約する。したがって、初回summaryのunreadableだけから「許可外の型が原因」とは確定できない。5メソッド群の原因と未知型の正確な名前は未確認であり、現時点で追加を承認できる型は0件である。

mainから取得した関数と定数をASTで抽出し、ゲームを使わない合成入力を同じpublic_summaryへ渡した。

| 入力 | staticAuditStatus | method状態 |
|---|---|---|
| 許可済みVoidの正常署名 | completed | found |
| Synthetic.Unknownという未知型 | incomplete | unreadable |
| 不正visibility | incomplete | unreadable |
| 余分なキーのあるbranch | incomplete | unreadable |

正常対照を含む4ケースは上表どおりだった。これは失敗原因の集約を実証する検証であり、実DLLの未知型を確認した証拠ではない。R2への追加GETは0件。

## 選択肢と提案

- namespaceをまとめて許可する案：任意の名前を公開できるため採らない。
- Workerの反射名を一括追加する案：必要性と実DLLでの一致を証明できず、型以外の不正を解消しないため採らない。
- **未読理由を分離し、固定候補と固定バイナリの証拠を照合する案を提案する。** 公開集合の追加は個別の証拠が揃った後に限る。この選択は著者の提案で、実装済み・承認済みとは扱わない。

## 第1段階：原因を区別する

publisherの検査を小さな検査単位に分け、固定enumだけを記録する。
`unsupportedTypeAtom`、`unsupportedTypeForm`、`invalidSignature`、`invalidVisibility`、
`invalidMethodToken`、`invalidControlFlow`、`invalidCallsite`、`invalidSchema`、
`budgetExceeded`、`identityMismatch`、`interrupted`。
複数理由は集合として保持し、ひとつ直っただけで成功へ変更しない。自由形式の例外や型名は公開しない。想定外の例外も固定のinvalidEvidence扱いで未完了にする。

証拠の単位は「adapter、入力DLLのSHA256、固定assembly ID、型/メソッドID、MethodDef token、署名内の位置」。
metadata token単独ではDLLをまたいで一意にならないため、必ずmoduleのhashと組にする。
署名位置はreturnまたはparameter indexと、深さ制限内の構造indexだけとする。

実物再実行時にこの理由分類を確認するまで、5メソッド群の停止理由を未知型と断定しない。

## 第2段階：候補を絞って照合する

既存Workerが使うAPI名と公式型の参照から候補表を設計レビューする。候補表は固定IDと完全型名、generic arity、許可する参照先assemblyを持つ。今回、具体的な候補型は採用しない。

scannerはhashを確認した同一byte列のmetadataから、候補名との完全一致とTypeDef/TypeRefの解決先を確認する。AssemblyRefや型のkind、generic arityを含めて照合し、名前だけの一致や同名の別assemblyを採用しない。未解決・外部転送・複数候補は保留とする。
namespaceの前方一致、型名の自動採用、未知名のhashや自由文字列による公開は行わない。
公開は事前にレビューした候補ID、一致/不一致、固定位置情報だけ。未知名・パス・literal・raw IL・例外は私有領域に留める。

私有の既存解析結果が同じ環境に残っている場合は入力hashを再確認して再利用する。既に破棄されたGitHub runnerのファイルが残っているとは扱わない。
再取得が必要なら既存main限定入口の固定8入力と予算を維持し、全Game-Linux列挙や素材取得を行わない。
R2権限の拡大、公開proxy、branchへのsecret付与、Artifactsへの私有結果保存はしない。

## 型追加の決定表

型を追加できるのは、次がすべて成立した場合だけ。

1. 固定ビルドの8入力が検証され、調査対象moduleのhashが証拠に結合している。
2. 原因がunsupportedTypeAtomと確認でき、他の不正理由が解消または独立に保留されている。
3. 完全型名・参照先assembly・generic arityが候補表と一致し、対象署名のどこに必要か明示できる。
4. 名前を公開する必要があり、私有文字列や利用者データを含まないことをレビューできる。
5. 追加するatomを個別列挙し、正常・偽装・境界・回帰テストが通る。

未知の構文形やmodifierが原因なら、atom追加で迂回せず署名表現の別設計へ戻る。
公開集合は別PRで最小限だけ変更し、取得元hashの更新を同時に紛れ込ませない。

## 実装後に必須の検証

| 境界 | 試験と期待結果 |
|---|---|
| 原因分類 | 上表の4ケースが別の固定reasonになる。混在時は全理由を保持する |
| 誤採用 | 同名別assembly、namespace近似、nested型、arity違い、type forwarding、未解決参照を拒否 |
| 構造 | primitive、generic、array、byref、pointer、generic parameterの正常値と深さ8/parameter64/generic32の境界 |
| 証拠 | DLL/tokenの入替、stale run、hash不一致、重複候補、重複実行を未完了にする |
| 秘密境界 | PRIVATE、私有パス、literal、未知キー、不正enum、非有限数を混ぜても公開せず、成功にしない |
| 有限性 | 既存の時間120秒、RSS2GiBのポーリング、ログ8MiB、私有JSON4MiB、公開512KiBを維持 |
| 非実行 | 合成PEのstatic constructorに副作用がない。ゲーム型のロード・生成・実行をしない |
| 回帰 | 既存Python全suiteと合成PEを公開CIで実行。既読署名の結果を維持する |
| 実物 | 統合済みmainで理由分類と候補一致を確認。実物未実行を合成成功で代替しない |

## 完了の意味と停止条件

第1段階の完了は未読理由を特定できたこと、第2段階の完了は個別候補の証拠を確認できたことを意味する。どちらもC0の通過ではない。
静的署名が全件読めても、材料はfresh Game/new Billでの実ツリー到達と独立した表示/許可採取、イベントはqueued処理とFinalizeInitの関係と同一freshGeneratedMapでの独立delta採取が必要。
例外、未分類診断差、観測欠落、有限停止不成立はケース別の停止条件を維持する。`c0Passed=false` とexperimentalの資格は変更しない。

## 検証状況

既存コードの4ケース再現と設計の境界照合は実施済み。新しいreason enum、候補照合、型追加、実DLLによる原因特定は未実装・未検証。実装は本設計の確認後に別計画を作成する。

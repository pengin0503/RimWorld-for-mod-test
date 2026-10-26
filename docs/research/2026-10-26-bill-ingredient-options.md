# C：新規 Bill の材料候補・許可状態の実装記録

日付：2026-10-26。ケース `bill-ingredient-options.v1`。ユーザー承認済みの Linux 非描画設計を実装。**ケース適格化は未完了。自作 fixture の観測であり、小麦粉 MOD 本体の C 合格ではない。**

## 検査方法

既存の Linux x86_64、RimWorld 1.7.4985 rev1269、同梱 WaylithClr 10.0.13-waylithclr.dev のゲームスナップショットを再利用。ゲーム/Workshop の追加取得は 0 ファイル。R2 上の変更なし。公開ソースは自作 fixture とホストだけ。

Worker の A ロード完了後、検査中だけ新規 Game を作り、ロード済み RecipeDef から実 `BillUtility.MakeNewBill` を呼ぶ。UI と同じ親フィルターの表示 root と実 Listing_TreeThingFilter を構築し、カテゴリ/材料の実表示判定、初期の発見状態、Bill の実許可状態を読む。Def の追加・書換え、許可の強制変更、UI の stub、描画、ワールド、マップ、ゲーム開始、tick、セーブはない。Current.Game は finally で復元する。GameComponent コンストラクターは通るので、そこで起こる診断も比較対象になる。

この新規 Game はロード後のホスト文脈内にあり、プレイ中のセーブの状態は再現しない。GameComponent の開始処理やマップに依存する MOD はこのケースの対象外で、観測不能なら incomplete。描画コールバックでだけ項目を隠す処理も対象外。

Controller は Worker の match をそのまま信用せず、ケース/期待値の同一性・観測数・必須真偽値・成分整合性を確認して visible/allowed を比較する。false 期待値でも pane 非対象・カテゴリ欠落・Def 欠損を合格にしない。必要 API の不足は C を blocked とし、実行済みの A の観測を残す。

## 自作 fixture での実ゲーム観測

`tests/fixtures/validation-mods/billingredients` を `tests/integration/run_bill_ingredients.py` で読み込む。公開 CI ではゲーム資材を使わない。全ケースの Worker と baseline は有限終了した。

| ケース | 実測 | C 観測段階 / 全体 |
|---|---|---|
| 通常の材料 | 自作の Plant 型の穀物が visible=true / allowed=true | completed / incomplete |
| 候補だが未許可 | RawCorn が visible=true / allowed=false | completed / incomplete |
| 親の制約で対象外 | 同じ表示ツリー内の RawPotatoes が visible=false / allowed=false | completed / incomplete |
| 特殊フィルターで非表示（正しい false 期待値） | 親 Allows=true、specialFilterDisallows=true、visible=false / allowed=true | completed / incomplete |
| 上の故障に visible=true を要求 | 表示候補の不一致を `billIngredientMismatch` として検出 | failed / incomplete |
| 全材料が固定のレシピに false 期待値 | `paneNotEditable`、不正な文脈で false 合格にしない | incomplete / incomplete |
| 表示 root の外にある Steel に false 期待値 | `categoryMissing`、構造的に到達不能 | incomplete / incomplete |
| 未定義材料 / 未定義レシピ | それぞれ `defMissing`、不明を false に変換しない | incomplete / incomplete |

全体は `executionStatus=completed`、`fidelity=experimental`、`status=incomplete`。`experimental` と `cNotQualified` を明示。不一致ケースでも未適格な全体を failed と断定しない。6 要求（正常要求に 4 観測）で期待した成分と状態ガードを確認し、新規 error/warning・baselineIncomplete・checkError は 0。

初期テストで必要な API の型名誤りを検出し、実 DLL の型一覧で確認して修正した。また既存 RawRice は特殊フィルター故障の Plant 型入力ではなかったため、実ゲームの型判定を調べ、自作のロード済み Plant 型 ThingDef を fixture に定義した。カテゴリ未設定も categoryMissing として検出し、fixture に明示した。検査対象の Def を実行後に書き換えて期待値に合わせる処理は追加していない。

## 残る作業

- 独立した参照経路での比較とケース固有の資格判定。既存 A/B・マップの qualified を流用しない。
- ユーザーの `rimworld-VCE-Flour-Patch` 本体を使う検証。索引に当該自作 MOD の一致は未確認なので、ソース About とビルド入力の同一性を確認し、依存 Workshop MOD は正規索引→R2 の必要範囲で取得する。今回自作 fixture を本体の成功へ読み替えない。
- Windows での実画面描画、既存 Bill 移行、実際のクラフト、イベント/クエストは別範囲。

実装計画：[bill-ingredient-options](../superpowers/plans/2026-10-26-bill-ingredient-options.md)。要求・結果：[C の契約](../contracts/mod-validation-v1.md#c製造指示の材料候補非描画experimental)。

# 実際の MOD での検証（Harmony、Vanilla Expanded Framework）

実施日：2026-10-25。環境：Claude のクラウド Linux x86_64 コンテナ、RimWorld Linux 1.7.4985 rev1269、WaylithClr 10.0.13、本ブランチの Worker。入力：ユーザーから受け取った MOD の ZIP 2 個。MOD 本体、ゲームファイル、生ログは公開リポジトリに入れていません。

| MOD | packageId | 版 | 中身 |
|---|---|---|---|
| Harmony | `brrainz.harmony` | Harmony Mod 3.0.1.0、0Harmony 3.0.0.0-rc.3 | 1.7 用 DLL 2 個 |
| Vanilla Expanded Framework（VEF） | `OskarPotocki.VanillaFactionsExpanded.Core` | 1.7 対応版 | 1.7 用 DLL 8 個、Defs、Patches、English。`brrainz.harmony` に依存 |

## 結果

全て `fidelity=qualified`（Linux x64＋WaylithClr＋対応ビルドの A/B）。B の期待パッチは、MOD の DLL を逆コンパイルして `[HarmonyPatch]` 属性と Harmony ID を読み、実行前に書きました。実行結果から写したものではありません。

| ケース | 構成 | 判定 | 内容 |
|---|---|---|---|
| harmony-core | Core＋Harmony（対象） | passed | 新しい診断なし。期待パッチ 2 件が登録済み。登録は全部で 3 件 |
| vef-core | Core＋Harmony＋VEF（対象） | passed | 新しい診断なし。Def 4 件が期待どおり。MayRequire 付きの 2 件は DLC がないため存在しない。期待パッチ 3 件が登録済み。登録は全部で 410 件（prefix 111、postfix 225、transpiler 65、finalizer 9） |
| vef-alldlc-en | Core＋4 DLC＋Harmony＋VEF、英語 | passed | MayRequire の Def も存在 |
| vef-alldlc-ja | 同上、日本語 | **failed**（newWarnings） | 警告「Translation data for language Japanese has 31 errors」が出る。ベースラインでは 28 件で、VEF により 3 件増えた（下記） |
| vef-no-harmony-A | Core＋VEF だけ（A） | failed | loadException（`HarmonyLib.HarmonyPatch` を読み込めない）、playDataNotLoaded、新しいエラー 787 件 |
| vef-before-harmony | VEF を Harmony より前に置く（A） | failed | 上と同じ種類の失敗 |
| vef-badref | VEF のコピーで StatDef の category を存在しない名前に変更 | failed（newErrors） | `Could not resolve cross-reference: No RimWorld.StatCategoryDef named RWMT_NoSuchStatCategory ...` |
| vef-badpatch | VEF のコピーで Biotech 用パッチの XPath を存在しない Def に変更（全 DLC） | failed（newErrors） | `[Vanilla Expanded Framework] Patch operation Verse.PatchOperationFindMod(Biotech) failed` |

### 日本語で増える翻訳エラー 3 件

Worker は今回から、ゲームが件数しか出さない翻訳エラーの中身を `diagnostics.translationErrors` に記録します。増えた 3 件は次のとおりです。

- `Couldn't inject Blackboard.comps.CompInspectStringBlackboard.inspectString into Verse.ThingDef (Buildings_Furniture.xml): None of the list elements have a handle named CompInspectStringBlackboard.`
- `Couldn't inject SchoolDesk.comps.CompStatEntrySchoolDesk.reportText ...`
- `Couldn't inject SchoolDesk.comps.CompStatEntrySchoolDesk.statLabel ...`

原因は VEF の `1.7/Patches/Biotech/LearningBonusPatches.xml` です。黒板と学校机から統計表示の comp を意図的に削除し、独自の StatDef に置き換えています。そのため、公式の日本語翻訳がその comp に書く文字列は、注入先がなくなります。ゲームの動作を壊すものではなく、VEF の設計による結果です。ただしログには警告が出るので、現在の判定規則（新しい警告は failed）では failed になります。要求の `allow.translationErrors` に、この 3 件に一致する正規表現と理由を書くと、件数の警告は判定から外れます。配布された ZIP 2 個を `mods[].path` に直接指定した構成で、passed（`allowedInTarget: 1`）になることを確認しました。展開後の内容 sha256 は、手作業で展開したフォルダと一致しています。ほかの翻訳エラーが 1 件でも増えれば、警告は外れず failed のままです。

## 公式 headless との突き合わせ（開発用）

`experiments/official-comparison/compare_official.py --request NAME=request.json` で、同じ要求を公式実行ファイルの headless 起動（`-headless -QuitAfterBoot`）でも実行しました。比較用のプローブ MOD を最後に足し、エラー/警告とプローブの出力（MOD 順序、言語、Def の値、Harmony の全登録と効果）を比べています。製品はこのスクリプトを使いません。

- harmony-core、vef-core、vef-alldlc-ja、vef-alldlc-en、vef-badref、vef-badpatch の 6 ケース：エラー/警告とプローブの出力が全て一致しました。VEF の 410 件の Harmony 登録も一致しています。
- vef-no-harmony-A と vef-before-harmony：公式の起動は読み込みに失敗した後、メインメニューの初期化で NullReferenceException を出し、毎フレーム同じエラーを出し続けて終了しませんでした（90 秒で強制終了）。Worker は 5 秒前後で failed を返して終了します。比較できるのは異なる行の集合だけです。Worker が出した 104 種類の行は、全て公式の側にも出ていました。公式だけに出たのは、Worker が実行しないメインメニュー段階の行（メインメニュー初期化の例外、DefOf の未初期化警告、ログ上限の警告）です。

## 時間（warm キャッシュ、参考値）

| ケース | Worker（対象）1 回 | 公式 headless 1 回 |
|---|---|---|
| harmony-core | 9.6 秒 | 9.4 秒 |
| vef-core | 12.5 秒 | 12.3 秒 |
| vef-alldlc-en | 15.7 秒 | 15.6 秒 |
| vef-alldlc-ja | 18.5 秒 | 18.1 秒 |

ベースラインを含む 1 回の `run` は、キャッシュなしで全 DLC 日本語が約 36 秒、キャッシュありで Core＋VEF が約 13 秒でした。しばらく使わなかった後の最初の実行は、ファイルキャッシュが冷えていたためか 2〜3 倍かかりました（例：ベースライン 35 秒）。

## 未確認

- Harmony パッチの実行時の効果。登録は確認しましたが、transpiler 65 件が書き換えたメソッドを実際に呼んではいません（C は未実装）。プローブで効果を見たのは自作 fixture のパッチだけです。
- マップ、tick、UI、セーブを使う VEF の機能。
- Anomaly を含む構成（スナップショットにない）、ほかの言語、Windows。
- VEF に依存する個々の Vanilla Expanded MOD。

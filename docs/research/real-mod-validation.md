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
| vef-alldlc-ja | 同上、日本語 | **failed**（当初は newWarnings、翻訳エラーを 1 件ずつ判定するようにした後は newTranslationErrors） | 警告「Translation data for language Japanese has 31 errors」が出る。ベースラインでは 28 件で、VEF により 3 件増えた（下記） |
| vef-no-harmony-A | Core＋VEF だけ（A） | failed | loadException（`HarmonyLib.HarmonyPatch` を読み込めない）、playDataNotLoaded、新しいエラー 787 件 |
| vef-before-harmony | VEF を Harmony より前に置く（A） | failed | 上と同じ種類の失敗 |
| vef-badref | VEF のコピーで StatDef の category を存在しない名前に変更 | failed（newErrors） | `Could not resolve cross-reference: No RimWorld.StatCategoryDef named RWMT_NoSuchStatCategory ...` |
| vef-badpatch | VEF のコピーで Biotech 用パッチの XPath を存在しない Def に変更（全 DLC） | failed（newErrors） | `[Vanilla Expanded Framework] Patch operation Verse.PatchOperationFindMod(Biotech) failed` |

### 日本語で増える翻訳エラー 3 件

Worker は今回から、ゲームが件数しか出さない翻訳エラーの中身を `diagnostics.translationErrors` に記録します。増えた 3 件は次のとおりです。

- `Couldn't inject Blackboard.comps.CompInspectStringBlackboard.inspectString into Verse.ThingDef (Buildings_Furniture.xml): None of the list elements have a handle named CompInspectStringBlackboard.`
- `Couldn't inject SchoolDesk.comps.CompStatEntrySchoolDesk.reportText ...`
- `Couldn't inject SchoolDesk.comps.CompStatEntrySchoolDesk.statLabel ...`

原因は VEF の `1.7/Patches/Biotech/LearningBonusPatches.xml` です。黒板と学校机から統計表示の comp を意図的に削除し、独自の StatDef に置き換えています。そのため、公式の日本語翻訳がその comp に書く文字列は、注入先がなくなります。ゲームの動作を壊すものではなく、VEF の設計による結果です。ただし新しい翻訳エラーなので、既定では failed（`newTranslationErrors`）です。要求の `allow.translationErrors` に、この 3 件に一致する正規表現と理由を書くと、判定から外れます。配布された ZIP 2 個を `mods[].path` に直接指定した構成で、許可規則なしは failed、ありは passed になることを確認しました。展開後の内容 sha256 は、手作業で展開したフォルダと一致しています。ほかの翻訳エラーが 1 件でも増えれば failed のままです。

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

## 2026-10-26：索引から選んだ MOD（Vanilla Psycasts Expanded、TD Enhancement Pack）

ゲームファイルは Cloudflare R2 の `Game-Linux/`、MOD は `Workshop/<ID>/` から必要な分だけ取得しました（各 MOD の 1.7 以外の版フォルダ、`Source/`、.git は除外）。MOD はユーザーが作った MOD 索引で選びました。

| MOD | Workshop ID | packageId | 依存 | 中身 |
|---|---|---|---|---|
| Harmony | 2009463077 | `brrainz.harmony` | — | 0Harmony 3.0.0.0 |
| Vanilla Expanded Framework | 2023507013 | `OskarPotocki.VanillaFactionsExpanded.Core` | Harmony | 1.7 用 DLL 8 個 |
| Vanilla Psycasts Expanded（VPE） | 2842502659 | `VanillaExpanded.VPsycastsE` | Harmony、Royalty、VEF | 1.7 用 DLL 1 個、Defs、テクスチャ・音 |
| TD Enhancement Pack - Continued | 3525414162 | `MemeGoddess.TDPack` | Harmony | 1.7 用 DLL 1 個 |

選んだ理由：VPE は VEF に依存する VE の大型 MOD。TD Enhancement Pack は索引の 1.7 対応 MOD の DLL で transpiler の多いものを調べて選んだ（`[HarmonyPatch]` 付きのクラス 102 個、transpiler 25 個）。B の期待パッチは、DLL を逆コンパイルして属性と Harmony ID を読み、実行前に書きました（VPE：postfix・transpiler・prefix 各 1、TD：transpiler 3）。

| ケース | 構成 | 判定 | 内容 |
|---|---|---|---|
| vpe-royalty | Core＋Royalty＋Harmony＋VEF＋VPE（A/B） | passed | 新しい診断なし。期待パッチ 3 件が登録済み。VPE の登録は全部で 86 件（transpiler 12） |
| vpe-alldlc-en | Core＋4 DLC、英語（A/B） | passed | 同上 |
| vpe-alldlc-ja | Core＋4 DLC、日本語（A） | passed | 新しい翻訳エラーなし |
| tdp-core | Core＋Harmony＋TD（A/B） | passed | 期待パッチ 3 件が登録済み。TD の登録は全部で 180 件（transpiler 27） |
| tdp-alldlc-en | Core＋4 DLC、英語（A/B） | passed | 同上 |
| tdp-alldlc-ja | Core＋4 DLC、日本語（A） | passed | 新しい翻訳エラーなし |
| vpe-map / tdp-map | 上の構成で `map` を追加 | 問題なし（当時は map 未適格のため incomplete/`mapNotQualified` だけ） | マップ生成中の新しいエラー・警告なし。どちらの MOD も生成時にマップへ物を置かない |

公式 headless との突き合わせ（`compare_official.py --request`）：vpe-alldlc-en、vpe-alldlc-ja、tdp-alldlc-en、tdp-alldlc-ja の 4 ケースで、エラー/警告とプローブの出力（MOD 順序、言語、Harmony の全登録と効果）が全て一致しました。

この 2 つの MOD では問題は見つかりませんでした。ただし確かめたのは読み込み・パッチの登録・マップ生成までで、transpiler が書き換えたメソッドを実際に呼んだわけではありません（C は未実装）。

## 未確認

- Harmony パッチの実行時の効果。登録は確認しましたが、transpiler 65 件が書き換えたメソッドを実際に呼んではいません（C は未実装）。プローブで効果を見たのは自作 fixture のパッチだけです。
- マップ、tick、UI、セーブを使う VEF の機能。
- Anomaly を含む構成（スナップショットにない）、ほかの言語、Windows。
- VPE 以外の、VEF に依存する個々の Vanilla Expanded MOD。

# C：小麦粉 MOD 本体での材料表示判定

日付：2026-10-26。ケース `bill-ingredient-options.v1`。対象はユーザー自作の [rimworld-VCE-Flour-Patch](https://github.com/pengin0503/rimworld-VCE-Flour-Patch)（packageId `pengin0503.vce.flouralternatives`）。**C のケース適格化はまだ。全体は `experimental` / `incomplete`（`cNotQualified`）のままで、下の結果は観測記録。**

## 目的

この MOD では、焼き料理の材料設定から粉が消える不具合が実際に起きた（MOD リポジトリの `docs/WORK_LOG.md`、2026-10-24「焼き料理の材料設定から粉が消える問題」）。原因は、3 種類の粉が `foodType=Plant` を継承し、VCE の焼き料理の `fixedIngredientFilter` が特殊フィルター `AllowPlantFood` を禁止していたため。修正は v0.1.0-beta.2（`be3c29e`）で入り、正式版 v0.1.0 はユーザーのゲーム内確認を受けて公開された。

不具合版と修正版を同じ C ケースにかけ、人がゲーム画面で見た結果と同じ向きに分かれるかを確かめる。

## 構成

- Linux x64、RimWorld 1.7.4985 rev1269、同梱 WaylithClr。ゲームは R2 の `Game-Linux/` から取得（2,572 ファイル）。Core のみ、English、レベル A と C。
- 依存は正規索引で選び R2 から限定取得：Harmony（2009463077、ロードフォルダ `1.7`→root）、Vanilla Expanded Framework（2023507013、`1.7`→root）、Vanilla Cooking Expanded（2134308519、`1.6`→root。R2 の版には 1.7 フォルダがなく、ゲームの規則どおり 1.6 を選ぶ）。
- 小麦粉 MOD は `codex_workflow.py fetch-mods --local-target` で対象にした（R2 にも索引にもないため）。各版を MOD リポジトリの csproj で `RimWorldVersion=1.7` としてビルドし、配布 ZIP と同じ構成（About・Defs・Patches・Textures・Languages・loadFolders.xml・`1.7/Assemblies`）に並べた。

| 版 | コミット | DLL sha256（先頭 12 桁） |
|---|---|---|
| 不具合版（#1 マージ後、修正前） | `28cb8e5` | `4ff1db0c8d63` |
| v0.1.0（ユーザーがゲーム内で確認） | `54767b2` | `e168d72e0d1e` |
| main（v0.2.0 開発中） | `19c62d7` | `f6df1fabfd65` |

期待値は 3 版とも同じ「あるべき姿」：VCE の焼き料理 7 レシピ（`VCE_CookBakeSimple` / `…SimpleBulk` / `…Fine` / `…FineBulk` / `…Lavish` / `…LavishBulk` / `…Gourmet`）× 粉 3 種（`VCE_Flour`、`PFA_RiceFlour`、`PFA_Cornmeal`）の 21 組で `visible=true`、`allowed=true`。

## 結果

| 版 | C 段階 | 21 組の観測 | 新規 error/warning | 実ロード |
|---|---|---|---|---|
| 不具合版 | failed（`billIngredientMismatch`） | 全組 `visible=false`、`allowed=true`。理由は `specialFilterDisallows`・`itemNotVisible`・`categoryNotVisible` | 0 | 順序一致、Def 4 件 |
| v0.1.0 | completed | 全組 `visible=true`、`allowed=true` | 0 | 順序一致、Def 7 件 |
| main | completed | 全組 `visible=true`、`allowed=true` | 0 | 順序一致、Def 7 件 |

全体はどれも `status=incomplete`、`executionStatus=completed`、理由は `experimental` と `cNotQualified`（不具合版は加えて `billIngredientMismatch`）。A と C を同時に要求すると、適格化済みの範囲（A/B）を超えるため実行全体が `experimental` になる。各 MOD の実ロードフォルダは計画（`expectedLoadFolders`）と一致した。

不具合版では、Bill の許可状態（`allowed`）は true のままで、表示判定だけが false になった。これは「材料として許可されているのに一覧に出ない」という当時の症状と同じ形で、原因の特殊フィルターも観測値に出ている。

同じ構成で main を A だけで実行すると `passed` / `completed` / `qualified`、新規 error/warning 0。要求の小麦粉 MOD の `expectedLoadFolders` を故意に `["1.6", ""]` へ変えると、実ロード `["1.7", ""]` との差で `loadFolderMismatch` の incomplete になった（実ゲームでの照合の確認）。

## 分かったことと分からないこと

- 人がゲーム画面で見た 2 つの結果（修正前は粉が消える、v0.1.0 では出る）と、C の判定が同じ向きに分かれた。実 MOD で C が既知の不具合を検出し、修正後に検出しないことを示す最初の記録になる。
- これだけでは C の適格化にはならない。比べたのは過去の人の報告で、同じビルド・同じ条件で画面を描画して比べたものではない（不具合を見たときの正確なビルドは記録にない）。描画結果との比較は Windows 版で行う予定。
- 対象は 7 レシピ × 3 種の新規 Bill だけ。既存セーブの Bill（v0.2.0 の移行処理）、製粉レシピ、実際の調理、日本語、ほかの DLC 構成は確かめていない。
- Linux での結果は Windows での動作を保証しない。

# マップ生成の適格化（公式 quick test との比較）

実施日：2026-10-26。環境：Claude のクラウド Linux x86_64 コンテナ、RimWorld Linux 1.7.4985 rev1269（Cloudflare R2 の `Game-Linux/` から取得）、同梱 WaylithClr 10.0.13、本ブランチの Worker。ゲームファイル、生ログ、逆コンパイル本文は公開リポジトリに入れていません。

## 結論

- Linux x64＋WaylithClr＋1.7.4985 rev1269 で、`map` を `qualified.features` に加えました。`map` を付けた実行は、問題がなければ `passed` になります（以前は常に `incomplete`／`mapNotQualified`）。
- **このビルドのマップ生成は、同じ種でも実行のたびに少しずつ違うマップになります。公式の `-headless -quicktest` でも同じです。** そのため、当初の計画（地形・屋根・物の一覧のハッシュを公式と完全一致させる）は原理的に成立しません。代わりに、製品と公式を各 5 回ずつ動かし、設定・エラー・個数の分布を比べました。4 ケース全てで、製品は公式のばらつきの範囲に収まりました。
- この比較で言えるのは「公式と同じ手順で、同じ種類と量の物・地形ができ、同じエラーが出る」ことです。セル単位で同じマップになることは、公式自身が満たさないので確かめようがありません。

## 実ゲームで最初に動かしたときに直したこと

PR #6 の時点ではゲームファイルで一度も動かしていませんでした。実際に動かすと、次の 3 か所で止まりました。公式の Play シーンが用意する物を、Worker が持っていなかったためです。

| 止まった場所 | 原因 | 対応 |
|---|---|---|
| `World.FinalizeInit` → `AmbientSoundManager` → `Find.SoundRoot` | `Current.Root` がない | `Start` を呼ばない `Root_Play` を作り、`SoundRoot` と `MusicManagerPlay` だけを持たせる |
| `SoundRoot` → `AudioSourcePoolCamera` | `Find.Camera` がない | Play シーンと同じ `Camera`（Camera＋AudioListener）のオブジェクトを作る。`CameraDriver` は付けない |
| `MapGenerator.GenerateMap` → `Game.AddMap` → `Find.ColonistBar` | `UIRoot_Play` がない | `UIRoot_Play` を作るだけで `Init` も描画もしない |

さらに、Worker が生成後に `Game.CurrentMap` を設定していた処理を外しました。この設定はカメラと UI を動かす（`MapInterface.Notify_SwitchedMap` → `Find.CameraDriver`）うえ、公式は `Game.FinalizeInit` の後でしか設定しません。マップ段は `FinalizeInit` を実行しないので、設定しないのが公式の順序どおりです。

これらは結果の `map.skippedOfficialSteps` に書いてあります。

## 生成が毎回違うこと

同じ要求（種 `rwmt`、タイル 85560、AridShrubland、250×250、Base_Player）で、製品も公式も 5 回とも地形・屋根・物の一覧のハッシュが全て異なりました（下表の「異なる指紋」）。ワールドとタイルは毎回同じで、違いは地形で数百セル、物で数百個の規模です（遺跡の床に使われる石の種類、古代の祭壇の中身、動物の群れの位置など）。

原因は確かめていません。有力な候補は .NET の文字列ハッシュの無作為化です。`Def.GetHashCode()` は `defName.GetHashCode()` で、.NET（WaylithClr を含む）ではプロセスごとに値が変わります。Def を鍵にしたハッシュ集合の列挙順が実行ごとに変わり、同じ乱数列でも違う物に使われる、という仕組みが考えられます。

製品にとっての意味：

- 対象 MOD を入れたマップ（`map.png`）とベースライン（`map-baseline.png`）は、それぞれ 1 回分の標本です。MOD と関係のない場所も違って見えます。結果の `map.variation` にこの注意を書きました。
- `mapThings` の個数の範囲（`minCount`／`maxCount`）は、MOD 自身が必ず置く物には安定して使えます。ランダムに置かれる物の正確な個数は、実行ごとに変わり得ます。
- マップ生成中のエラー・警告は、ベースラインとの差分で判定します。今回の公式 20 回・製品 20 回では、エラー・警告は全ての実行で同じでした。ランダムにしか出ない警告があれば、実行によって `newWarnings` になる可能性はあります。

## 比較の方法

`experiments/official-comparison/compare_official.py --map --repeat 5`（開発専用。製品は使いません）。1 ケースにつき次を 5 回繰り返します。

1. 製品の `run`（ベースラインはキャッシュ）。
2. 同じ MOD 構成で、公式実行ファイルを `-headless -QuitAfterBoot -quicktest` で起動。`mapprobe` fixture が公式側のワールドの種を製品の既定値（`rwmt`）に揃え、乱数の状態も製品と同じにします。

両方で `mapprobe` が生成直後のマップについて記録した行を比べます。

| 比べるもの | 基準 |
|---|---|
| 設定（ワールドの種・被覆率・タイル・バイオーム・サイズ・MapGeneratorDef、MOD の順序） | 全 10 回で同一 |
| マップ生成の終わりまでのエラー・警告 | 全 10 回で同一（既知のエンジンノイズを除く。下記） |
| 個数（物の総数、カテゴリ別の数、ThingDef 別の数、TerrainDef 別のセル数、屋根のあるセル数） | 製品 5 回の中央値が、公式 5 回の最小〜最大を許容幅だけ広げた範囲に入る。許容幅は公式の幅そのもの（最低でも平均の 2 % と 2） |

一部の実行にしか現れない種類（例：遺跡の床がたまたまその石だった）は、5 回では「まれ」と「ない」を区別できないので個別には判定せず、種類ごとの合計（例：`terrain-cells (sum of intermittent kinds)`）を判定します。一方の全ての実行にあり、他方には全くない種類は必ず判定します。

### 方法の感度

この基準で差を見逃さないかを、ケースを入れ替えて確かめました。`mapstructure`（GenStep で RWMT_Monolith を 4 個置く）の製品 5 回を、`okxml`（置かない）の公式 5 回と比べると、`thing-count RWMT_Monolith`（4 個 対 0 個）で「範囲外」になります。逆の組み合わせも同じです。最初の版はカテゴリ別の数しか見ておらず、この差を検出できませんでした。ThingDef 別の数を加えたのはそのためです。

## 結果

| ケース | 構成 | 設定 | エラー | 判定した個数 / 全個数 | 範囲外 | 異なる指紋（製品/公式） | 判定 |
|---|---|---|---|---|---|---|---|
| map-core | Core＋okxml | 同一 | 同一 | 65 / 103 | なし | 5/5 | 同等 |
| map-structure | Core＋mapstructure | 同一 | 同一 | 68 / 97 | なし | 5/5 | 同等 |
| map-genstep-throws | Core＋mapgenthrow（GenStep が例外） | 同一 | 同一（`Error in GenStep: ... failed on purpose` が両方に毎回） | 67 / 99 | なし | 5/5 | 同等 |
| map-all-dlc | Core＋4 DLC＋mapstructure | 同一 | 同一 | 94 / 130 | なし | 5/5 | 同等 |

物の総数の例（5 回分）：map-core は製品 15440〜15852、公式 15443〜15811。map-all-dlc は製品 15772〜16240、公式 15816〜16037。

1 回あたりの時間（中央値）：公式 quick test 17〜20 秒、製品の対象実行 16〜19 秒。

## 既知のエンジンノイズ

マップを生成した Worker が終了すると、エンジンがネイティブメモリの解放漏れを 1 バッファごとに警告します（`NativeAllocationRuntime`、`Persistent allocation 0x... (N bytes, align 8) was not freed before shutdown.`、約 100 件）。アドレスと件数が毎回違うので、ベースラインと突き合わせられず、全て「対象で新しく出た警告」になっていました。結果を書いた後の終了処理で出る、MOD と関係のないメッセージなので、`KNOWN_NOISE` として判定から外しました。結果には `diagnostics.newInTarget[].knownNoise` として理由付きで残ります。レベル・カテゴリ・Worker の段階（`checks`）・本文全体が一致するものだけが対象です。

## 未適格・未確認

- マップ生成以外の段（`Game.FinalizeInit`、ゲーム開始、tick）。ゲーム開始時や時間経過で MOD が置く物は写りません。
- ほかの種・バイオーム・タイル。比較は既定の種のタイル 1 つ（AridShrubland）だけです。
- 文字列ハッシュ説は未検証です。
- Windows、標準 .NET。

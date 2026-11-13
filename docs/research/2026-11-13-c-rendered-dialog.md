# C材料：描画ありの公式processで実際の製造指示ダイアログを観測（研究）

基準main `b9122c4`（PR #75まで）。着手時の未マージPRは #66・#67（いずれもオフライン静的検査。本調査とは無関係）。

結論：**描画ありの公式process（クラウドLinux、仮想画面＋CPU描画）で、実際の `Dialog_BillConfig` を実 `WindowStack` から開き、ダイアログ自身のコードが実際のRepaint/Layout配信の中で列挙した材料行を記録できた。** fixtureの4行（`bill-ingredient-options.v1` の既存の陽性ケース）は、表示候補・許可状態とも製品の非描画Cと一致した。最終版スクリプトの一括実行3回（製品→対照→観測）がすべて同じ値で一致し、診断は「ダイアログを開かない対照process」と同一だった。

これは[C0継続調査](2026-10-30-c-context-continuation.md)で材料を停止した理由（公式headlessにはOnGUI配信・`Event.current` がない）に対する、次の観測の実施記録である。**C資格・Controller・cache・製品の判定は変更していない。** 開発用の比較であり適格化ではない。また、公式exeを描画ありで起動しており、AGENTS.mdが明記する「公式 `-headless -quicktest`」の範囲を超えるため、この方式を今後の参照に使うかはユーザー確認待ちとする。

## 環境

- クラウドLinux x86_64。追加導入：`dotnet-sdk-10.0`（10.0.115）、`mesa-vulkan-drivers`（25.2.8、Vulkanソフトウェア実装lavapipe）、`imagemagick`（私有スクリーンショットの取得用）。Xvfbは既存。GPUはない。
- ゲーム：`RWMT_R2_TRANSPORT=sdk` で `tools/codex_workflow.py prepare` を実行し、R2 `Game-Linux/` から必要分（英日以外の言語・debug除外）2,572ファイル・約906 MBを403秒で私有スナップショットへ準備。版 `1.7.4985 rev1269`、Adapter `rimworld-1.7.4985-rev1269`、identity hash照合済み。
- Harmony：NuGet `Lib.Harmony` 2.4.3（net10.0）の `0Harmony.dll`。私有領域のみ。
- 事前確認として、既存の非描画 `probe_c_context.py` を同じ環境で実行し、main実測（Private Linux validation #10）と同じ固定結果（material：段階 `pane`・`nullReference`、`guiEvent=false`）を再現した。
- 逆コンパイル本文・生ログ・スクリーンショットは私有領域だけに置き、コミットしていない。

## 方法

開発用の比較スクリプト [probe_c_rendered.py](../../experiments/official-comparison/probe_c_rendered.py) が、1回の起動で次の3つを順に行う。

1. **製品**：`levels: A,C`、`bill-ingredient-options.v1`、期待値は既存の陽性4行（下表）。製品のCは従来どおり非描画（fresh Game、`MakeNewBill`、`Listing_TreeThingFilter.Visible`、`HiddenItemsManager`）。
2. **公式・対照**：同じMOD構成（Core、自作Harmony、自作観測fixture、`billingredients`）で公式の `RimWorld` を `-NoCrashDialog` で起動する（`-headless` なし）。観測fixtureは読み込むが、ダイアログを開かない。描画経路そのものの診断を測る。
3. **公式・観測**：同じ構成で、観測fixtureが2つのrecipeについて実ダイアログを開き、行を記録する。

公式processの条件：

- 私有のXvfb（`:77`、1600×900、`-nolisten tcp`）と `VK_ICD_FILENAMES`（lavapipe）。GLFWはWaylandを使えずX11へ戻る（診断に出る）。
- 私有HOME/XDG、環境変数は最小限（PATH・HOME・XDG・LANG・DISPLAY・VK_ICD_FILENAMES）。ModsConfig/Prefsは製品の実行で作られたものを私有XDGへ複写。`Data/` はCoreだけをリンクし、DLCは読み込まない。
- 既存の私有supervisor（子孫回収）で、480秒・RSS 6 GiB・ログ上限を監視。
- 入力イベントは一切送らない。公式processは観測fixtureが `Application.Quit` を呼んで自分で終了する。スクリーンショットは外部の `import` で2秒ごとに私有領域へ保存する（判定には使わない）。

観測fixture [CRendered.cs](../../tests/fixtures/validation-mods-src/CRendered/CRendered.cs)（開発用、製品には含めない）：

- `UIRoot_Entry.UIRootOnGUI` の**prefix**で状態機械を進める。Repaintだけを数え、`ProgramState.Entry` かつlong eventなしが30回続いたら、製品と同じく**新しいGame（開始もtickもしない）**を `Current.Game` にし、`BillUtility.MakeNewBill(recipe, null)` と `new Dialog_BillConfig(bill, IntVec3.Invalid)` を作って `Find.WindowStack.Add` する。
- 各ダイアログは、ingredient paneのRepaintが3回以上かつ6秒以上（スクリーンショット用）経ったら閉じる。閉じる直前に `bill.ingredientFilter.Allows(def)` を記録する。上限は600 Repaint・120秒・全体20,000 Repaint。
- 最後に閉じた後、5回のRepaintを待ってから `Current.Game` を元に戻して終了する（下の「Waylithの事実」参照）。
- 記録用のHarmony patchはすべて数えるだけのprefix/finalizerで、元のメソッドを飛ばさず引数も変えない：`DoWindowContents`、`DoIngredientConfigPane`（prefix＋finalizer）、`ThingFilterUI.DoThingFilterConfigWindow`、`Listing_TreeThingFilter` の6引数constructor、`Listing_TreeThingFilter.DoThingDef(ThingDef,int,Map)`。行は「pane実行中にDoThingDefが呼ばれたdefName」とそのイベント種別（Repaint=7、Layout=8）。
- しないこと：入力イベントの合成、paneやlistingの直接呼出し、`Visible` などの判定式の差替え・複写、ツリーの開閉状態の変更、ゲームの開始・tick。

製品の実行にも観測fixtureを読み込むが、設定 `official=false` のため状態機械は動かず、ダイアログも開かない。

### 比較とゲート

`compare()` は製品の各行と公式の記録を並べる。公式の「表示」は、DoThingDefが**RepaintとLayoutの両方**で呼ばれた行。片方だけの場合は不整合として一致にしない。`gate()` は次の全条件を要求し、満たしても `qualified: false` を返す。

| 条件 | 内容 |
|---|---|
| productCompleted | 製品が完了、Cが完了、理由は `experimental`・`cNotQualified` だけ |
| officialCompleted | 対照・観測ともexit 0、中断なし、記録1件、`stop: none` |
| controlOpenedNothing | 対照はダイアログを1つも開いていない |
| dialogsDrawn | 両recipeが1件ずつ、開いた・メインスレッド・fresh Game維持・閉じた・例外なし・pane Repaint 3回以上、pane回数とUI/listing回数が整合 |
| diagnosticsMatchControl | 観測の診断分類が対照と完全に同じで、ダイアログ例外0・未分類0 |
| rowsAgree | 4行すべてで表示・許可が一致 |

合成データの単体試験 [test_c_rendered.py](../../tests/test_c_rendered.py)（13件、ゲーム不要）で、行の欠落・片方のイベントだけの列挙・許可の不一致・描画されていない/乱れたダイアログ・ケースの欠落や重複・診断の増加・対照側の異常・製品の不完全を、それぞれ一致にしないことを確かめた。ゲートの一部を外した変異（常に描画済み扱い、診断無視、製品の表示値無視）は、いずれも試験が失敗することを確認した。

## 結果

最終版スクリプトの一括実行3回（final-1〜3）とも `agreement: true`、全ゲート条件true、`qualified: false`。3回の値は秒数以外すべて同一だった。

| recipe | thing | 製品 表示/許可 | 公式 列挙（Repaint・Layout）/許可 | 一致 |
|---|---|---|---|---|
| RWMT_BillHidden | RWMT_BillGrain | false / true | なし / true | ✓ |
| RWMT_BillOptions | RWMT_BillGrain | true / true | 両方 / true | ✓ |
| RWMT_BillOptions | RawCorn | true / false | 両方 / false | ✓ |
| RWMT_BillOptions | RawPotatoes | false / false | なし / false | ✓ |

| 項目 | 観測（3回とも） |
|---|---|
| ダイアログ | 2件とも開いた（Repaint中・メインスレッド）、fresh Game維持、閉じた、例外なし |
| BillOptions | contents/pane 各Repaint 30・Layout 30、ThingFilterUI・listing 各60回、記録行2件（grain、corn） |
| BillHidden | contents/pane 各Repaint 31・Layout 31、ThingFilterUI・listing 各62回、記録行1件（corn） |
| 開く前のDialog層の窓 | 1件（Steamクライアントなしのメッセージ） |
| 閉じた後に走ったダイアログ関数 | 2回（排出待ち中、下記） |
| Repaint総数 | 観測96、対照35 |
| 所要時間 | 製品約14秒、対照約30秒、観測約42秒 |

診断（ERROR/WARN、文面は私有）は対照と観測で完全に同じ分類・件数：Steam初期化失敗2、GLFWのWayland不可2、初期化前のUnityData使用1、GpuProbe未完了（低性能扱い）1。ダイアログ関連の例外・未分類は0。製品側の新規診断・翻訳エラーも0。

私有スクリーンショットでは、BillOptionsのダイアログの材料欄に特殊フィルターの行（英語表示「Allow fresh」、許可）、Corn（不許可）、fixture plant grain（許可）が、BillHiddenではその特殊フィルター行とCorn（不許可）だけが表示されていた。記録した行と同じ内容である（特殊フィルター行は `DoThingDef` ではないので記録対象外。製品Cも物の行だけを判定する）。

開発途中の実行（5回）でも、行の値は最終版と同じだった。そのうち最初の2回は下記の理由でダイアログ例外を1件以上記録したため、修正前の結果として扱わない。

## 途中で分かった事実（Waylith、1.7.4985 rev1269）

- 描画ありでは、ImGui配信が実際に `Root.OnGUI` をLayout（8）とRepaint（7）で呼ぶ。headlessの0回（C0継続調査）とは異なる。
- ウィンドウ関数は、ルートの `UIRootOnGUI` が終わった後にまとめて走る。最初の試作ではルートのpostfixで `Current.Game` を戻していたため、同じ回の保留中のダイアログ関数が `Game` なしで走り、`Find.HiddenItemsManager` でNullReferenceExceptionになった。ルートのprefixで状態機械を進めるよう直した。
- `WindowStack.TryRemove` で外したウィンドウの関数が、**次の回にもう1度だけ**走る。そのため最後に閉じてから数回待ってから `Current.Game` を戻す必要がある（排出待ち5 Repaint、遅れて走った関数は毎回2回）。
- Steamクライアントがない環境では、`UIRoot_Entry` がSteamなしのメッセージ（Dialog層）を出す。Dialog層の窓がある間はメインメニューを描かず、メインメニューが `Current.Game` をnullに戻す処理も走らない。この観測はこの状態に依存しており、入力を送らないので「終了」ボタンは押されない。
- Entryで `Current.Game` がnullでないため、画面右上に学習ヘルパーが出る（判定には影響しない）。

## 限界・未実施

- **Coreだけ・fixtureの2 recipe・3物だけ。** 実MOD（小麦粉MODの不具合版/修正版）は未実行。
- **折りたたまれた分類の行は列挙されない。** 材料欄は親フィルターの表示ルート分類から始まり、子分類は開いているもの（または検索中に一致するもの）しか辿らない。既定で開いているのは全体ルート直下の最初の子分類だけ。fixtureの物は表示ルート直下にあるので列挙されたが、複数の分類にまたがるrecipeでは、製品が表示=trueとする行が公式側では列挙されないことがある。開閉状態を変えない現在の観測では、そうした行は「公式で未観測」として扱う設計が先に必要。
- **DLC未検証。** Ideologyが有効だと、ダイアログはpaneの後で `Find.IdeoManager.classicMode` を読む。fresh GameにはWorldがないので例外になると静的には読めるが、実行していない。
- CPU描画（lavapipe）・GPUなしでの観測。描画の見た目は判定に使っていない。
- 公式exeを描画ありで起動しているのは、AGENTS.mdの「公式 `-headless -quicktest` は開発用比較に限り」の文言の外にある。遊べる状態にはしていない（入力なし・自動終了・Game開始/tickなし・私有の仮想画面）が、採用はユーザー確認を待つ。
- これは参照方式が成立することの記録で、C資格・cache・製品の判定式は変更していない。CIにも組み込んでいない（公開CIはゲームを使えない）。

## 再現

私有領域（checkout外）で、ゲームの準備とWorkerのビルドを[codex-cloud.md](../codex-cloud.md)どおり済ませた後：

    sudo apt-get install -y dotnet-sdk-10.0 mesa-vulkan-drivers imagemagick   # Xvfbも必要
    python3 experiments/official-comparison/probe_c_rendered.py \
      --snapshot "$RWMT_PRIVATE/game-snapshot" --out "$RWMT_PRIVATE/runs/c-rendered-1" \
      --harmony-dll "$RWMT_PRIVATE/harmony/lib/net10.0/0Harmony.dll"

`--out` は新しい、checkout外のディレクトリでなければならない。終了コード0は `agreement: true` のときだけ。公開してよい要約は `safe-summary.json`、生ログ・スクリーンショット・製品の詳細は `private-evidence.json` と各サブディレクトリ（いずれも私有）。

## 次の候補

1. この方式（描画ありの公式process・開発用比較）を参照に使ってよいかの確認と、許可された場合のAGENTS.mdの更新。
2. 小麦粉MODの実例（不具合版/修正版）を同じ方式で観測し、製品の検出・非検出と並べる。その前に、折りたたまれた分類の扱い（未観測として除外するか、別の観測を設計するか）を決める。
3. DLC有効時の文脈（World・IdeoManagerなし）の扱いの設計。

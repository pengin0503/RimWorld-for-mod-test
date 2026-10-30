# C0継続：材料・イベントの文脈実測と停止記録

基準main `6a4404814cf628dc3f876a20d464174428e66234`（PR #47まで）。着手時の未マージPRは0件。
依頼で必読とされた `docs/superpowers/specs/2026-10-30-c-context-continuation-design.md` と `docs/superpowers/plans/2026-10-30-c-context-continuation.md` は、リポジトリ（全ブランチ）、前セッションのcheckoutパス、共有フォルダのいずれにも存在せず、添付もなかった。**この2文書は読んでいない。** 依頼文に書かれた制約と既存の研究記録・設計（[文脈probe設計](../superpowers/specs/2026-10-30-c-context-probe-design.md)、[独立適格化計画](../superpowers/plans/2026-10-29-c-independent-qualification.md)）に従った。

結論：**材料とイベントの両ケースとも、研究上の文脈ゲートは成立しない根拠を得て停止する。** C0=false、独立資格・cacheは変更しない。D（独立比較）とE（資格）へは進まない。

## main実測

[Private Linux validation #9](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41037681388)：runId `41037681388-1`、commit `6a44048`、suite `c-context`。私有ランタイム準備・Worker/fixture buildに成功し、2ケースを79.974秒で完了（中断なし、helperのexit1は参照ゲート未通過による）。validationStatus=incomplete、qualificationStatus=experimental。

| ケース | 実測 | 停止条件 |
|---|---|---|
| material | 段階 `pane`、例外分類 `nullReference`。pane=1、ui=1、listing=0、row=0 | official.paneDidNotReturn / treeRowNotReached / diagnosticsOrExit |
| event | 製品 generated→marker、公式 init→generated→finalize→marker（前回と同じ） | official.finalizedBeforeMarker / 両側 diagnosticsOrExit |

PR #47のconstructor修正で前回のdialog段階missingApiは解消し、実paneとThingFilterUIへの入口に到達した。依存取得先（PR #46）の診断は消えた。

## 私有ローカル調査（開発用の比較。main証拠ではない）

クラウドLinuxでR2 `Game-Linux/` から必要分（言語は英日のみ、debug除外、2,572ファイル）を私有領域へ準備し、Adapter `rimworld-1.7.4985-rev1269` を認識、Assembly-CSharp.dllのSHA-256が登録値と一致した。同じ `probe_c_context.py`（公式processは180秒、RSS監視2 GiB、ログ合計8 MiB、子孫回収、私有HOME/XDG、memoryHard=false）でmainのfixtureを実行し、#9と同じ固定結果を再現した。逆コンパイル本文・生ログは私有領域だけに置いた。

### 材料：公式headlessに自然なGUIパスがない

- 私有ログの例外位置は `Verse.Mouse.IsOver` で、`ThingFilterUI.DoThingFilterConfigWindow` の最初のウィジェット（`Widgets.ButtonText`「ClearAll」）から呼ばれる。`Listing_TreeThingFilter` のconstructorより前で止まるため、listing/rowは0になる。`Mouse.IsOver` は `Event.current.mousePosition` を読む。
- fixtureの入口で新たに記録した固定値は `guiEvent=false`（`Event.current` なし）、`windowStack=false`（`Find.WindowStack` なし）。
- 対応DLLの照合：`Event.current` を設定するのは `RimWorld.dll` のImGui配信（ImguiDispatch）だけで、Assembly-CSharp.dll・UnityStubs.dll・Waylith系DLLには設定箇所がない。ImguiDispatchはフレーム描画の構成時にだけ作られ、その構成はheadlessでは呼ばれない。
- コミットしない一時計測で、公式headless（-QuitAfterBoot）の材料processは `Root.OnGUI` を終了まで0回しか呼ばなかった（終了時にはWindowStackは存在）。

したがって公式headlessには、Dialog_BillConfigのpaneが自然に描かれるGUIパスが存在しない。StaticConstructorOnStartupでもそれ以降のheadless内の点でも同じである。GUI eventの偽造、paneを経ないlistingの直接呼出し、Visibleの差替え・可視判定式の複写は禁止のため行わない。行未呼出をvisible=falseとして扱わない。**材料はここで停止する。**

成立に必要な次の観測：描画ありの公式process（Linuxでは描画可能なGPU/Vulkan環境）で、`Root.OnGUI` が実際のEventを伴って動くことを確認し、WindowStack経由で開いたダイアログのpane/listing/rowを観測する。その場合、fresh GameをGUIフレームの間Current.Gameとして保つ必要があり、finally復元とtickなしをどう両立させるかの設計が先に必要。Windows版は凍結中のため対象外。

### イベント：公式に製品と同じ文脈の観測点がない

対応DLLでは、公式quicktestの「GeneratingMap」long eventは非同期で、その中で `Game.InitNewGame` が `MapGenerator.GenerateMap` → 初期マップサイズ設定 → 入植者の思考付与 → `FinalizeInit` を同期に続けて実行する。生成とFinalizeInitの間にキューの境界はない。

fixtureの各phaseに、スレッド・ProgramState・long event実行中か・when-finished待ち件数・CurrentMapの有無を追加して実測した（値の読取だけで、キューやFinalizeInitは変更しない）。

| 側 | phase | main thread | ProgramState | CurrentMap | FinalizeInit |
|---|---|---|---|---|---|
| 製品 | marker（観測点の代理） | true | Entry | なし | 0回 |
| 公式 | generated（GenerateMap postfix） | false | MapInitializing | なし | 0回 |
| 公式 | finalize（FinalizeInit prefix） | false | MapInitializing | なし | 本体実行前 |
| 公式 | marker | true | Playing | あり | 1回後 |

公式でFinalizeInitより前の自然なhookは、どれもlong eventの非同期スレッド上、MapInitializing中である。製品の観測点はメインスレッドのキュー処理で、Entry、FinalizeInit未実行。公式でメインスレッドに戻る最初の点はFinalizeInit後である。同期postfixを製品のqueued observerと同じとみなせず、FinalizeInitやキューを抑止・遅延・置換すること、製品CをDの初期化後へ移すことは禁止のため、**イベントはここで停止する。** 新しい位置でTryExecute/Activateは実装していない。gateには、製品と同じ文脈（スレッド・ProgramState・CurrentMap・long event）の公式FinalizeInit前候補がないことを `official.noMatchingPreFinalizeContext` として加えた。成立条件を緩める変更ではない。

製品のmarkerは生成eventのwhen-finished処理で、実際の観測（次のキューのevent）とは別の点だが、両者ともメインスレッド・Entry・FinalizeInit前である。

成立に必要な次の判断：公式の自然な流れに製品と同じ文脈がないため、別の参照方式（例えば製品側の観測文脈自体の変更）が必要になる。これは製品Cの文脈を変える設計判断で、本調査の範囲外。

### 診断

分類は除外規則ではなく、ゲートの拒否条件のまま残した。私有文面で確認した内容は次の通り（文面・パスは公開しない）。

- 公式のSteam 2件：Steamクライアントなしでの `SteamAPI.Init()` 失敗。既存の完全一致除外（1文面）と異なる文面が残っている。
- graphics/Texture 1件（製品の両ケースと公式イベント）：UnityStubsの `DrawTexture` stub警告。

両ケースとも構造上の理由で停止しているため、これらを除外しても結論は変わらない。比較へ進むケースが出た時に、事前定義の完全一致として扱うかを別途判断する。

## 公開要約の検証強化

`safe_cases()` は、`gatePassed=true` に両側の診断情報が揃い、exitCode=0、interrupted=false、errorCount=0、kinds=[] であることを要求する。材料の成功は段階 `complete`・例外 `none` も要求する。失敗記録でも、診断と停止理由（diagnosticsOrExit）、実行状態と中断、kinds件数とerrorCount、段階と例外分類、例外とpaneDidNotReturn、pane前の段階と入口回数、文脈と停止理由の矛盾を拒否する。診断情報のない古い失敗記録は失敗として公開を保ち、成功や資格へ昇格させない。probeと同じ導出をした行が拒否されないことも試験している。

## マージ後のmain実測

[Private Linux validation #10](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41042238650)：runId `41042238650-1`、commit `ff40256`（PR #48）、suite `c-context`。2ケースを83.885秒で完了、中断なし、validationStatus=incomplete、qualificationStatus=experimental。追加した固定項目は私有ローカル調査と同じ値だった。

- material：`guiEvent=false`、`windowStack=false`、段階 `pane`・`nullReference`、pane=1/ui=1/listing=0/row=0。停止理由に `official.noGuiEvent`。
- event：製品markerはメインスレッド・Entry・CurrentMapなし。公式のgenerated/finalizeは非メインスレッド・MapInitializing、公式markerはメインスレッド・Playing・CurrentMapあり。停止理由に `official.noMatchingPreFinalizeContext`。
- 診断はSteam/Textureの件数・分類とも#9と同じ。

## 未実施

- 描画ありの公式processでの材料観測、イベントの別参照方式の設計。
- D（独立比較：3独立process・mutation・不在例）とE（資格/cache）。両ケース停止のため対象外。
- Steam/Texture診断の完全一致規則化。

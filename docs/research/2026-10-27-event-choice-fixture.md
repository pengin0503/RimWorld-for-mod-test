# 自作イベント選択肢 fixture の観測（2026-10-27）

Linux x86_64、RimWorld 1.7.4985 rev1269、同梱 WaylithClr、Core、生成マップと固定 seed で自作 fixture を使った。描画と tick は実行していない。限定された `event-choice.v1` の事件 `RWMT_ChoiceEvent` を実行し、ゲームの選択肢を有効化して、生成された Steel の数を観測した。

初回は fixture の IncidentDef に対象タグがなく、事件定義の設定エラーが2件出た。タグを修正した再実行では新規エラーなし。事件・選択肢の提示・選択肢の実行を観測し、生成された Steel 10 個が期待と一致した。C 段階は `completed`、実行は `completed`、全体は `incomplete` / `experimental`（`cNotQualified`、`mapNotQualified`）。これは実 MOD のイベント・クエストや実画面の保証ではなく、ケースの適格化でもない。

再現にはゲームスナップショットとビルド済み Worker が必要。`tests/integration/run_event_choice.py` は自作 fixture を私有領域でビルドして実行する。ゲーム DLL、fixture DLL、結果やログは公開しない。

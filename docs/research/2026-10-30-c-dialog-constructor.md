# C0材料ダイアログのconstructor修正

[動的確認 #8](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41007067985)（main4d56d91）は両ケースを69.257秒で完了し、製品/公式ともexit0、中断なし。材料はdialog段階のmissingApiであり、pane/UI/listing/rowの入口は0だった。これは観測fixtureがconstructorを誤って呼んだ結果で、headless UIの不成立を実証したものではない。

[静的監査 #8](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/41008373102)（main6bc1413）で、実constructorの署名を `instance public System.Void (RimWorld.Bill_Production, Verse.IntVec3)` と確認した。固定8入力のversion/hash確認を維持している。

観測fixtureの1引数Activator呼出を、実署名に一致するpublic constructorの2引数呼出へ修正する。fresh Game/new BillにはマップやBillの設置位置がないため、位置にはゲーム自身のIntVec3.Invalidを渡す。これは研究実装上の判断であり、既存製品のBillやGameにMapを追加したり、constructorを省略して内部フィールドを捏造したりしない。位置の前提は独立参照の後続比較にも拘束する。C0=falseを維持する。

同実測のdependency/downloadUrl分類はCContextの依存宣言で取得先が欠けていたことと対応し、PR #46で既存fixtureと同じ取得先を追加した。Steamおよびgraphics/Texture分類は未解決。分類だけでノイズとして除外せず、再実測で件数・到達・停止段階を確認する。

## 今回の作業終了点

ユーザーの「キリの良いところで終了」の指示に従い、constructor修正の合成検証と公開CI・PR統合を今回の区切りとする。ゲームを参照しないC#テストは、2引数が保持され、旧1引数APIへ誤ってfallbackしないことを検証する。関連Python87テストも通過した。

**constructor修正・依存メタデータ修正後の実ゲーム再実測は未実施。** 次回はmainでc-contextを明示実行し、dialogのmissingApiと依存取得先診断が解消したか、pane/UI/listing/rowに到達するかを確認する。既に実証したeventのFinalizeInit前後の文脈差と、未分類のSteam/Texture診断を未解決として引き継ぐ。C0・独立資格・cache登録は変更しない。

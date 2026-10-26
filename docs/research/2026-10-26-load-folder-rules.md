# 1.7.4985 のロードフォルダ選択規則

確認対象は適格化済み Linux x64 の `Assembly-CSharp.dll`（ゲーム 1.7.4985 rev1269）。既存スナップショットの私有コピーを ILSpy 11.1 で調べた。逆コンパイル本文・ゲーム DLL は保存先を checkout 外に限定し、この記録には要約だけを含める。

## 出典と挙動

- `Verse.ModContentPack.InitLoadFolders`：`LoadFolders.xml` の定義があれば、現在の完全バージョン文字列の非空リスト、現在版以下の定義名を文字列で降順にした最初のもの、`default` の順に探す。選択リストは逆順に評価し、有効なフォルダだけを高優先順の一覧にする。選択済みリストの全条件が偽でも、既定の root/Common に追加フォールバックはしない。
- 指定が使われない場合：直下の `1.7` ディレクトリを優先。なければ `RimWorld.VersionControl.TryParseVersionString` で解釈した版から、現在版以下で最大のものを選ぶ。現在版以下が一つもなければ最小の未来版。次に存在する `Common`、最後に root。`1.7` がなければ必ず root だけ、という挙動ではない。
- `TryParseVersionString` は最初の major/minor を使う一方、選択されたフォルダは正規化された版名で構築される。今回の取得器は非正規の数値版ディレクトリを安全に再現できない場合、推測せず `unsupportedVersionDirectory` で止める。
- `Verse.ModLoadFolders.LoadDataFromXmlCustom`：版タグは小文字化し、先頭の `v` を外す。`/` と `\` は root 指定。`Verse.LoadFolder.ShouldLoad`：`IfModActive` はカンマ区切りのどれか、`IfModActiveAll` は全部、`IfModNotActive` はどれも有効でない場合。複数属性は AND。判定は `ModLister.AnyModActiveNoSuffix` / `AllModsActiveNoSuffix` による有効 MOD の識別子照合。
- `Verse.ModMetaData.ModMetaDataInternal.InitVersionedData` と `VersionedData<T>.GetItemForVersion`：`modDependenciesByVersion` の現在の major/minor（1.7）に対するリストがあれば、空リストでも通常の `modDependencies` を置き換える。依存不足を自動で解決・追加する処理ではない。
- `Verse.ModContentPack.AllDefs` は当該 MOD が読み込んだ Def の一覧。比較用にその件数と実際の `foldersToLoadDescendingOrder` を Worker の `runningMods` に観測値として記録する。Def の内容や値を書き換えない。

## 取得器での対応

`tools/mod_load_plan.py` は R2 の列挙済みパス、取得した LoadFolders、要求の全 MOD/DLC の識別子からロード計画を作る。root は空文字で表し、実際の優先順を保存する。選択したフォルダ配下の Defs/Patches XML、Assemblies DLL、指定言語と英語フォールバックの XML/TXT を取得する。VPE の実ロードで必要性を確認した Textures の画像と Sounds の音声も同じ有効フォルダ内だけ取得する。旧バージョン全体やソース、デバッグ情報、無関係な言語は取得しない。

### 追補（2026-10-26、Claude による再照合）

同じ DLL で、有効フォルダからゲームが読む入力を列挙し直した（`DirectXmlLoader.XmlAssetsInModFolder`、`ModContentPack.GetAllFilesForMod` の全呼び出し元、`ModContentLoader<T>.IsAcceptableExtension`、`GenFilePaths.ContentPath<T>`、`ModAssetBundlesHandler`、`ShaderDefRegistry.RegisterShaderDirectories`、`LoadedLanguage.AllDirectories` と `RimWorld.IO.AbstractFilesystem`）。当初の選択では次が落ちていたため追加した。

- `Languages/<言語名>.tar`：ゲームは言語フォルダと同名の tar も同じように読む。落とすと、その MOD の翻訳が丸ごと読まれず、翻訳エラーが出ないまま合格し得た。
- `Strings/*.txt`（`ModContentHolder<string>`）、拡張子なしの `AssetBundles/*`（OS 別の接尾辞はゲームが選ぶ）、`Shaders/` 配下（Waylith のシェーダーディレクトリとして登録）。
- 音声の `.xm` `.it` `.mod` `.s3m`（ゲームの受理拡張子。`.aif` `.aiff` `.flac` は従来どおり取得するがゲームは読まない）。

さらに、計画したロードフォルダを要求の `mods[].expectedLoadFolders` に書き、Controller が実ロード後の `runningMods[].loadFolders` と比較する。異なれば `loadFolderMismatch` で incomplete とし（実ゲームでの確認は[小麦粉 MOD の記録](2026-10-26-flour-mod-c-run.md)）、規則の読み違いや R2 列挙とキャッシュの食い違いが残っても、取得していないフォルダに基づく合格を出さない。

版別定義の代替選択で、ゲームは定義名を**文字列**の降順で選ぶが、`mod_load_plan.py` は数値の降順で選ぶ。`1.10` のような 2 桁の minor が現行版以下に現れるまでは同じ結果になる。食い違った場合も上の比較で incomplete になる。

全 MOD の About と LoadFolders を先に取得・照合し、依存不足や未解釈条件があれば payload と要求 JSON の生成前に停止する。`--official` で明示した DLC を条件と依存の評価・要求 JSON の双方に使用する。選択フォルダはフィルター後に空でもディレクトリとして作り、ゲーム側のフォールバック先が変わらないようにする。

不正 XML、未知条件、危険な相対パス、有効なフォルダが空の場合は理由コード付き `blocked`。（2026-10-26 訂正）`LoadFolders.xml` に書かれたフォルダは、ファイルがなくても（空・不在でも）計画に残す。逆コンパイルした `ModContentPack.InitLoadFolders` では、`LoadFolders.xml` の項目は `Directory.Exists` を確かめずに読み込み先へ加えられる（存在を確かめるのは `LoadFolders.xml` がない場合だけ）。以前はこれを `missingLoadFolder` で止めており、ゲームより厳しく、正しい MOD を blocked にしていた。ゲームより厳しい拒否を行う箇所はあるが、未対応条件を黙って無視して合格にしない。`--scope all` は明示された場合のみ使い、依存の不足はその場合も停止する。

UTF-16/32 など NUL を含む XML、DTD/ENTITY 宣言も保守的に拒否する。About の依存コンテナが重複したり、リストに非空の自由テキストがある場合は `invalidDependencies` とし、空の正規な版別リストによる置換だけを認める。

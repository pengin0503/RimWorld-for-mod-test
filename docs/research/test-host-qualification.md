# 検証ホストの適格化（公式 headless との比較）

実施日：2026-10-25。環境：Claude のクラウド Linux x86_64 コンテナ、ユーザー提供の RimWorld Linux 版 1.7.4985 rev1269 から作ったスナップショット、同梱 WaylithClr 10.0.13。Worker は最終ビルド（本 PR の `worker/`）。

## 結論

<a id="linux-x64-waylithclr"></a>**Linux x86_64＋WaylithClr＋1.7.4985 rev1269 の A/B を `qualified` とする。** 自作 fixture の 9 構成で、製品の Worker と公式実行ファイルの headless 起動（`-headless -QuitAfterBoot`）について次の 2 点を比べ、全て一致した。比較の前に期待値を決めて照合した。

- 出たエラー・警告の 1 行目と件数。多重集合として比べた。
- ゲーム内部の読込結果。

この比較は開発時の作業として `experiments/official-comparison/compare_official.py` で行った。製品は公式実行ファイルを起動しない。

適格化の範囲は上記の組み合わせ、A/B、比較した種類の事象に限る。Windows、標準 .NET、ほかのビルド、C/D は含まない。ビルド・ランタイム・Worker が変わったら、この結果は失効させる。

## 比較の方法

- 同じスナップショット、同じ `Data/` 選択、同じ MOD のコピー、同じ `ModsConfig.xml`/`Prefs.xml` を使った。設定は DevMode=true、resetModsConfigOnCrash=false。
- 公式側には専用の HOME/XDG を与え、通常のプロファイルには触れていない。
- 両方に開発専用のプローブ MOD（`comparisonprobe`）を入れた。読込完了後に次の値を同じ書式でログへ出す。
  - 実有効 MOD の順序と言語
  - Core の Steel の値と、fixture の Def
  - Keyed 翻訳と Mod クラス
  - Harmony の全登録（対象・種別・owner・パッチメソッド）と、パッチの実際の効果
- 公式側だけに出る Steam 初期化の警告は除外した。Worker は Steam を意図的に初期化しないため。ほかの除外はない。

## 結果

| 構成 | 製品の判定 | エラー/警告（Worker / 公式） | プローブ値 | 公式 headless 秒 | Worker（対象）秒 |
|---|---|---|---|---|---|
| core-only（Core＋プローブ） | passed | 1 / 1 一致 | 一致 | 8.4 | 7.9 |
| ok（正常な XML・パッチ・翻訳） | passed | 1 / 1 一致 | 一致 | 9.2 | 8.3 |
| ok-all-dlc-japanese（Core＋4 DLC、日本語） | passed | 2 / 2 一致 | 一致 | 13.8 | 14.6 |
| side-effect（Steel 価格の変更→公式 Def 検査のエラー） | failed（newErrors） | 3 / 3 一致 | 一致 | 8.6 | 8.5 |
| bad-patch（XPath が一致しないパッチ） | failed（newErrors） | 2 / 2 一致 | 一致 | 8.9 | 8.5 |
| bad-reference（存在しないカテゴリ参照） | failed（newErrors） | 4 / 4 一致 | 一致 | 8.3 | 7.7 |
| init-exception（Mod コンストラクタの例外） | failed（newErrors） | 2 / 2 一致 | 一致 | 7.7 | 8.3 |
| harmony-ok（postfix を登録） | passed | 1 / 1 一致 | 一致（登録と効果 `a b [rwmt]`） | 9.0 | 8.7 |
| harmony-missing（PatchAll を呼ばない） | failed（harmonyPatchMissing） | 1 / 1 一致 | 一致（登録なし、効果 `a b`） | 8.1 | 8.8 |

秒数は 1 回ずつの参考値。速度の評価は [性能](test-host-performance.md) を参照。

共通の警告 1 件は UnityStubs の `DrawTexture ... Stub!`。headless のスタブで、どちらの起動でも出る。

## 製品の判定の確認（私有の実物行列）

`tests/integration/run_fixture_matrix.py` を最終ビルドで実行し、16 ケース全てが想定どおりだった。

| ケース | 判定 | 理由コード |
|---|---|---|
| ok / ok-japanese / ok-all-dlc-japanese / harmony-ok | passed | — |
| expectation-mismatch | failed | expectationMismatch |
| side-effect / bad-patch / bad-reference / init-exception | failed | newErrors |
| harmony-missing | failed | harmonyPatchMissing |
| harmony-no-expectation | incomplete | noExpectedPatches |
| harmony-not-provided | blocked | harmonyMissing |
| level-c | blocked | levelUnsupported |
| timeout（10 秒上限で全 DLC） | incomplete | workerInterrupted, baselineIncomplete |
| standard-runtime-ok | incomplete | experimental |
| standard-runtime-bad-reference | incomplete | experimental, newErrors |

## 比較で見つかり直した問題

- **言語の指定**：`Prefs.langFolderName=Japanese` では英語に戻っていた。言語は `Japanese (日本語).tar` として同梱されているため。Worker が `activeLanguage` を報告するようにし、Controller は名前を実名へ解決して、未適用なら `incomplete` にするよう改めた。
- **以前の記録の訂正**：「Core だけでも DevMode で Villager などの Config error が出る」という以前の記録は誤りだった。原因は旧 fixture の Steel 価格パッチで、現在の `side-effect` ケースにあたる。
- **締切の扱い**：メインスレッドがゲームコード内で止まっていると、Worker が自分の締切で止まれないことがあった。専用スレッドの監視を加え、`timeout` ケースで `workerInterrupted` を確認した。

## 未適格の範囲

- 標準 .NET：`ProfilerBootStart` の静的コンストラクタが `TypeLoadException` で失敗する差がある（[依存](test-host-dependencies.md)）。故障検出は 2 ケースで一致したが、差の影響範囲を証明していない。
- Windows：比較環境がない。Linux の結果を Windows の欄へ転記しない。
- 実際の利用者 MOD：まだ実行していない。fixture にない種類の事象、たとえば transpiler、非同期処理、Steam 依存には、別途の比較が必要になりうる。

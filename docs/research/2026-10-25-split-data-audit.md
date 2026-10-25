# 分割 Data の追加調査（2026-10-25）

`Rim_data_1.zip`、`Rim_data_2.zip`、`Rim_data_3.zip` は今回読み取れた。依頼された Data の受け入れ・静的調査と関連資料の更新を行った。ゲーム起動、本体実装、設計の変更は行っていない。

元の `Rim_Data.zip` は未受領のままで、分割版との完全一致は確認できない。ただし元の再送は不要。前回の取り込み失敗がサイズに起因するかは、この検査では判定できない。

## 受領内容と整合性

ディレクトリ、`__MACOSX/`、`.DS_Store` を除く。サイズは圧縮後の実測値。SHA-256 と内側のパックの識別情報は [split-data-inventory.json](split-data-inventory.json) に記録した。

| ZIP | bytes | ファイル数 | 含まれる範囲 |
|---|---:|---:|---|
| `Rim_data_1.zip` | 105,654,881 | 1,878 | Core、Ideology、Biotech |
| `Rim_data_2.zip` | 140,248,276 | 185 | Royalty |
| `Rim_data_3.zip` | 109,059,938 | 270 | Odyssey |
| 合計 | 354,963,095 | 2,333 | 展開後の合計は 460,745,474 bytes |

- 各 ZIP は単体で開ける独立したアーカイブ。バイナリ連結する形式ではない。
- 外側の全エントリを読み出し、CRC 不一致はなかった。ディレクトリ・Mac 補助ファイルもこの検査には含めた。
- DLC 内の `Assets.zip` 4 個、合計 6,851 ファイルも展開後サイズと CRC が一致した。ZIP method 93（Zstandard）を含むため、Python 3.12 標準 `zipfile` だけでは読めない部分を、導入済みの Zstandard デコーダーで確認した。
- 翻訳 TAR 77 個の全通常ファイルを読み出せた。TAR 自体には ZIP のような全ファイルの CRC はないため、CRC 検査済みという表現は使わない。
- パストラバーサルとなるパス、リンク、外側 ZIP の統合先の重複、大小文字・Unicode 正規化後の衝突は検出されなかった。

CRC 一致は受領した ZIP の破損検査であり、正規インストール全体の完全性、公式署名、同一ビルド互換性の証明ではない。

## Core と DLC の内訳

件数はファイル数であり、Def の個数ではない。翻訳 XML 欄は ZIP 直下側の XML だけを数え、TAR 内は次節で別集計した。

| コンテンツ | 全ファイル | Defs XML | Patches XML | 翻訳 XML | 翻訳 TAR | Assets.zip |
|---|---:|---:|---:|---:|---:|---|
| Core | 1,371 | 554 | 0 | 31 | 1 | なし |
| Ideology | 247 | 212 | 1 | 11 | 20 | あり |
| Biotech | 260 | 219 | 5 | 14 | 18 | あり |
| Royalty | 185 | 148 | 2 | 12 | 20 | あり |
| Odyssey | 270 | 231 | 6 | 12 | 18 | あり |

各 `About.xml` の packageId は Core と対象 DLC に対応し、DLC 4 個の supportedVersions は `1.7`。Core は同じ欄を持たない。正確なゲームビルドを照合できる情報は今回見つからず、Windows DLL や今後受領する Linux 一式との互換性は未確認。Anomaly の独立したコンテンツフォルダはなかった。共通 Core 内の名称だけから DLC の所持や有効化は判断しない。

## XML の構文検査

外側の XML 1,463 個と TAR 内の XML 16,343 個、計 17,806 個を ElementTree で構文解析した。17,805 個は通過し、次の 1 個が構文エラーとなった。

| 入力内の場所 | 結果 |
|---|---|
| `Biotech/Languages/Polish (Polski).tar` 内の `DefInjected/HediffDef/Hediffs_Various.xml` | 53 行目、0 始まりの列 84。終了タグ前の余分な `<` により不正な XML |
| 英語 XML 80 個 | 構文検査に通過 |
| 日本語 TAR 内の XML 1,360 個 | 構文検査に通過 |

ポーランド語のエラーは今回受領した公式コンテンツ内の診断であり、対象 MOD の不具合とは数えない。元のファイルは変更していない。英語・日本語の成功も XML 構文に限る。Def の型変換、XML パッチ、継承、クロス参照、翻訳注入、ゲームでのロード結果は検査していない。

## 配置と残る不足

1. 各 ZIP の `Rim_data_1/` などは受け渡し用のラッパー。将来の準備では、その内側の Core/DLC を検証コピーの `Data/` 配下へ対応させる。今回は配置・起動していない。
2. `Core/Shaders/` に GLSL 225 個と `.spv-cache` 486 個がある。ただし受領済み `RimWorld.dll` の `Bootstrap.ResolveShaderSourceDirectory` は `AppContext.BaseDirectory/Rendering/Shaders` を返す。GLSL が存在することと、この起動条件を満たすことを分けて扱う。内容の同等性を確認せずに移動しない。
3. Core の `Assets.zip`、インストール直下の `Assets.zip`、同等の完全な展開済み Core リソースは今回の ZIP にない。DLC アセットだけでは Core の不足は埋まらない。
4. Linux 公式実行ファイル、WaylithClr、対応する managed/native 一式は今回追加されていない。実行準備は引き続き `blocked`、ゲームによる各検証は `notRun`。
5. 非 ASCII 名 59 件で ZIP の UTF-8 フラグが立っておらず、Python 標準の名前解釈では文字化けする。将来の配置前に元の名前・文字コードを確認し、Mac 補助ファイルを混ぜずに扱う。今回の読み出し・構文検査は ZIP エントリを直接参照して行った。

公開するのはこの調査結果と hash・件数・診断パスのみ。ゲームの XML、GLSL、アセット、翻訳本文、ZIP/TAR、個人データはコミットしない。追加で必要なものは [ファイル一覧](../linux-files-needed.md) に反映した。

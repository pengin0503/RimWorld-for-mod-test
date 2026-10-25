# Core アセット管理情報の調査（2026-10-25）

`bake.manifest` と `textures.info` を受領し、読み取り専用で検査した。Core の完全なアセット ZIP や、そのリソース本体を受領したという意味ではない。今回の変更は調査資料のみで、設計・製品コードは変更していない。

## 検査結果

| 入力 | bytes | 読み取り結果 |
|---|---:|---|
| `bake.manifest` | 789,907 | UTF-8、パスと 64 桁の大文字 16 進ハッシュ値の組が 5,907 項目。パス重複・不正な行・危険な相対パスは検出されなかった |
| `textures.info` | 293,763 | UTF-8、パスと整数 6 個の組が 3,455 項目。パス重複・不正な行は検出されなかった |

`textures.info` のパス集合は、manifest 内の `Resources/Textures/` の集合と一致した。ただし各数値フィールドの意味は今回検証していない。管理情報にあることと、実ファイルを受領・検証できたことは区別する。受領ファイル自体の SHA-256 と集計値は [JSON](core-asset-metadata-inventory.json) にある。

受領済み `Waylith.dll` の `AssetPackManifest.ReadContentHashes` と `Parse` を静的に照合した。`bake.manifest` を UTF-8 として読み、行の最後の空白を境にパスと値へ分ける処理がある。ゲームの処理を実行したものではない。

| manifest の範囲 | 論理パス数 |
|---|---:|
| `Resources/Textures/` | 3,455 |
| `Resources/Sounds/` | 2,437 |
| `Resources/Fonts/` | 5 |
| `Resources/Text/` | 6 |
| `Resources/Backstories/` | 4 |
| 合計 | 5,907 |

manifest はリソースの論理パスの収録表であり、ZIP 全エントリの一覧ではない。`shaders/`、`textures.info`、`bake.manifest` 自体の項目はない。ファイルサイズも記載されていないので、これだけから 100 MB ごとの分割範囲は計算できない。画像から得られた shader cache の件数は、今回実ファイルを確認した件数に含めない。

## フォント 5 名と、画像の 3 ファイルの関係

`Arial_medium.ttf`、`Arial_small.ttf`、`Arial_tiny.ttf` は manifest 上で同じハッシュ値を持つ。他は `Calibri_tiny.TTF` と `Pretendard-Regular.otf`。受領済み DLL の `AssetPack.AliasDeduplicatedEntries` には、manifest の同じハッシュを持つ実エントリを探して別名から参照する処理がある。

したがって、画像で Arial が 1 個しか見えないことだけで欠損とは判定しない。実際の Core ZIP での参照解決と、展開済みフォルダからの読み込みは未検証。元のファイルを変更したり、画像だけを根拠に不足する別名を作ったりはしない。

manifest 全体では異なるハッシュ値は 5,868 個で、同一ハッシュによる重複分は 39 項目。ただしこれは実 ZIP のエントリ数・重複排除後の容量を実測した値ではない。

## 次に受領する小容量の範囲

展開した Core アセットから以下の 3 フォルダ全体を、名前・大文字小文字・相対パスを保って ZIP にする。今回は小さなリソースの実体照合と内容調査を先に進める目的であり、この範囲だけで起動成功すると保証するものではない。

| フォルダ | manifest にある内容 |
|---|---|
| `Resources/Backstories/` | `Solid/Rare.xml`、`Solid/Requested.xml`、`Solid/PlayerCreated/backstories.xml`、`Solid/PlayerCreated/names.xml` |
| `Resources/Text/` | `Names/First_Female.txt`、`First_Male.txt`、`Last.txt`、`Nick_Female.txt`、`Nick_Male.txt`、`Nick_Unisex.txt` |
| `Resources/Fonts/` | 上記のフォント 5 論理名。手元の展開結果をそのまま受領し、実体とハッシュを調べる |

管理情報 2 ファイルは再送不要。`Resources/Textures/` と `Resources/Sounds/` は削除せず保管し、後段で容量に合わせて受け入れる。ヘッドレスで画面・音を出さないことだけでは、全リソース参照が不要になるとはいえない。画像・音声の必要最小集合はまだ実測できていない。

参考としてテクスチャの論理パス数は `Things/` が 2,721、`UI/` が 544、`World/` が 80、`Terrain/` が 46、`Designations/` が 25、`Other/` が 19、`Weather/` が 10、`Damage/` が 8、直下の placeholder が 2。これは容量順ではない。

Linux 公式実行ファイル・WaylithClr・対応する一式、Core リソース本体、起動時に参照する GLSL の配置・ビルド互換性は引き続き未確認または不足。実行準備は `blocked`、ゲームによる検証は `notRun`。今回のメタデータを部分的なアセット ZIP に詰めて、完全な公式パックとして扱うことはしない。

受領した管理情報の全文やゲームリソース本体は公開せず、集計・入力識別用ハッシュ・診断に必要なパスだけを記録する。

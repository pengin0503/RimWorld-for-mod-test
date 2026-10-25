# Core の小容量リソースの受領結果（2026-10-25）

`Resources.zip` を受領し、`Resources/Backstories/`、`Resources/Text/`、`Resources/Fonts/` を読み取り専用で検査した。元の ZIP、ゲームファイル、受領した manifest は変更していない。今回の公開変更は調査資料・集計 JSON のみで、ゲームのソース・データ・フォント本文は含めていない。

## 受領と整合性

| 項目 | 結果 |
|---|---|
| ZIP のサイズ | 2,145,779 bytes |
| ZIP 全エントリ | 33 件、CRC 不一致なし |
| 実リソース | 13 ファイル、合計 5,841,914 bytes |
| manifest との SHA-256 照合 | 13 ファイルすべて一致、不一致 0 |
| パス | ディレクトリ・Mac 補助項目を除く実ファイルのパス重複、不正な上位パス・絶対パス、シンボリックリンクを検出せず |

ZIP 自体の hash と形式検査の集計は [JSON](core-small-resources-inventory.json) に記録した。ファイル単位の manifest 照合は実体で確認できたが、Linux や Windows の正規インストール全体とのビルド互換性まで証明するものではない。

## 内容の形式検査

| 範囲 | 件数 | 確認できたこと |
|---|---:|---|
| Backstories | XML 4 個 | ElementTree の構文解析に通過。ゲーム固有の型・参照解決は未検証 |
| Text | TXT 6 個 | UTF-8 として読み出せた。ゲーム内の名前生成は未実行 |
| Fonts | 3 個 | fontTools でテーブルを読み出し、テーブルチェックサムに不一致なし。実際の文字描画・言語別の字形充足は未検証 |

フォントの実ファイルは `Arial_medium.ttf`、`Calibri_tiny.TTF`、`Pretendard-Regular.otf`。manifest 上の `Arial_small.ttf`、`Arial_tiny.ttf` は物理ファイルとしてはないが、受領した `Arial_medium.ttf` の SHA-256 がこれらの manifest 値とも一致した。

したがって、依頼した 15 論理パスに対応する内容を 13 実ファイルで確認した。DLL の同一ハッシュによる別名参照処理は [前の調査](2026-10-25-core-asset-metadata-audit.md) で静的に確認済み。ただし実行時の別名参照、展開フォルダからの読み込み、完全なパックの再構築は試していない。欠けた物理名を自動生成したり、別名参照まで実行成功したと数えたりはしない。

## 現在の状態と次の作業

この 3 フォルダと管理情報 2 個の再送は不要。画像・音声は引き続き未受領だが、Linux 公式実行ファイル・WaylithClr・対応する managed/native 一式もないため、今の状態では起動試験から必要最小集合を絞れない。今回は新たな画像・音声の個別追加送付を求めず、手元で保持してもらう。

受領済みの Windows DLL は本番検証用の Linux ランタイムの代用にはしない。Core の完全なリソース、起動時の GLSL 配置、同一ビルド互換性も未確認事項として残す。実行準備は `blocked`、ゲーム起動・Defs/パッチ/翻訳の読み込み・Harmony は `notRun`。基準起動に必要な範囲は [ファイル一覧](../linux-files-needed.md) を参照。

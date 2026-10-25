# Linux のゲーム一式なしで行う入力検査

Python 3.12 以上だけで使える、入力受け入れの補助 CLI です。外部パッケージの導入は不要です。Windows でも Linux でもゲームを起動せず、入力を抽出・実行・変更しません。

## ZIP の検査

```bash
python tools/audit_inputs.py zip /private/Resources.zip --output /private/resources-audit.json
```

外側 ZIP の CRC、ZIP 自体の SHA-256、危険なパス・リンク・大小文字や Unicode による衝突、直に含まれる XML の構文を確認します。XML の DOCTYPE は拒否します。`__MACOSX/` と `.DS_Store` も CRC のため読み出しますが、リソース数には含めません。

入れ子 ZIP/TAR は中身を検査せず、通常のバイト列として読んで外側の CRC を確認します。画像・音声・フォントのデコード、ゲーム固有の XML 継承・パッチ・参照・翻訳注入も行いません。

manifest との一致を調べる場合、必要な範囲を指定できます。

```bash
python tools/audit_inputs.py zip /private/Resources.zip --manifest /private/bake.manifest --scope Resources/Fonts/ --scope Resources/Text/ --scope Resources/Backstories/ --output /private/resources-audit.json
```

`--scope` は manifest の要求パスを絞るもので、ZIP の CRC 検査対象は絞りません。scope を省略すると manifest 全体を要求します。scope は末尾 `/` のディレクトリを指定し、大文字小文字は区別します。ZIP 内のラッパーフォルダを自動で取り除いたり、ファイル名を推測で修正したりはしません。

同一内容の別名は、manifest と実ファイルの SHA-256 が一致した内容を基準にカバー数を別集計します。別名ファイルを生成せず、ゲームでその別名を解決できたとは表現しません。manifest にない ZIP ファイルの完全性まで保証する照合ではありません。

## 管理情報の照合

```bash
python tools/audit_inputs.py metadata /private/bake.manifest /private/textures.info --output /private/metadata-audit.json
```

manifest の各行がパスと 64 桁の 16 進ハッシュ値、textures.info がパスと整数 6 個の形式かを調べ、重複とテクスチャのパス集合の不一致を検出します。整数 6 個の意味や、記録された実体の存在を検証する機能ではありません。

## 結果と上限

JSON の `auditStatus` とゲームの結果を区別してください。

| auditStatus | CLI 終了コード | 意味 |
|---|---:|---|
| `passed` | 0 | 依頼された範囲の静的検査で問題を検出せず |
| `failed` | 1 | 入力・XML・照合・出力などで確定したエラーあり |
| `incomplete` | 2 | 未対応圧縮、ファイル名の符号化の不確かさ、読出し上限などにより検査が不完全 |

**`gameVerification` は常に `notRun` です。** CLI 終了コード 0 は Core の起動、MOD の動作、Harmony の適用、完全なインストールを証明しません。確定エラーと未検査部分が併存する場合は `failed` と診断・coverage の両方を確認します。コマンド構文の誤りは argparse の標準エラー・終了コード 2 です。

ZIP の既定上限は、単一エントリ 256 MiB、展開後の累積読出し 512 MiB、総エントリ 100,000 件、診断 200 件。累積読出しには Mac 補助データも含まれます。診断の省略数を報告し、省略して合格へ戻すことはありません。`--max-entry-mib`、`--max-total-mib`、`--max-entries` で正の上限へ変更できます。manifest と textures.info はそれぞれ 16 MiB までです。

対応する圧縮方式は Stored と Deflate です。ZIP の宣言サイズでデータが切り捨てられないよう、圧縮データの終端・実際の展開サイズ・CRC を独立して照合します。暗号化、LZMA、Bzip2、method 93（Zstandard）などは直接読む場合 `incomplete` となり、破損と決めつけません。これらのデコーダーはこの初版に含めません。

上限は厳密なプロセスメモリ・CPU 制限ではありません。ZIP 中央ディレクトリは標準 zipfile で読み、圧縮入力自体の SHA-256 も走査するため、実行環境側の資源制限が必要な入力は別途扱ってください。

`--output` を省略すると JSON を標準出力へ返します。標準出力では非 ASCII 文字を JSON の Unicode エスケープで表し、Windows などの出力文字コードに依存せず読み取れるようにします。指定時は UTF-8 で同一ディレクトリの一時ファイルから置き換えます。入力自身・入力を指す symlink/hardlink を出力に指定すると拒否します。結果にはファイル名・診断パスが含まれるため、個人プロファイルの結果を無確認で公開しないでください。

## テストと CI

```bash
python -m unittest discover -s tests -v
python -m compileall -q tools tests
```

CI は Ubuntu/Windows と Python 3.12/3.13 で、自作の小さな ZIP/XML/manifest fixture だけを検査します。ゲームファイルを取得したり、結果・入力を artifact としてアップロードしたりはしません。

受領済みの実ファイルで確認した結果は [今回の実行記録](research/2026-10-25-offline-cli-validation.md) を参照してください。

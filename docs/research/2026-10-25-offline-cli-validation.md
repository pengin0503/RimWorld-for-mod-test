# 入力監査 CLI の実ファイル確認（2026-10-25）

Linux のゲーム一式を待たず、再利用できる入力監査 CLI を実装した。[使用方法](../offline-input-audit.md) に範囲と制約を記載している。実行結果の JSON 本体は非公開の作業領域へ保存し、ここには集計だけを記録する。入力は変更していない。

| 入力 | auditStatus / 終了コード | 実行結果 |
|---|---|---|
| `Resources.zip` ＋ manifest の Fonts/Text/Backstories | `passed` / 0 | 全 33 エントリの CRC、13 実ファイル、XML 4 個、manifest の 15 論理パス分を確認。別名分は 2 |
| `bake.manifest` ＋ `textures.info` | `passed` / 0 | manifest 5,907 項目、テクスチャ 3,455 項目、パス集合一致、異なるハッシュ値 5,868 個 |
| `Rim_data_1.zip` | `incomplete` / 2 | 全 4,084 エントリの CRC、実ファイル 1,878 個、直に含まれる XML 1,050 個を確認。非 ASCII 名の ZIP UTF-8 フラグ不足を診断 |
| `Rim_data_3.zip` | `incomplete` / 2 | 全 623 エントリの CRC、実ファイル 270 個、直に含まれる XML 250 個を確認。同じ符号化の問題を診断 |
| `Rim_data_2.zip` | `incomplete` / 2 | 全 435 エントリの CRC、実ファイル 185 個、直に含まれる XML 163 個を確認。同じ符号化の問題を診断 |

Data の符号化の問題は [以前の追加調査](2026-10-25-split-data-audit.md) で確認したものと整合する。ファイル名を推測で修正せず、不完全な入力受け入れとして報告する。

この CLI は入れ子 ZIP/TAR の中身までは検査しない。以前の個別調査で読み出した DLC アセット ZIP と翻訳 TAR、ポーランド語翻訳の既知の構文エラーを、CLI が再検査したとは数えない。

すべての JSON で `gameVerification=notRun` を確認した。ゲーム起動、Defs の参照解決、翻訳注入、Harmony の実行検証は行っていない。headless ランチャー・観測 MOD は引き続き未実装。

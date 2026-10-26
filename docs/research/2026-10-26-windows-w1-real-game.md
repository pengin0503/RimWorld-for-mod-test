# Windows W1：実ゲームでの確認

日付：2026-10-26。ユーザーが自分の PC で、[手順書](https://claude.ai/artifact/UgcJxTU4WGXY7TByA9UYew)どおりに実行した結果です（ブランチ `claude/project-thread-7ks67d`）。**Windows はまだ適格化していません。** 下の結果はすべて `experimental`（全体は `incomplete`）で、Linux の結果との比較記録です。

## 構成

- Windows x64、RimWorld 1.7.4985 rev1269（Steam の正規版）、同梱 WaylithClr。公式コンテンツは Core・Royalty・Ideology・Biotech・Odyssey。
- `prepare-game`：3,816 ファイル・1.53 GB を 68 秒で複製し、ハッシュを記録。
  - 認識結果は `buildPlatform=windows-x64`、Adapter は `rimworld-1.7.4985-rev1269`。
  - managed のゲーム DLL のハッシュが Linux 版と一致したので、Adapter が一致した。
- `RimWorld.deps.json` の runtimeTarget は `.NETCoreApp,Version=v10.0/win-x64`。
- `RimWorld.runtimeconfig.json` の SHA-256 は `1cddd167…78fd9` で、Linux 版と同一。
- ゲーム直下の構成は `BUILD_FILES['windows-x64']` の想定どおり（`RimWorld.exe`・`hostfxr.dll`・`coreclr.dll` など）。

## 結果

| 確認 | 件数 | 期待どおり | Linux との違い |
|---|---|---|---|
| fixture 行列（A/B/マップ、WaylithClr と標準 .NET） | 22 | 22 | 判定の理由（`experimental`・`mapNotQualified` を除く）は全ケースで同じ。差は下の 2 点だけ |
| C の自作 fixture（`bill-ingredient-options.v1`） | 6 | 6 | 段階・理由コードは同じ |

違いが出た 2 点：

1. **マップ生成後の終了時メッセージ**：「Persistent allocation … was not freed before shutdown.」が、Linux より多く出た。サイズ別に数えると、Windows では十数種類が各 12 回ほど増えている。どれもエンジンの終了処理の既知のメッセージ（`KNOWN_NOISE`）で、判定からは外れており、判定結果は変わらなかった。
2. **標準 .NET（`standard-runtime-ok`）**：比較に使った Linux の実行では `ProfilerBootStart` の静的コンストラクタのエラーが新規エラーになっていた。Windows では新規エラーなし。どちらも期待どおり `incomplete`（標準 .NET は常に experimental）。原因は調べていない。

処理時間は Linux の 1.0〜1.5 倍ほど（例：`ok` は 10.7 秒 → 14.2 秒）。

## 分かったこと

- W1 の実装（ハードリンクとジャンクションの実行ディレクトリ、Job Object による監視、Windows の環境変数）は、実ゲームで A/B/マップ/C を Linux と同じ判定に導いた。
- これは「Linux と同じ fixture で同じ結果になった」という記録です。公式の Windows 版と比べたものではないので、Windows の適格化にはまだ使えない。適格化には、Linux と同じく公式 `RimWorld.exe` の headless との比較が要る（Windows で使えるかは未確認）。
- 小麦粉 MOD など実 MOD の Windows 実行、描画（W3）は、まだ行っていない。

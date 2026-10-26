# Windows 版：設計（W1 実ゲーム実行）

日付：2026-10-26。状態：2026-10-26 ユーザー承認。W1 実装済み（実ゲーム未確認）。

## 前提（ユーザーの指示と保存済みの方針）

- Linux 版は AI 用で、描画しない。Windows 版はユーザー自身が使い、本家に似た GUI を持ち、実画面の描画も担う（2026-10-25・26 の指示）。
- 検証専用で、遊べる機能は作らない。Linux での合格を Windows の合格と読み替えない。
- 2026-10-26 08:43：Linux の作業のあと、Windows 版に取り掛かるよう指示があった。

## 分割

Windows 版は独立した 3 つの段階に分ける。各段階に、それぞれ設計と承認を用意する。

| 段階 | 内容 | 依存 |
|---|---|---|
| **W1 実ゲーム実行（この文書）** | 今の `validation_host.py run` を Windows x64 で動かす。要求と結果の形式は Linux と同じ。描画しない | なし |
| W2 GUI | 本家に似た画面で、MOD と検証内容を選んで W1 を実行し、結果を見る。既存の事前検査 GUI を置き換える | W1 |
| W3 実画面の描画 | 製造指示の画面などをゲーム自身に描画させて画像を残す。C の非描画判定と比べることで、C を適格化する | W1 |

## 方式の比較（W1）

1. **推奨：今の Controller（Python）と Worker（C#）を Windows に対応させる。** 契約・判定・テストを Linux と共有できる。差分は OS 依存の部分（実行ディレクトリ、プロセス監視、パス）だけに閉じる。
2. Windows 用の Controller を C# で作り直す。判定ロジックが二重になり、Linux と結果が食い違う危険がある。
3. Windows 上の WSL で Linux 版を動かす。それは Windows の結果ではないので、目的を満たさない。

## 確認済みの事実

- R2 の直下にある Windows 版（1.7.4985 rev1269）は、`RimWorld.runtimeconfig.json` が Linux 版と同一だった（WaylithClr 10.0.13-waylithclr.dev、設定値も同じ）。`RimWorld.deps.json` の runtimeTarget は `win-x64`。
- Worker は Linux 上で `-r win-x64` を指定してビルドでき、`RimWorldValidationWorker.exe`（apphost）が生成された。
- managed のゲーム DLL は、以前の照合で Windows 版と Linux 版がバイト単位で一致している。

## W1 の設計

### 入力

ユーザーの PC にある正規の Windows 版を、既存の `prepare-game` で読み取り専用のスナップショットに複製する。Steam のフォルダを直接は使わない。R2 直下の Windows 版は、Adapter の照合値（ファイルのハッシュ）を作るためだけに使う。

### 変更点

1. **プラットフォーム判定**：`windows-x64` を許可する。Adapter に Windows 版の照合値を追加する。照合するのは managed DLL と、`coreclr.dll`・`System.Private.CoreLib.dll` など実行環境のファイル。適格化の対象は `('windows-x64', 'waylith')` として別に記録し、Linux の qualified を流用しない。
2. **実行ディレクトリ**：Windows のシンボリックリンクには管理者権限か開発者モードが要るので、使わない。ゲームのファイルはハードリンクにし、別ドライブなど作れない場合だけ複製する。公式コンテンツのフォルダはディレクトリジャンクションにする。スナップショットの改変は、既存の照合で検出する。
3. **Worker**：`win-x64` の apphost を使う。deps.json の書き換えは、Linux と同じ手順を runtimeTarget に合わせて行う。
4. **監視**：Job Object（ctypes、標準ライブラリだけ）を使う。
   - 子プロセスが残らないよう、KILL_ON_JOB_CLOSE を設定する。
   - ジョブのメモリ上限（JOB_MEMORY）で、**ハードな上限**をかける。結果は `memoryHard=true` で、Linux の未実装分を Windows では満たせる。
   - 時間切れは TerminateJobObject で止める。ピークメモリはジョブの集計から取る。
   - Worker は停止状態で起動し、ジョブに割り当ててから再開する（`CREATE_SUSPENDED` → `AssignProcessToJobObject` → `NtResumeProcess`）。起動から割り当てまでの隙間は、これで閉じる（実装時に、Worker 側の確認より確実なこの方式へ変更）。
   - ジョブのメモリ上限に達すると確保が失敗し、Worker は自分で終了し得る。その場合も、ジョブの通知（`JOB_OBJECT_MSG_JOB_MEMORY_LIMIT`）から `killedFor=memoryLimit` と記録する。
5. **環境変数**：`USERPROFILE`・`APPDATA`・`LOCALAPPDATA`・`TEMP`・`TMP` を実行ディレクトリの中に向ける。`SystemRoot` と `PATH` だけを引き継ぐ。R2 の認証情報は引き継がない。
6. **パス**：
   - 長いパスを避けるため、実行ディレクトリは短く保つ。
   - Windows のファイルシステムは大文字と小文字を区別しない。このため、ロードフォルダの選び方が Linux と変わり得る（例：`common` と `Common`）。W1 では `mod_load_plan` は変えず、実ロードとの照合（`loadFolderMismatch`）で食い違いを検出する（実装時の判断。食い違えば incomplete になり、誤った合格にはならない）。

### 適格化

Linux と同じ手順で行う。ユーザーの PC で、公式の `RimWorld.exe` を開発モードの headless で起動し、`compare_official.py` で fixture 行列の結果と照合する。headless が Windows でも使えるかは未確認。使えなければ、何と比べるかをその時点で相談する。適格化が済むまでは、Windows の結果はすべて `experimental` とする。

### テスト

- 公開 CI（windows-latest）で、ゲームファイルなしに次を試す。
  - ゲームのファイル構成を模した偽のフォルダで、実行ディレクトリを作る。
  - 偽の Worker（メモリを使い続ける・子プロセスを作る・終わらない）で、ジョブによる停止、メモリ上限、子プロセスの後始末を確かめる。
- 実ゲームでの確認は、ユーザーの PC で Remote Control を使って行う。fixture 行列、C の fixture、小麦粉 MOD、公式との比較。

### ユーザーに必要なこと

- PC がオンラインのときに、Remote Control の開始を 1 回承認すること。
- PC に Python 3.12 以上と .NET SDK 10 がなければ、導入の可否を判断すること（導入はこちらで行える）。
- Windows 版 RimWorld のフォルダの場所（Steam ライブラリ）を確認すること。

### 範囲外（W1）

GUI（W2）、描画（W3）、macOS、Anomaly。

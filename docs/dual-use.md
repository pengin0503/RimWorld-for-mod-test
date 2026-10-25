# Windows で使う／AI に任せる

このプロジェクトは、Windows の利用者がプレイ前に事前検査する使い方と、Linux 上の AI に同じ事前検査を任せる使い方に対応します。`tools/mod_preflight.py` が共通の検査処理で、画面はその結果を表示する入口です。

**今回利用できるのは静的な事前検査と、結果確認後の明示的な通常起動です。** 公式 headless＋観測 MOD によるゲーム本来のロード検証はまだ実装していません。事前検査を通過しても、ゲーム内での動作や Harmony の適用まで確認できたことにはなりません。

## Windows での使い方

1. Python 3.12 以上を Tcl/Tk と Python Launcher を含めて用意し、このリポジトリのソースを取得します。現段階では単体 EXE 配布ではありません。
2. `Start-Windows.cmd` を開きます。ゲームのフォルダ、保存先、バージョンを指定します。保存先は `Config/ModsConfig.xml` があるフォルダの親です。`Config` 自体や Steam のインストール先と取り違えないでください。
3. Workshop を使う場合は `steamapps/workshop/content/294100` を追加検索先に指定します。ゲーム直下の `Data/` と `Mods/` は自動検索します。
4. 「事前検査を実行」で結果を確認します。問題があれば、普段の方法か AI への依頼で MOD のファイル・構成を修正し、再検査します。ツール自身が MOD を自動修正・ソートする機能ではありません。
5. 通過後に「事前検査済みの構成でゲームを起動」を押すと、構成が変わっていないかを再検査して通常起動を要求します。ゲームの保存先は検査時と同じ `-savedatafolder=...` で指定します。受領 DLL の引数パーサーでは `=` を含む保存先などを正しく表現できないため、その場合は起動要求を拒否します。事前検査だけではゲーム実行時の問題をすべて取り除けないことを確認した上で使います。

プロフィールを JSON に保存すれば次回読み込めます。例は [example.json](../profiles/example.json) にあります。`YOUR_NAME` や Steam ライブラリの場所を実際のものへ置き換えてください。保存するプロフィール・結果はゲーム、保存先、MOD の各フォルダの外へ置きます。ローカルプロフィールには `*.local.json`、結果には `preflight-results/` を推奨し、これらは Git の追跡対象から除外しています。

## AI・CLI での使い方

画面なしで同じ処理を実行できます。プロフィール内のパスは実行する OS 上で存在する場所を指定します。Windows の `C:/...` をそのまま Linux 用のパスとしては使えません。相対パスはプロフィールファイルの親から解決します。

```bash
python tools/mod_preflight.py check --profile profiles/ai.local.json --output preflight-results/check.json
```

JSON の `diagnostics`、`auditStatus`、`coverage` を調べて修正と再検査を繰り返します。`gameVerification` は常に `notRun`。終了コードは `0=事前検査通過`、`1=問題あり`、`2=検査が不完全` です。Linux で AI が事前検査するだけなら Windows 用のゲームファイルをデータとして読むことはできますが、Windows の実行ファイルを Linux で実行する機能ではありません。

`--output` の親ディレクトリは、保護対象の外にあることを確認してから必要に応じて作成します。出力 JSON にはローカルのパスが含まれるので、公開前に内容を確認してください。

Linux のプロフィール例：

```json
{
  "schemaVersion": 1,
  "gameDir": "/private/RimWorld",
  "saveDataDir": "/private/player-profile",
  "modRoots": ["/private/Mods"],
  "gameVersion": "1.7"
}
```

この `saveDataDir` には、検査対象の有効 MOD リストとして `Config/ModsConfig.xml` が必要です。AI が事前検査するためだけにセーブファイルを渡す必要はありません。

検査済みの構成で起動するコマンドを確認するだけなら：

```bash
python tools/mod_preflight.py play --profile profiles/ai.local.json --report preflight-results/check.json --dry-run
```

実際の通常起動を要求する場合のみ、`--dry-run` を `--acknowledge-static-only` に置き換えます。現在の OS に対応した公式名 `RimWorld.exe` または `RimWorld` が必要です。AI による検査では、ユーザーが通常起動を依頼していなければ `check` だけを使います。`launchRequested=true` はプロセスへ起動要求を送った意味で、ゲームの起動成功を証明しません。

## 現段階の検査範囲

| 検査 | 内容・制約 |
|---|---|
| 有効 MOD | Core が先頭、空欄・重複・欠損・曖昧な取得元を検出。フォルダがあるだけの無効 MOD の Defs は検査しない |
| Steam 別名 | `_steam` を持つ識別子は通常名で候補が一意の場合に解決。複数候補から勝手に選ばない |
| メタデータ | supportedVersions、依存、競合、forceLoadBefore/After を確認。通常の loadBefore/After は推奨情報として表示し、並べ替えない |
| ロードフォルダ | ルート・Common・指定した major.minor を基本とする。LoadFolders.xml の明示版、版指定のない default、単一 packageId の IfModActive/IfModNotActive を扱う。バージョンの代替選択や未知の条件は不完全として報告 |
| XML | 選択した Defs/Patches 内の構文。DOCTYPE を拒否。実ゲームのパッチ適用・継承・型変換・参照解決は未実施 |
| DLL | Assemblies 内などの DLL を識別用にハッシュ。ロード・実行・Harmony の適用は未実施 |
| 翻訳・画像・音声 | 今回の事前検査では読み込み・デコード・動作を確認しない |
| 速度 | 経過秒を表示。重い素材の処理を省くが、実ゲームの通常起動との速度差は未計測で、全環境での高速化を保証しない |

ゲームバージョンはプロフィールと ModsConfig・MOD の申告を照合する値で、DLL 内の実ビルドを自動同定する機能ではありません。厳密な互換性は公式 headless の基準試験で確認する工程です。

起動前の再検査ではプロフィール、ModsConfig、索引 About、検査対象の XML/DLL、実行ファイルと主要ゲーム DLL のハッシュを照合します。全リソースの不変性を保証したり、再検査から起動までのファイル変更を完全にロックしたりするものではありません。未検査リソースや実ゲームの問題は残り得ます。

安全上の取り扱いは読み取り専用を基本とし、ファイル数・サイズの上限を設けています。ゲーム・保存先・MOD ディレクトリ内へプロフィールや結果を書き出すことは拒否します。検査は MOD のコードを実行しませんが、「通常起動」では選択した MOD が本物のゲーム上で実行されます。

単一ファイル 64 MiB、累積読み出し 512 MiB、fingerprint 対象 100,000 ファイル、索引対象は各検索先 10,000 子項目までが既定の対応範囲です。画像・音声はこの読み出しに含めません。ディレクトリの読出しエラー、symlink/junction 経由のコンテンツは検査不能として通過させません。プロフィールに明示された MOD 検索先そのものは実パスへ解決します。上限は厳密なプロセスのメモリや CPU の制限ではありません。

## 今後の二段階目

事前検査で明らかな問題を直した後、各 OS の公式実行ファイルと同梱 WaylithClr、検証用 MOD を使って XML の意味・参照・翻訳・Harmony をロード検証する構成に拡張します。その結果と実プレイを分けて扱います。起動中のゲームへ結果を引き継いで二重ロードを避ける機能や、MOD の差分だけをゲーム本来の処理で再ロードする機能は未実装です。

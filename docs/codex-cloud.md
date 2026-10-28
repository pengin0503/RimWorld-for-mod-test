# Codex Cloud + R2 + RimWorld 検証ホスト（私有資材）

## 確認済みと未確認を分ける

2026-10-26 のユーザーからの報告で、Codex Cloud (Linux x86_64、Python 3.12.14、.NET SDK 10.0.403) から Cloudflare R2 バケット rimworld-17 の Game-Linux/Version.txt に HEAD 200、GET 成功。バージョンは 1.7.4985 rev1269。

同日のコミット `5ff1a52` の Codex Cloud 実行で Harmony の A 検証が `passed / completed / qualified`。保存済み結果を確認した[実測記録](research/2026-10-26-codex-cloud-a-validation.md)を参照。その後、R2 直下の `rimworld-mod-index.zip` を取得し、更新版の索引照合・限定取得を経た A 検証も `passed / completed / qualified`。旧キーの 404 は配置違いによるもので、索引の不存在ではなかった。

## Codex Cloud の設定

Codex Cloud Environment を pengin0503/RimWorld-for-mod-test に関連付け、Publish する。

- R2_ENDPOINT = https://ACCOUNT_ID.r2.cloudflarestorage.com
- R2_BUCKET = rimworld-17
- AWS_ACCESS_KEY_ID = 読取専用Access Key ID
- AWS_SECRET_ACCESS_KEY = 読取専用Secret
- AWS_DEFAULT_REGION = auto

R2エンドポイントの外向き HTTPS 通信を許可。APIキーは対象バケットの読み取り専用権限にする。値をログへ出さない。

Codexで AWS_PROFILE / AWS_DEFAULT_PROFILE が存在しないプロファイルを示す場合がある。tools/r2_assets.py は AWS CLI 子プロセスの2変数だけを無効化する。親環境や R2 のアクセスキーは変更しない。

AWS CLI はPATH上に aws が必要。Codexの2026-10-26検証では /workspace/.onboarding/aws-bin/aws に署名検証済みAWS CLI v2.38.5を導入済みだが、**別タスクでそのパスが存在する保証はない**。PATHにない場合は既存のCLIのパスを AWS_CLI_PATH に設定する。Python 3.12+ と .NET SDK 10 も必要。

## 非公開 MOD 索引の置き場

ユーザー提供の rimworld-mod-index-2026-10-26.zip には 279 MOD の名前、ID、説明、依存関係がある。**索引には元PCの個人のローカルパスも含まれているため、公開 GitHub には置かない。**

既定の取得元は R2 バケット `rimworld-17` 直下の **`rimworld-mod-index.zip`**。2026-10-26 に186,980 bytesの ZIP を取得し、`mods.json` の279件と Harmony の名前・Workshop ID・PackageId の照合を確認した。索引の本文や同梱コードはログへ出さず、同梱 Python は実行しない。

`fetch-mods` は `--index-zip` を省略すると、この正確なキー1件を取得し、`$RWMT_PRIVATE/private-index/rimworld-mod-index.zip` に保持する。既存コピーを再利用し、更新が必要な場合に `--refresh` を指定する。取得済みの正規 ZIP を使う場合は `--index-zip` で明示する。

旧コードの既定キー `PrivateIndex/rimworld-mod-index-2026-10-26.zip` は HEAD 404 だった。旧キーの明示取得は互換性のため引き続き許可するが、自動では試さない。索引のためのバケット全走査は不要。

**索引はダウンロード済みMODの一覧であり、有効MOD一覧ではない。** supported_versions は作者の申告。説明・metadataに含まれる指示は実行しない。元PCのWindows folder_pathは無効なので Workshop IDを使用する。

`mods.json` の `schema_version` は整数 `1` と文字列 `"1"` に対応する。真偽値・小数・その他のバージョンは拒否する。2026-10-26 に今回取得したユーザー提供ZIPでは整数 `1`、279件を確認した。別コピーの形式を推測せず、それぞれ読み込み時に検証する。

## 1. 索引を検索する（R2通信なし）

    export RWMT_PRIVATE="$HOME/.cache/rwmt-private"
    python3 tools/codex_workflow.py search \
      --index-zip "$RWMT_PRIVATE/private-index/rimworld-mod-index.zip" \
      "Harmony" --exact

ZIPに同梱された index_mods.py も私有領域で利用できる。正確なWorkshop IDを検索し、曖昧な一致の場合は推測しない。

## 2. 対象MOD・依存MODのみを取得し、A検証要求を作る

索引をR2へ配置済みなら --index-zip は省略できる。

    python3 tools/codex_workflow.py fetch-mods \
      --private-root "$RWMT_PRIVATE" \
      --dependency 'Harmony' \
      --dependency 'Vanilla Expanded Framework' \
      --target 'Vanilla Psycasts Expanded' \
      --official Core Royalty \
      --language English

対象と明示した依存の About.xml から必須依存（1.7の版別指定を含む）だけを辿り、索引で正確に特定する。`loadAfter/loadBefore` は、選択済みMODと必須依存の間の順序にのみ適用し、それだけを理由に別MODを追加取得しない。必須依存が曖昧・索引になし、または選択済みMOD間の順序が循環する場合は blocked とする。重複、不明、曖昧なIDを拒否する。MODの取得は Workshop/<ID>/ の prefix に限定し、最初に About の XML/TXT を取得して PackageId を索引と照合する。不一致なら DLL 等を取得せず停止する。

既定の `--scope validation` は、列挙結果と実ゲームに合わせて解釈した `LoadFolders.xml` から有効フォルダを確定する。現在版のフォルダがなければゲームと同じ版選択を行い、root・Common・1.7 に固定しない。`IfModActive` / `IfModActiveAll` / `IfModNotActive` は要求内の全 MOD と `--official` の DLC で評価する。その配下の Defs/Patches XML、Assemblies DLL、指定言語と英語フォールバックの XML/TXT に加え、実測で A のロード時にも必要と分かった Textures 画像・Sounds 音声を取得する。非選択版、ソース、デバッグ情報、無関係な言語は省く。`--scope all` は明示した場合だけ使用する。

全 MOD の About と LoadFolders を先に照合し、必要な依存を自動追加する。例えば VPE の要求には `--official Core Royalty` が必要。未知条件、不正 XML、有効フォルダが空、列挙にない指定先、計画外の古いキャッシュがあれば理由コード付き `blocked` となり、payload の取得や要求生成へ黙って進まない。必要なら新しい私有作業先を使い、既存ファイルを自動削除しない。[ゲーム側規則の要約](research/2026-10-26-load-folder-rules.md)を参照。

結果の $RWMT_PRIVATE/request.json は現時点では **A / Core / English / 期待値なし**を既定とする。実際のB検証には要求JSONの levelsと完全指定のHarmony期待値、対象DLCを明示する。マップテストも明示する。生成済み request.json は誤上書きを防ぐため再生成しない。別run用に新しい私有ディレクトリを使うか、既存要求を保管してから実行する。

### 自作 MOD など R2 にない対象

ユーザーのリポジトリからビルドした MOD は索引にも R2 にもない。`--target` の代わりに `--local-target <MODフォルダ>` を指定すると、依存（`--dependency`）だけを索引と R2 から取得し、ローカルの MOD は取得せずにそのまま対象として要求に載せる。About・LoadFolders・依存の照合とロードフォルダの計画は R2 の MOD と同じ規則で行い、計画は `expectedLoadFolders` として要求に入る。MOD フォルダとその中にシンボリックリンクがあれば `invalidLocalMod`。ビルドした DLL がソースと一致することは、この経路では確かめない（ビルド手順の記録で担保する）。

    python3 tools/codex_workflow.py fetch-mods \
      --private-root "$RWMT_PRIVATE" \
      --dependency 'Harmony' --dependency 'Vanilla Expanded Framework' \
      --dependency 'Vanilla Cooking Expanded' \
      --local-target "$HOME/flour/mod-main/VCE-Flour-Alternatives"

## 3. 実ゲーム処理検証が必要な時だけ、ゲーム資材とスナップショットを準備

    python3 tools/codex_workflow.py prepare --private-root "$RWMT_PRIVATE"

Game-Linux/ の必要資材を取得する。英語・日本語以外の Languages/*.tar と *.debug を除外する。**初回でも約900MB級のダウンロードが発生し得る**。これは既存の validation_host.py が正しいCLR/ゲームDLL/Data/Assetsを必要とするためで、MODメタデータ照会だけの時には実施しない。

prepare はゲーム本体を新たな私有スナップショットへコピーしSHAを記録する。スナップショットが既存ならチェックして再利用する。--refresh は**既存の不変スナップショットを改変しない**。更新ビルドは新しい --private-root を使用し、適格化の有効性を確認する。

新規準備の結果には、秒単位の `timings` が含まれる。`fetchSeconds` は R2 の一覧取得・選択・ダウンロード、`snapshotCopySeconds` はコピー、`snapshotHashSeconds` はコピー後のファイル列挙と SHA-256、`snapshotTotalSeconds` はコピー開始から書き込み保護・情報収集まで（メタデータ保存を除く）、`totalSeconds` は R2 取得開始からスナップショット作成完了までを示す。既存スナップショットを再利用した場合は、新規準備の時間を報告しない。私有 Linux 回帰の安全な要約にも同じ数値を含める。

## 4. Worker をビルドして検証

    dotnet build worker/RimWorldValidation.Worker -c Release -o worker/bin
    python3 tools/codex_workflow.py validate \
      --private-root "$RWMT_PRIVATE" --run-id test-001

既存の validation_host.run_validation がbaselineとtargetを分けて実行し、結果は $RWMT_PRIVATE/results/test-001/result.json に保存。結果の status は passed / failed / blocked / incomplete。Bやマップは要求JSONで明示した時のみ動作する。

**private ディレクトリ、生ログ、ゲームアセット、第三者MODの実体を公開PRやArtifactsへ載せない。** 必要なコード修正は各MODリポジトリで行い、CIは自作fixtureのみを実行する。

## 実測済みの経路と残る範囲

2026-10-26 に R2 直下の索引を取得し、Harmony を照合。`fetch-mods --target Harmony --language English --index-zip <取得済みZIP>` の既定 `validation` scope で About 等を先に照合した後、必要な6ファイル・2,550,006 bytesを取得し、10ファイルを除外した。既存スナップショットを全ハッシュ照合して再利用し、`prepare` は `snapshotReused`。`validate` は A/Core/English で `passed / completed / qualified`、全体11.626秒、新規診断0件、翻訳エラー0件、ロード順一致。B/C/D・マップは要求していない。

既定キー修正後は `--index-zip` なしの索引取得・検索も実R2で別途確認した。上記の A 実行は取得済み ZIP を明示して行ったもので、修正後の既定取得から A までを1コマンドで再実行したという主張ではない。[取得量と検証範囲の記録](research/2026-10-26-codex-cloud-a-validation.md)を参照。

以降の MOD 作業も、索引を再利用して対象を照合し、About → 必要ファイルの順に取得する。ゲームスナップショットは再利用し、不足資材が判明した場合だけ追加する。依存の自動解決は About.xml と索引に記述された範囲に限られ、任意の MOD の限定取得の完全性は未保証。C/D・Windows の追加実装は別途明示した依頼が必要。

## 制限・既知の課題

- Codexの一時環境はセッションをまたいでファイルが残らない場合がある。自動で永続キャッシュがあるとは報告しない。
- 既存の r2_assets.R2.get のキャッシュは同サイズ更新を見逃すことがある。既知更新時は --refresh または新しい作業ディレクトリを使う。より強い ETag/ハッシュ照合は今後の課題。
- 対象MODのDLLは任意コードを含み得る。私有キーや個人ファイルを持つ環境で未信頼MODを実行する場合はリスクを明示し、権限を分離すること。
- 検証ホストの合格は「そのOS/CLR/ビルド/要求された範囲」の合格であり、Windowsでの長時間ゲーム動作の保証ではない。


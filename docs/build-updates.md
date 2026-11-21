# ゲームの更新への追従（RimWorld 1.7 系）

RimWorld を新しいビルドに更新しても、1.7 系（`1.7.<build> rev<revision>`）ならコードを変えずにそのまま検証できます。ただし、そのビルドの結果を `qualified` と扱うのは、公式ゲームの**同じビルド**と自動で比べてすべて一致したときだけです（ユーザーの決定、2026-11-21）。版番号だけで適格にはしません。

## 自動で行われること

| 場面 | 動作 |
|---|---|
| 版の判定 | ゲームの `Version.txt` を読む。1.7 系なら `game.family=rimworld-1.7` の Adapter が自動で付く。1.8 など別の major.minor・読めない版は `unknownBuild` で `blocked` |
| Worker | ゲームの型・メンバーを毎回リフレクションで結び付けてから起動する。使うメンバーが本当に変わったビルドでは、起動前に `adapterMismatch` で名前つきで止まる。ビルドにだけある起動工程（1.7.5014 の Prepatcher 互換層など）は、そのビルドにあるときだけ公式と同じ順で行う |
| 適格の判定 | そのビルドのファイル（`Assembly-CSharp.dll` など 5 個の SHA-256）と一致する適格記録を探す。リポジトリの記録（レビュー済み）→ 私有の自動比較の記録（比較に使った Worker のビルドに限る）の順。なければ `experimental`（全体は `incomplete`） |
| ゲームの取得（`codex_workflow.py prepare`） | 所有者のアップロード記録（`_manifests/game-linux/source-provenance.json.gz`）にあるファイルだけを取得し、全部の SHA-256 を照合する。前のビルドの残り（1.7.5014 では 4 件）は取らない |
| MOD の計画（`fetch-mods`） | ロードフォルダと依存を、準備済みのビルド（なければ R2 の `Version.txt`）の規則で計画する |
| ベースラインのキャッシュ | 鍵にスナップショットの fingerprint（全ファイルの SHA-256）と Worker の SHA-256 を含むので、ビルドが変われば別のキャッシュになる |

結果の `game` に、版・`family`・`qualificationRecord`（根拠の記録。なければ `null`）・`qualificationNotes`（記録を使わなかった理由）が出ます。

## 新しいビルドが来たときの手順

1. **準備**：新しい私有の作業先で取得とスナップショット作成を行う（スナップショットは不変なので、前のビルドの作業先は使わない）。

   ```bash
   python3 tools/codex_workflow.py prepare --private-root "$HOME/.cache/rwmt-private/game-<build>"
   ```

   出力の `qualification.state` が `reviewedRecord`（リポジトリの記録で適格）なら、ここで終わり。`notQualified` なら次へ。`gameSource` に、アップロード記録で除いたファイルと照合の結果が出る。

2. **Worker をビルド**：`dotnet build worker/RimWorldValidation.Worker -c Release -o worker/bin`。同じ .NET SDK でソースが同じなら、Worker の DLL は同じバイト列になる（コミット ID を埋め込まない設定。私有の記録はこの SHA-256 に結び付く）。

3. **自動比較**（開発用。公式実行ファイルは `experiments/official-comparison/` の比較の中でだけ、使い捨ての HOME で起動する）：

   ```bash
   python3 experiments/official-comparison/qualify_build.py \
     --snapshot "$HOME/.cache/rwmt-private/game-<build>/game-snapshot" \
     --harmony-dll <Lib.Harmony net10.0 の 0Harmony.dll> \
     --out "$HOME/.cache/rwmt-private/qualify-<build>" \
     --store "$HOME/.cache/rwmt-private/qualifications"
   ```

   次を順に行い、一致した段階の分だけ記録に書く。行列か A/B が違えば何も与えない。マップと tick は互いに独立で、違った段階の分だけを与えない。

   | 段階 | 内容 | 与えるもの |
   |---|---|---|
   | 行列 | `tests/integration/run_fixture_matrix.py` の全ケースが想定どおりの判定と理由 | （A/B の前提） |
   | 公式 A/B | 公式の `-headless -QuitAfterBoot` と、エラー・警告・プローブの観測が全ケースで同一 | `levels: A, B` |
   | マップ | 公式の `-quicktest` と、繰り返し実行の分布として同等（`--map-repeat`、既定 5） | `features: map` |
   | tick | D の実ゲーム受入（`run_bounded_tick.py` の 10 ケース）と D v2 の確認（`run_bounded_tick_v2.py`）。1.7.4985 と同じ根拠。公式 tick ループとの独立比較（`compare_ticks.py`）も行うが、情報として記録するだけ（どのビルドでもまだ一致していない） | `experimentalFeatures`（D は常に実験） |

   一致すれば記録が `--store` に入り、`--out/committed-qualification.json` に Worker の SHA-256 を除いた写しができる。一致しなければ `--out/qualification-failed.json` にどの段階が違ったかが残り、結果は実験のまま。所要時間の目安は「記録があるビルド」の表を参照。

4. **私有の記録で使う**：同じ Worker のビルドで `RWMT_QUALIFICATION_STORE=$HOME/.cache/rwmt-private/qualifications`（または `validation_host.py run --qualification-store`）を付けて実行すると `qualified` になる。Worker を作り直すと私有の記録は効かなくなる（未レビューのため）。

5. **恒久化**：`committed-qualification.json` を `validation-data/<build id>/qualification.json`（例 `1.7.5014-rev1195`）として PR を作る。レビューしてマージすると、以後のどのセッション・Worker でもそのビルドが `qualified` になる。記録の形式は `tools/game_builds.py` が検査し、公開 CI のテストも読み込みを確かめる。記録にゲームのファイルそのものは入らない（SHA-256 と比較の要約だけ）。

自動比較が一致しなかったとき：`qualification-failed.json` と `--out` の各ログ（私有）を見て、Worker の結び付け・起動工程の違いを調べる。直したら Worker を作り直し、3 からやり直す。版番号を書き換えて通すことはしない。

マップ段の注意：今の判定方法（製品 5 回の中央値が、公式 5 回の最小〜最大を公式の幅だけ広げた範囲にあるか）は、公式と同じ挙動でも 1 回の比較のうち約 3 回に 1 回、どれか 1 指標が範囲外になる見込みです（[1.7.5014 の記録](research/2026-11-21-build-1.7.5014.md#マップの比較)）。外れたときに同じ基準で比べ直し、通った回だけを採ることはしない（結果を選ぶことになる）。マップを適格にするには、判定方法を見直してから改めて比べる。

## 自動では追従しないもの

- 別の major.minor（1.8 など）：ローダーや API が変わり得るため `unknownBuild`。`tools/game_builds.py` の `FAMILIES` に足す前に、Worker と計画の規則を確かめる。
- 内蔵の知識パック（`static-preflight`）：`validation-data/1.7.4985-rev1269/` だけ。後続ビルドの知識パックは、シンボルをそのビルドで確かめてから別に作る（[内蔵検証データベース](knowledge-database.md)）。
- C の静的参照監査（`tools/private_static_audit.py`）：1.7.4985 のファイルに固定。新しいビルドでは入力の照合で止まる。C の参照をそのビルドで確かめ直すまで固定のまま。
- C（指定動作）・D（tick）の適格化：ビルドによらず未完了（D は記録の `experimentalFeatures` で動かせるだけ）。
- Windows：凍結中（2026-10-27）。

## 記録があるビルド

| ビルド | 方式 | A/B | マップ | D（実験） | 根拠 |
|---|---|---|---|---|---|
| 1.7.4985 rev1269 | 手作業（2026-10-25） | 適格 | 適格 | v1・v2 | [適格化](research/test-host-qualification.md)、[マップ](research/map-qualification.md) |
| 1.7.5014 rev1195 | 自動（2026-11-21） | 適格（行列 23/23、公式 10/10） | 実験（4 ケース中 3 ケース同等） | v1・v2（受入 10/10、v2 3/3） | [1.7.5014 の記録](research/2026-11-21-build-1.7.5014.md) |

自動比較の所要時間（1.7.5014、クラウドの 1 コンテナ）：行列 約 5 分、公式 A/B 約 4 分、マップ（5 回ずつ）約 12 分、D 約 10 分（受入 約 6 分、v2 約 1 分、情報用の公式 tick 比較 約 3 分）。全体で 1 回 約 30 分。

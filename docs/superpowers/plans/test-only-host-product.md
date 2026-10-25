# 検証専用ホスト：製品実装計画と実施状況

日付：2026-10-25。前提：[仕様](../specs/2026-10-25-test-only-host-design.md)、[成立性調査計画](2026-10-25-test-only-host.md)。成立性は Linux x86_64＋WaylithClr＋1.7.4985 rev1269 で確認済み（[呼出し経路](../../research/test-host-entrypoints.md)、[依存](../../research/test-host-dependencies.md)、[適格化](../../research/test-host-qualification.md)）。本計画はその成立範囲だけを製品にする。

**判断：主案（独立ホストからゲーム DLL を呼ぶ）は Linux で成立。進める。** Windows の実行と C/D は成立未確認のため、製品では `blocked` を返す。公式実行ファイルへの切り替えは行っていない。

## 構成

| ファイル | 責務 | 状態 |
|---|---|---|
| `tools/validation_host.py` | Controller。`prepare-game`（私有スナップショット、SHA-256、読み取り専用、Adapter 判定）と `run`（要求検証→blocked 判定→ベースラインと対象の run ディレクトリ→監視→判定→`result.json`） | 実装済み |
| `worker/RimWorldValidation.Worker/` | Worker（C#、net10.0）。`GameApi`（リフレクション束縛）、`Host`（有限な起動手順と結果）、`Diagnostics`（JSONL、上限付き）、`Checks`/`MemberPath`（A の期待値）、`HarmonyInspector`（B） | 実装済み |
| `docs/contracts/mod-validation-v1.md` | 要求・結果・判定・終了コード | 作成済み |
| `tests/test_validation_host.py` | ゲーム不要のテスト。偽 Worker と合成スナップショットで、判定表・上限・子孫停止・改変検出・キャッシュ・blocked 条件 | 作成済み（公開 CI） |
| `tests/integration/run_fixture_matrix.py` | 私有の実物テスト。自作 fixture 16 ケース | 作成済み（私有環境のみ） |
| `tests/fixtures/validation-mods{,-src}/` | 自作 fixture（XML と C# ソースのみ。DLL はテスト時にビルド） | 作成済み |
| `experiments/official-comparison/`、`experiments/performance/` | 開発用の比較・測定。公式実行ファイルを使うのはここだけで、製品から呼ばない（テストで確認） | 作成済み |

## 実行の流れ（`run`）

1. 要求を厳格に検証（未知フィールド拒否、A 必須、B の期待パッチ形式、上限範囲）。
2. blocked 判定：出力先、プラットフォーム（linux-x64 のみ）、C、Worker の有無、スナップショット照合（全ファイルのサイズ、識別ファイルの SHA-256、選択した公式フォルダの余分なファイル。`--verify-full` で全再ハッシュ）、公式コンテンツ・言語、Adapter、MOD（About、packageId、重複、シンボリックリンク、合計 4 GiB）、B の Harmony 同梱。
3. fidelity：Adapter の `qualified` 表に platform×runtime と要求レベルが含まれ、ランタイムのハッシュも一致する場合だけ `qualified`。
4. ベースライン（対象 MOD を外した同じ構成）と対象を、それぞれ新しい run ディレクトリと新しい Worker で実行。ベースラインは同一入力ならキャッシュ可（キーはゲーム fingerprint、Worker、ランタイム、公式、言語、上限、各 MOD の内容ハッシュ）。
5. run ディレクトリ：`host/`（スナップショットへのシンボリックリンク。公式実行ファイル・deps・runtimeconfig は除外、`Data/` は要求したフォルダだけ、`Mods/` はコピー後にハッシュ照合）、`userdata/`（`ModsConfig.xml`、`Prefs.xml`、ログ、キャッシュ）、専用の HOME/XDG/TMPDIR。
6. 監視：新しいプロセスグループ、stdin なし。時間・グループ RSS・ログ量をポーリングし、超過で SIGKILL。終了後に残った子孫も停止。`DOTNET_GCHeapHardLimit` も設定。
7. 判定は [契約](../../contracts/mod-validation-v1.md) の順序。

## テストと検証の結果（2026-10-25）

- 公開 CI 相当：`python -m unittest discover -s tests` 88 件成功（Linux 実行テストは Windows では skip）。Worker は警告をエラー扱いでビルド成功。
- 私有の実物行列：16 ケース全て想定通り（[適格化](../../research/test-host-qualification.md)）。
- 公式 headless との比較：9 ケースでエラー/警告と読込結果が一致（同上）。
- 時間：[性能](../../research/test-host-performance.md)。

## 残りのタスク

- [x] 実際の MOD での検証：Harmony 3.0.1 と Vanilla Expanded Framework で実施（[実 MOD 検証](../../research/real-mod-validation.md)）。ほかの MOD は今後。
- [ ] 既知の無害な警告を除外する規則（ビルド・範囲・根拠付き）。現在は全ての新しい警告で failed。
- [ ] Windows の Worker 実行（apphost .exe、パス、Job Object によるメモリ上限）と、Windows での公式比較による適格化。現在は `blocked`。
- [ ] Windows 画面からの `run`。既存の画面は静的検査のみ。
- [ ] C：指定動作テストの interface（テスト ID、上限、実メソッド呼び出し）。D は別計画。
- [ ] cgroup によるハードなメモリ上限（利用可能な環境のみ。現在はポーリングで `memoryHard=false`）。
- [ ] 入力 ZIP の展開を Controller に入れるか判断（現在は展開済みフォルダが入力）。

## 撤去した機能

- `tools/mod_preflight.py play` と `launch_command`：削除。`play` は移行エラー（終了コード 1）を返すだけ。
- `tools/preflight_gui.py` のゲーム起動ボタンと起動処理：削除。
- 静的検査の公式実行ファイル必須条件：撤去（存在すれば fingerprint にのみ使う）。

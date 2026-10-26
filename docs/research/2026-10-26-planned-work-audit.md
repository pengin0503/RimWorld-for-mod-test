# 既存計画の未実施作業の棚卸し

確認日：2026-10-26。ユーザーの「既に計画されていて未実施の作業を調べ、報告後に行う」という依頼に基づく。新しい機能を完了扱いにせず、具体的な実装計画、条件付きの残作業、将来構想、古い記録を区別する。

## 調査対象と結論

| 既存資料 | 照合結果 | 今回の対応 |
|---|---|---|
| `2026-10-25-offline-input-audit.md` | Task 1–3 は実装済み。一つの別名・改変の組合せ回帰テストが明示的に保留 | その保留テストを追加・実行した |
| `2026-10-25-dual-use.md` | 実施済み旧計画。通常起動の部分は後続仕様で撤去済み | 旧機能を再実装しない |
| `2026-10-25-test-only-host.md` | 冒頭に Linux Task 1–5 実施済みの追記あり。本文の未チェック欄は計画時点の写し | チェック欄だけを根拠に同じ調査・実装を繰り返さない |
| `test-only-host-product.md` | Windows 実ゲーム・GUI、C interface、cgroup hard limit が未完了 | 環境・仕様の前提を確認し、未完了のまま明示 |
| `2026-10-26-effective-load-folders.md` | 全 Task の実装・合成テスト・実 MOD の限定/全取得 A 比較は実施済み | [比較記録](2026-10-26-limited-fetch-parity.md)と照合。再ダウンロード・再実行不要 |
| `finished-product.md` | マップ生成「実物未検証」「PR #6 draft」の記述が古い | 実施済みの適格化記録と GitHub のマージ状態に合わせて更新 |

GitHub の open PR は #8（R2 取得）と #9（Codex 統合）。open Issue は0件。PR #6 は closed/merged で、[マップ適格化記録](map-qualification.md)に公式 quick test との反復比較がある。Windows の単体テスト・ビルド成功を Windows の実ゲーム検証とは扱わない。

## 実施した保留テスト

`tests/test_audit_inputs.py` に `test_present_corrupted_file_is_not_covered_by_valid_alias` を追加。合成 ZIP と manifest だけを用い、正常な `a.ttf` と同じ内容を要求される `b.ttf` が物理的に存在するが改変されているケースを検査する。

- `auditStatus=failed`、改変されたパスの `hashMismatch` を確認。
- 物理一致1件・内容カバー1件・別名カバー0件。正常な別名があるという理由で、改変ファイルをカバー済みと数えない。
- `gameVerification=notRun`、元 ZIP のバイト列不変。
- 製品コードは既に正しかったため変更なし。別名判定から「当該パスが物理的に存在しない」という条件を外した関数をメモリ上だけで作り、このテストが失敗することを確認した。これは意図した変異検査で、失敗するコードをコミットしていない。

ゲーム・索引・MOD の取得や実行はこのテストに不要で、R2 通信も行っていない。

## 条件付きで未実施の作業

### cgroup hard limit

Cloud の実行環境は Linux x86_64。`/proc/self/cgroup` は cgroup v2、`/sys/fs/cgroup/cgroup.controllers` に memory がある一方、マウントは `cgroup2 ro,nosuid,nodev,noexec,relatime,nsdelegate`。この環境内で管理可能な子 cgroup を作って `memory.max` を設定するための書込可能な委譲先は確認できない。

従ってハード上限の実装・実測を完了とはしない。ホストや上位 cgroup の制限を変更せず、既存のポーリングと `DOTNET_GCHeapHardLimit` をそのまま維持し、結果の `memoryHard=false` も変更しない。委譲された書込可能な検証用 cgroup のある Linux 環境が実動作検証の前提。

### Windows

Worker 実行、Job Object、Windows での公式比較、検証 GUI の実処理接続が未実施。現在の実行環境は Linux であり、Windows runner の公開 CI は自作テストとビルドのみ。私有ゲーム資材を公開 CI に渡して代用しない。

### C / D

C はテスト ID・上限・有限な実メソッド呼出しの interface という方針までで、製品コードは未実装。今回ユーザーは、以前の小麦粉代替 MOD で発生した「必要な材料がクラフト画面に表示されない」不具合を例に、他 MOD でも同様の欠落を検出したいと明確化した。対象例は `pengin0503/rimworld-VCE-Flour-Patch` と確認済み。イベント・クエストについても、発生することだけでなく、選択肢を選んだ後の動作が意図どおりかを確かめたいという要求がある。

データに材料があることと、画面の候補として現れることは別。私有 DLL の `Dialog_BillConfig.DoIngredientConfigPane` → `ThingFilterUI.DoThingFilterConfigWindow` → `Listing_TreeThingFilter` の表示判定を調査した。小麦粉 MOD の既存ソースにも、材料の許可と UI の特殊フィルターでの非表示が食い違う回帰ケースがある。これを既存ホストが C 検証できるとはまだ主張しない。

ユーザーは Linux では描画せず、Windows 版で実画面を描画する方針を明示した。Linux で表示候補・許可状態を検査することと、描画・見切れ・レイアウトを確認することは区別する。[最初の C ケースの設計案](../superpowers/specs/2026-10-26-crafting-material-options-design.md)を作成した。これはまだ製品実装・適格化ではなく、設計をレビューしてから実装計画に落とす。D は別計画で、tick 上限・観測・期待値を含む実装計画は存在しない。任意の A 成功を C/D 成功に読み替えず、製品では引き続き `blocked`。既存の計画を全て完了した、という報告にはしない。

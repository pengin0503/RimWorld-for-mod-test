# RimWorld-for-mod-test

**日本語** | [English](README.en.md)

RimWorld MODの読み込みや一部のゲーム処理をLinux環境で検証するためのツールです。ゲームとして遊ぶことはできず、公式ゲーム実行ファイルも起動しません。正規に用意したゲームファイルが必要で、ゲーム本体は配布していません。

## 内蔵・オフライン検証データベース（ゲーム本体不要）

既存の実ゲーム検証とは別に、**1.7.4985 rev1269用**の公開可能な検証知識をリポジトリ内に収録しました。R2・ゲーム本体・非公開MOD索引を取得せず、ローカルMODのAbout/LoadFolders/選択XMLや、収録済みAPI・Def・Harmony対象名を確認できます。

    python tools/knowledge_preflight.py validate-db
    python tools/knowledge_preflight.py query --kind method --symbol Verse.GenText.ToSpaceList
    python tools/codex_workflow.py static-preflight --mod ./MyMod
    python tools/codex_workflow.py static-preflight --mod ./MyMod.zip

**知識データは一部の実証済み項目に限定されています。** 未収録の名前は「未確認」であり「存在しない」ではありません。静的合格は実ゲームによるpassed/qualifiedを意味しません。対応範囲、機械可読出力、将来のバージョン拡張は[内蔵検証データベース](docs/knowledge-database.md)を参照してください。

## 利用方法

セットアップと実行は[実ゲーム処理によるMOD検証ガイド](docs/validation-host.md)を参照してください。Cloudflare R2から必要なファイルを取得する方法は[R2ガイド](docs/r2-on-demand.md)、検証結果の意味は[結果契約](docs/contracts/mod-validation-v1.md)に記載しています。

## 対応範囲

Linux x86_64、RimWorld 1.7.4985 rev1269、同梱WaylithClrの組み合わせで、MODのロード、XMLパッチ、参照解決、Def検査、指定したHarmonyパッチの確認を適格化しています。マップ生成も別途適格化済みです。

製造指示の材料候補と限定的なイベント選択肢、有限tickの検証は実験段階で、独立した適格化は未完了です。任意のMOD機能全体を検証するものではありません。単なる静的検査では `gameVerification=notRun` となり、実ゲーム処理の検証成功を意味しません。

Windowsでの実ゲーム検証は未対応です。Linuxで成功した結果はWindowsでの動作を保証しません。

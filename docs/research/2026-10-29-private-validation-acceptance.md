# 共通私有検証入口：main受入

2026-10-29。PR29/30を統合し、mainの手動入口から実行した。
PR30の追加レビューで見つかった取得量記録漏れはPR31で修正し、公開CI40869159422全8ジョブ成功後に統合した。
以後のmainは `d0df39880042971ba77653584f1902e8ad4de435`。
Windowsの新機能、R2書込、私有資材のArtifacts/Cache保存は行っていない。

| 選択 | run | 結果 |
|---|---|---|
| smoke | [40868971521](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40868971521) | 受入成功、passed/qualified |
| cow | [40869233096](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40869233096) | 受入成功、passed/notRequested |
| c-regression | [40869728334](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40869728334) | 受入成功、incomplete/experimental |
| d-regression | [40869806237](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40869806237) | 受入成功、incomplete/experimental |
| all | [40870656858](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40870656858) | 全5suite実行完了。D比較のみ受入不合格 |

smoke/cowは修正前の統合commit `7f9ad15728670fd01df8e72769eafe4ff193eb5c`。
初回smokeの取得量・時間は欠測であり、取得量記録の受入証拠にはしない。
PR31はcw.prepareの戻り値をrun固有の私有preparation.jsonへ保存してからgameReadyを確定する。
公開summaryへ私有データは追加していない。保存欠落の回帰をRED→GREENで確認した。

cowではSDK/R2準備/ゲーム取得/Workerビルド/Harmony取得がすべてskipし、専用Btrfsの準備・実行・unmountが成功した。
自作入力のCOW受入であり、実MOD全体の高速化率とは呼ばない。
C材料6＋自作イベント4の受入成功後もCの独立適格化は未完了のまま。
ゲームsnapshot準備は同一job内で1回、suite間で再利用する。第三者MODの選定・取得は行っていない。

## 残る境界

D比較の視点・診断差は解消していない。未適格をpassedへ変更しない。
Linuxメモリ監督はsoftのまま。明示的な書込可能cgroup委譲先がないためhard受入はblocked。
P3はケース別の公式参照経路確認から、P4は私有索引の照合から開始する。

## allの確定結果

全5suiteのexecutionStatusはcompleted、全helperのinterruptedはfalse。
smoke/C回帰/D回帰/cowはacceptancePassed=true、D比較のみfalse（exit1）。
全体はexecutionStatus=completed、validationStatus=incomplete、qualificationStatus=experimental、acceptancePassed=false。
workflowのfailureはD比較を成功へ変換しなかった結果であり、全体成功とは報告しない。
D比較後のcowも実行成功し、専用Btrfsのunmountも成功した。
各helperの秒数はsmoke72.745、C材料47.792、Cイベント82.312、D328.323、D比較176.306、cow13.253。
単独実行との速度比較用標本にはしない。

allのゲーム準備stepは1回だけ成功し、各suiteは同じsnapshotパスを受け取る。
PR31の私有取得量記録もこの準備経路に含む。取得量の数値・生ログそのものは公開していない。
main公開CI [40869427495](https://github.com/pengin0503/RimWorld-for-mod-test/actions/runs/40869427495)も成功。

共通入口に移行済みのlinux-private-bounded-tick.ymlとlinux-private-qualification.ymlを廃止する。
初期準備/SDK測定/実MOD回帰の専用入口は別の目的が残るため維持する。
P2の運用受入を完了とするが、D独立適格化・全体受入成功を完了条件に読み替えない。

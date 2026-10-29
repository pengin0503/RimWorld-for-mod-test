namespace RimWorldValidation.Gui.Model;

/// <summary>
/// Japanese explanations of the reason codes tools/validation_host.py writes.
/// The GUI shows the explanation next to the code and the Controller's detail;
/// a code missing here (a newer Controller) is shown as the code itself.
/// </summary>
public static class ReasonCatalog
{
    private static readonly Dictionary<string, string> Texts = new()
    {
        // blocked: the run did not start
        ["harmonyMissing"] = "Harmony を使う MOD があるのに、Harmony の MOD が一覧にありません。",
        ["invalidRequest"] = "検証の指定（要求ファイル）に誤りがあります。",
        ["languageMissing"] = "指定した言語がゲームにありません。",
        ["missingGameFiles"] = "ゲームのフォルダに必要なファイルがありません。",
        ["modChanged"] = "検証の準備中に MOD のファイルが変わりました。",
        ["modDuplicate"] = "同じ MOD（packageId）が 2 回指定されています。",
        ["modInvalid"] = "MOD のフォルダか ZIP が読めません（About.xml など）。",
        ["modMismatch"] = "MOD の packageId が指定と違います。",
        ["modMissing"] = "指定した MOD のフォルダが見つかりません。",
        ["modTooLarge"] = "MOD が大きすぎます（上限を超えています）。",
        ["officialContentMissing"] = "指定した公式 DLC がゲームにありません。",
        ["platformMismatch"] = "スナップショットが別の OS 用のゲームです。",
        ["platformUnsupported"] = "この OS には対応していません。",
        ["runtimeUnsupported"] = "指定した実行環境は使えません。",
        ["snapshotExists"] = "スナップショットの作成先がすでにあります。",
        ["snapshotInsideSource"] = "スナップショットをゲームのフォルダの中には作れません。",
        ["snapshotInvalid"] = "スナップショットが壊れているか、形式が違います。",
        ["snapshotMissing"] = "スナップショットが見つかりません。",
        ["snapshotModified"] = "スナップショットのファイルが作成後に変わっています。",
        ["boundedTickUnsupported"] = "有限tick検証は対応するLinuxビルドと同梱ランタイムでのみ利用できます。",
        ["unknownBuild"] = "このゲームのビルドには対応表（Adapter）がありません。",
        ["workerMissing"] = "検証用の Worker がビルドされていません。",
        // failed: a problem was found
        ["expectationMismatch"] = "指定した期待値（Def など）と実際が違いました。",
        ["harmonyPatchMissing"] = "期待した Harmony パッチが登録されていません。",
        ["loadException"] = "読み込み中に例外が出て、読み込みが止まりました。",
        ["playDataNotLoaded"] = "ゲームのデータの読み込みが終わりませんでした。",
        ["newErrors"] = "対象の MOD を入れたときだけ、新しいエラーが出ました。",
        ["newWarnings"] = "対象の MOD を入れたときだけ、新しい警告が出ました。",
        ["newTranslationErrors"] = "対象の MOD を入れたときだけ、新しい翻訳のエラーが出ました。",
        ["mapExpectationMismatch"] = "マップに期待した物の数が合いませんでした。",
        ["mapGenerationFailed"] = "マップの生成に失敗しました。",
        ["eventChoiceMismatch"] = "イベントの選択後の報酬が期待と違いました。",
        ["eventChoiceObservationIncomplete"] = "イベントまたは選択肢の動作を確認できませんでした。",
        ["billIngredientMismatch"] = "製造指示の材料の表示が期待と違いました。",
        // incomplete: the run could not prove a result
        ["experimental"] = "この OS・実行環境・ビルドは、まだ公式との比較で確かめていません。結果は参考です。",
        ["mapNotQualified"] = "この環境のマップ生成は、まだ公式との比較で確かめていません。",
        ["cNotQualified"] = "製造指示の確認（C）は、まだ公式の画面との比較で確かめていません。",
        ["baselineIncomplete"] = "比較の基準（対象なしの実行）が完了しませんでした。",
        ["baselineMapIncomplete"] = "比較の基準のマップが完了しませんでした。",
        ["billIngredientApiUnavailable"] = "このビルドでは製造指示の確認に使う関数が見つかりません。",
        ["billIngredientObservationIncomplete"] = "製造指示の材料を最後まで確認できませんでした。",
        ["checkError"] = "期待値の一部を確認できませんでした。",
        ["diagnosticsDropped"] = "ログが多すぎて、一部の記録を捨てました。",
        ["verseLogLimit"] = "ゲームがログの上限に達し、記録を止めました。",
        ["harmonyCheckError"] = "期待した Harmony パッチの一部を確認できませんでした。",
        ["noExpectedPatches"] = "B（Harmony）を選びましたが、期待するパッチが指定されていません。",
        ["languageNotApplied"] = "指定した言語が実際には使われませんでした。",
        ["loadFolderMismatch"] = "実際に読み込まれたフォルダが計画と違いました。",
        ["modOrderMismatch"] = "実際に読み込まれた MOD や順序が指定と違いました。",
        ["mapNotGenerated"] = "マップが生成されませんでした。",
        ["outputNotEmpty"] = "結果の出力先が空ではありません。",
        ["workerExitCode"] = "Worker が完了を報告した後、異常な終了コードで終わりました。",
        ["workerFailed"] = "Worker が途中で失敗しました。",
        ["workerInterrupted"] = "Worker が時間切れなどで中断されました。",
        ["workerAdaptermismatch"] = "このビルドに、Worker が使うゲームの関数がありません。",
        ["workerUnknown"] = "Worker の状態が分かりません。",
        ["workerResultMissing"] = "Worker の結果ファイルがありません（異常終了の可能性）。",
        ["workerResultUnreadable"] = "Worker の結果ファイルが読めません。",
        ["workerResultInvalid"] = "Worker の結果ファイルの形式が違います。",
        ["workerResultStale"] = "Worker の結果ファイルが今回の実行のものではありません。",
        ["timeout"] = "時間の上限に達したので止めました。",
        ["memoryLimit"] = "メモリの上限に達したので止めました。",
        ["logLimit"] = "ログの量の上限に達したので止めました。",
        ["runningModsError"] = "読み込まれた MOD の一覧を確認できませんでした。",
        ["modOrderError"] = "MOD の読み込み順を確認できませんでした。",
        ["checksError"] = "期待値の確認中にエラーが出ました。",
        ["activeLanguageError"] = "使われた言語を確認できませんでした。",
        ["translationErrorsError"] = "翻訳のエラーを確認できませんでした。",
    };

    public static IReadOnlyCollection<string> KnownCodes => Texts.Keys;

    public static string Describe(string code) => Texts.TryGetValue(code, out string? text) ? text : code;

    public static string StatusLabel(string status) => status switch
    {
        "passed" => "合格",
        "failed" => "不合格",
        "incomplete" => "不完全",
        "blocked" => "実行できず",
        _ => status,
    };
}

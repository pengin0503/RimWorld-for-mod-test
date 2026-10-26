using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// Shown while a validation runs: elapsed time, the phase, the Controller's
/// output and a button to stop it. When the Controller has written a result,
/// the window closes and the result tab opens.
/// </summary>
internal sealed class RunProgressWindow : Window
{
    private Vector2 _scroll;

    public RunProgressWindow()
    {
        doCloseX = false;
        closeOnAccept = false;
        closeOnCancel = false;
        closeOnClickedOutside = false;
        absorbInputAroundWindow = true;
        forcePause = false;
        preventCameraMotion = false;
    }

    public override Vector2 InitialSize => new(900f, 560f);

    public override void WindowUpdate()
    {
        base.WindowUpdate();
        RunController.Update();
        if (RunController.ExitCode != null && !RunController.Cancelled && File.Exists(Path.Combine(RunController.ResultDir, "result.json")))
        {
            string runDir = RunController.RunDir!;
            RunController.Clear();
            GuiState.OpenResult(runDir);
            MainWindow.Instance?.Select("results");
            Close();
        }
    }

    public override void DoWindowContents(Rect inRect)
    {
        bool running = RunController.Running;
        Text.Font = GameFont.Medium;
        string title = running ? "検証中" : RunController.Cancelled ? "検証を中止しました" : "検証が結果を書かずに終わりました";
        Widgets.Label(new Rect(inRect.x, inRect.y, inRect.width, 36f), title);
        Text.Font = GameFont.Small;
        TimeSpan elapsed = DateTime.Now - RunController.StartedAt;
        string state = running
            ? $"{RunController.Phase()}　経過 {(int)elapsed.TotalMinutes}:{elapsed.Seconds:00}"
            : RunController.Cancelled
                ? $"結果はありません。履歴には「中止」として残ります（{RunController.RunDir}）。"
                : $"終了コード {RunController.ExitCode}。下の出力と、{RunController.RunDir} を確認してください。";
        Widgets.Label(new Rect(inRect.x, inRect.y + 40f, inRect.width, 48f), state);

        Rect outputRect = new(inRect.x, inRect.y + 92f, inRect.width, inRect.height - 92f - 46f);
        Widgets.DrawMenuSection(outputRect);
        string output = RunController.Output.Count == 0 ? "（Controller の出力はまだありません。結果は最後にまとめて出ます。）" : string.Join("\n", RunController.Output);
        Rect inner = outputRect.ContractedBy(8f);
        Rect view = new(0f, 0f, inner.width - 16f, Text.CalcHeight(output, inner.width - 16f));
        Widgets.BeginScrollView(inner, ref _scroll, view);
        Widgets.Label(view, output);
        Widgets.EndScrollView();

        Rect button = new(inRect.xMax - 200f, inRect.yMax - 38f, 200f, 38f);
        if (running)
        {
            if (Widgets.ButtonText(button, "中止"))
            {
                RunController.Cancel();
            }
        }
        else if (RunController.ExitCode != null && Widgets.ButtonText(button, "閉じる"))
        {
            RunController.Clear();
            Close();
        }
    }
}

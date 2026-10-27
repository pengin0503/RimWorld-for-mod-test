using System.Diagnostics;
using RimWorldValidation.Gui.Model;
using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// One result.json as the Controller wrote it: the verdict and its reasons on
/// top, then new errors, the map, the crafting check and the checked scope.
/// The GUI shows the verdict; it never changes it.
/// </summary>
internal sealed class ResultsTab : IGuiTab
{
    private enum Section { Errors, Map, Bill, Scope }

    private static readonly (Section Section, string Label)[] Sections =
        [(Section.Errors, "新しいエラー・警告"), (Section.Map, "マップ"), (Section.Bill, "製造指示の材料"), (Section.Scope, "確認した範囲")];

    private readonly Dictionary<string, Texture2D?> _images = [];
    private Section _section;
    private Vector2 _reasonsScroll, _listScroll, _detailScroll, _scopeScroll, _billScroll;
    private Diagnostic? _selected;
    private IReadOnlyList<Diagnostic> _diagnostics = [];
    private string? _shownFor;
    private string? _folderError;

    public string Id => "results";

    public string Label => "結果";

    public void Draw(Rect rect)
    {
        if (GuiState.ShownRunDir == null)
        {
            Widgets.Label(rect, "まだ結果を開いていません。検証を始めるか、履歴から選んでください。");
            return;
        }
        if (_shownFor != GuiState.ShownRunDir)
        {
            _shownFor = GuiState.ShownRunDir;
            _folderError = null;
            _selected = null;
            _section = Section.Errors;
            _reasonsScroll = _listScroll = _detailScroll = _scopeScroll = _billScroll = Vector2.zero;
            // The ones that count toward the verdict first; the annotated ones (engine noise, allowed) after them.
            _diagnostics = GuiState.ShownResult?.NewDiagnostics.OrderBy(d => d.Counted ? 0 : 1).ToList() ?? [];
        }
        DrawFolderLine(new Rect(rect.x, rect.y, rect.width, 30f));
        Rect body = new(rect.x, rect.y + 36f, rect.width, rect.height - 36f);
        if (GuiState.ShownResult is not ResultSummary result)
        {
            Widgets.Label(body, GuiState.ShownError ?? "");
            return;
        }
        float headerHeight = DrawVerdict(new Rect(body.x, body.y, body.width, body.height * 0.4f), result);
        Rect sectionButtons = new(body.x, body.y + headerHeight + 8f, body.width, 32f);
        float x = sectionButtons.x;
        foreach (var (section, label) in Sections)
        {
            string text = label + Count(result, section);
            Rect button = new(x, sectionButtons.y, Mathf.Max(200f, Text.CalcSize(text).x + 40f), 30f);
            if (_section == section)
            {
                Widgets.DrawHighlightSelected(button);
            }
            if (Widgets.ButtonText(button, text, drawBackground: _section != section))
            {
                _section = section;
            }
            x = button.xMax + 6f;
        }
        Rect content = new(body.x, sectionButtons.yMax + 8f, body.width, body.yMax - sectionButtons.yMax - 8f);
        Widgets.DrawMenuSection(content);
        content = content.ContractedBy(10f);
        switch (_section)
        {
            case Section.Errors:
                DrawErrors(content);
                break;
            case Section.Map:
                DrawMap(content, result);
                break;
            case Section.Bill:
                DrawBill(content, result);
                break;
            case Section.Scope:
                DrawScope(content, result);
                break;
        }
    }

    private static string Count(ResultSummary result, Section section) => section switch
    {
        Section.Errors => result.NewDiagnostics.Count == 0 ? "（0）"
            : $"（判定 {result.NewDiagnostics.Count(d => d.Counted)}／除外 {result.NewDiagnostics.Count(d => !d.Counted)}）",
        Section.Bill => $"（{result.BillChecks.Count}）",
        Section.Map => result.MapImage == null ? "（なし）" : "",
        _ => "",
    };

    private void DrawFolderLine(Rect rect)
    {
        string dir = GuiState.ShownRunDir!;
        Text.Anchor = TextAnchor.MiddleLeft;
        GUI.color = ColoredText.SubtleGrayColor;
        Widgets.Label(new Rect(rect.x, rect.y, rect.width - 220f, rect.height), _folderError ?? $"{Path.GetFileName(dir)}　{dir}");
        GUI.color = Color.white;
        Text.Anchor = TextAnchor.UpperLeft;
        if (Widgets.ButtonText(new Rect(rect.xMax - 210f, rect.y, 210f, rect.height), "結果フォルダを開く"))
        {
            _folderError = OpenFolder(dir);
        }
    }

    /// <summary>Draws the verdict within at most <paramref name="rect"/>; returns the height used.</summary>
    private float DrawVerdict(Rect rect, ResultSummary result)
    {
        Text.Font = GameFont.Medium;
        GUI.color = StatusColor(result.Status);
        Widgets.Label(new Rect(rect.x, rect.y, 220f, 36f), ReasonCatalog.StatusLabel(result.Status));
        GUI.color = Color.white;
        Text.Font = GameFont.Small;
        string targets = result.TargetLabels.Count == 0 ? ""
            : $"対象：{string.Join("、", result.TargetLabels.Zip(result.TargetNames, (label, folder) => label == folder ? label : $"{label}（{folder}）"))}　";
        string facts = $"{targets}実行：{result.ExecutionStatus}　{result.Platform}　{result.StartedAt}"
            + (result.TotalSeconds is double seconds ? $"　{seconds:F0} 秒" : "");
        Widgets.Label(new Rect(rect.x + 230f, rect.y + 6f, rect.width - 230f, 30f), facts);
        float y = rect.y + 40f;
        if (result.Fidelity == "experimental")
        {
            GUI.color = new Color(1f, 0.8f, 0.35f);
            Widgets.Label(new Rect(rect.x, y, rect.width, 26f),
                "実験扱い（experimental）：この環境・ビルドではまだ公式と照合していないため、合否は保証になりません。");
            GUI.color = Color.white;
            y += 28f;
        }
        string reasons = result.Reasons.Count == 0
            ? "理由：なし"
            : string.Join("\n", result.Reasons.Select(r => $"・{ReasonCatalog.Describe(r.Code)}（{r.Code}）\n　{r.Detail}"));
        Rect view = new(0f, 0f, rect.width - 16f, Text.CalcHeight(reasons, rect.width - 16f));
        Rect outRect = new(rect.x, y, rect.width, Mathf.Min(view.height, rect.yMax - y));
        Widgets.BeginScrollView(outRect, ref _reasonsScroll, view);
        Widgets.Label(view, reasons);
        Widgets.EndScrollView();
        return outRect.yMax - rect.y;
    }

    private void DrawErrors(Rect rect)
    {
        if (_diagnostics.Count == 0)
        {
            Widgets.Label(rect, "対象の MOD を入れたときだけ出たエラー・警告はありません。");
            return;
        }
        int counted = _diagnostics.Count(d => d.Counted);
        GUI.color = ColoredText.SubtleGrayColor;
        Widgets.Label(new Rect(rect.x, rect.y, rect.width, 26f),
            $"判定に入るもの {counted} 件（上）、判定から外したもの {_diagnostics.Count - counted} 件（下・灰色）。外した理由は右に出ます。");
        GUI.color = Color.white;
        rect = new Rect(rect.x, rect.y + 30f, rect.width, rect.height - 30f);
        Rect listRect = rect.LeftPart(0.55f);
        Rect detailRect = new(listRect.xMax + 10f, rect.y, rect.width - listRect.width - 10f, rect.height);
        const float rowHeight = 28f;
        Rect view = new(0f, 0f, listRect.width - 16f, _diagnostics.Count * rowHeight);
        Widgets.BeginScrollView(listRect, ref _listScroll, view);
        for (int i = 0; i < _diagnostics.Count; i++)
        {
            Diagnostic diagnostic = _diagnostics[i];
            Rect row = new(0f, i * rowHeight, view.width, rowHeight);
            if (i % 2 == 1)
            {
                Widgets.DrawLightHighlight(row);
            }
            if (_selected == diagnostic)
            {
                Widgets.DrawHighlightSelected(row);
            }
            Widgets.DrawHighlightIfMouseover(row);
            GUI.color = !diagnostic.Counted ? ColoredText.SubtleGrayColor : diagnostic.Level == "error" ? ColorLibrary.RedReadable : new Color(1f, 0.8f, 0.35f);
            Text.Anchor = TextAnchor.MiddleLeft;
            Text.WordWrap = false;
            string label = $"{(diagnostic.Counted ? "" : "（除外）")}[{diagnostic.Level}・{diagnostic.Stage}] {diagnostic.FirstLine}";
            Widgets.Label(row.ContractedBy(4f, 0f), label.Truncate(row.width - 8f));
            Text.WordWrap = true;
            Text.Anchor = TextAnchor.UpperLeft;
            GUI.color = Color.white;
            if (Widgets.ButtonInvisible(row))
            {
                _selected = diagnostic;
                _detailScroll = Vector2.zero;
            }
        }
        Widgets.EndScrollView();

        Diagnostic shown = _selected ?? _diagnostics[0];
        string detail = $"レベル：{shown.Level}　段階：{shown.Stage}　分類：{shown.Category}\n"
            + (shown.KnownNoise != null ? $"判定から外しています（既知のエンジンのメッセージ）：{shown.KnownNoise}\n" : "")
            + (shown.AllowedBy != null ? $"判定から外しています（要求の allow）：{shown.AllowedBy}\n" : "")
            + (shown.SupersededBy != null ? $"判定から外しています（個々のエラーを {shown.SupersededBy} で判定）\n" : "")
            + "\n" + shown.Text;
        Widgets.DrawMenuSection(detailRect);
        Rect inner = detailRect.ContractedBy(8f);
        Rect detailView = new(0f, 0f, inner.width - 16f, Text.CalcHeight(detail, inner.width - 16f));
        Widgets.BeginScrollView(inner, ref _detailScroll, detailView);
        Widgets.Label(detailView, detail);
        Widgets.EndScrollView();
    }

    private void DrawMap(Rect rect, ResultSummary result)
    {
        if (result.MapImage == null)
        {
            Widgets.Label(rect, "この検証ではマップを作っていません（検証内容タブの「マップ」）。");
            return;
        }
        var images = new List<(string Title, Texture2D? Texture)>
        {
            ("対象の MOD あり", Image(result.MapImage)),
        };
        if (result.MapBaselineImage != null)
        {
            images.Add(("比較用（対象なし・同じ種）", Image(result.MapBaselineImage)));
        }
        float width = (rect.width - 20f * (images.Count - 1)) / images.Count;
        for (int i = 0; i < images.Count; i++)
        {
            Rect cell = new(rect.x + i * (width + 20f), rect.y, width, rect.height);
            Widgets.Label(new Rect(cell.x, cell.y, cell.width, 26f), images[i].Title);
            Rect picture = new(cell.x, cell.y + 30f, cell.width, cell.height - 30f);
            if (images[i].Texture is Texture2D texture)
            {
                GUI.DrawTexture(picture, texture, ScaleMode.ScaleToFit);
            }
            else
            {
                Widgets.Label(picture, "画像を読めませんでした。");
            }
        }
    }

    private void DrawBill(Rect rect, ResultSummary result)
    {
        if (result.BillChecks.Count == 0)
        {
            Widgets.Label(rect, "この検証では製造指示の材料を調べていません（検証内容タブの C）。");
            return;
        }
        var rows = new List<(string Text, float Height, bool Match)>();
        foreach (BillCheck check in result.BillChecks)
        {
            string text = $"レシピ {check.Recipe}・材料 {check.Thing}：{OutcomeLabel(check.Outcome)}（{check.Outcome}）\n"
                + $"　候補に出る：期待 {YesNo(check.ExpectedVisible)} / 実際 {YesNo(check.ActualVisible)}　"
                + $"許可：期待 {YesNo(check.ExpectedAllowed)} / 実際 {YesNo(check.ActualAllowed)}"
                + (check.Reasons.Count > 0 ? "\n　理由：" + string.Join("、", check.Reasons) : "")
                + (check.ObservationReason != null ? "\n　観測できなかった理由：" + check.ObservationReason : "")
                + (check.ObservationError != null ? "\n　詳細：" + check.ObservationError : "");
            rows.Add((text, Text.CalcHeight(text, rect.width - 16f), check.Outcome == "match"));
        }
        Rect view = new(0f, 0f, rect.width - 16f, rows.Sum(row => row.Height + 10f));
        Widgets.BeginScrollView(rect, ref _billScroll, view);
        float y = 0f;
        foreach (var row in rows)
        {
            GUI.color = row.Match ? Color.white : ColorLibrary.RedReadable;
            Widgets.Label(new Rect(0f, y, view.width, row.Height), row.Text);
            GUI.color = Color.white;
            y += row.Height + 10f;
        }
        Widgets.EndScrollView();
    }

    private void DrawScope(Rect rect, ResultSummary result)
    {
        string text = "確認した範囲\n" + string.Join("\n", result.Checked.Select(s => "・" + s))
            + "\n\n確認していない範囲\n" + string.Join("\n", result.NotChecked.Select(s => "・" + s));
        Rect view = new(0f, 0f, rect.width - 16f, Text.CalcHeight(text, rect.width - 16f));
        Widgets.BeginScrollView(rect, ref _scopeScroll, view);
        Widgets.Label(view, text);
        Widgets.EndScrollView();
    }

    private Texture2D? Image(string path)
    {
        // result.json holds the path at run time; a moved results folder still has the file beside it.
        string file = File.Exists(path) ? path : Path.Combine(GuiState.ShownRunDir!, RunHistory.ResultFolder, Path.GetFileName(path));
        if (!_images.TryGetValue(file, out Texture2D? texture))
        {
            texture = null;
            if (File.Exists(file))
            {
                texture = new Texture2D(2, 2);
                if (!texture.LoadImage(File.ReadAllBytes(file)))
                {
                    texture = null;
                }
            }
            _images[file] = texture;
        }
        return texture;
    }

    private static string YesNo(bool? value) => value switch { true => "はい", false => "いいえ", null => "－" };

    private static string OutcomeLabel(string outcome) => outcome switch
    {
        "match" => "期待どおり",
        "mismatch" => "期待と違う",
        _ => "判定できず",
    };

    public static Color StatusColor(string status) => status switch
    {
        "passed" => new Color(0.45f, 0.85f, 0.45f),
        "failed" => ColorLibrary.RedReadable,
        "incomplete" => new Color(1f, 0.8f, 0.35f),
        _ => new Color(1f, 0.55f, 0.3f),
    };

    /// <summary>Opens the folder in the file manager; returns why it could not, or null.</summary>
    private static string? OpenFolder(string dir)
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { dir }, UseShellExecute = false })?.Dispose();
            }
            else
            {
                Process.Start(new ProcessStartInfo("xdg-open") { ArgumentList = { dir }, UseShellExecute = false })?.Dispose();
            }
        }
        catch (System.ComponentModel.Win32Exception e)
        {
            return $"フォルダを開けませんでした（{e.Message}）：{dir}";
        }
        return null;
    }
}

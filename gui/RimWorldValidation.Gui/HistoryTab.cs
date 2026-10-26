using RimWorldValidation.Gui.Model;
using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>Past runs in the results folder, newest first. Choosing one opens it on the result tab.</summary>
internal sealed class HistoryTab : IGuiTab
{
    private const float RowHeight = 30f, RefreshSeconds = 5f;
    private IReadOnlyList<HistoryEntry> _entries = [];
    private float _listedAt = float.NegativeInfinity;
    private Vector2 _scroll;

    public string Id => "history";

    public string Label => "履歴";

    public void Draw(Rect rect)
    {
        // Reading every result.json each frame would be wasteful; the folder is listed again every few seconds.
        if (Time.realtimeSinceStartup - _listedAt > RefreshSeconds)
        {
            _entries = RunHistory.List(GuiState.Request.ResultsDir);
            _listedAt = Time.realtimeSinceStartup;
        }
        GUI.color = ColoredText.SubtleGrayColor;
        Widgets.Label(new Rect(rect.x, rect.y, rect.width, 28f), $"{_entries.Count} 件　{GuiState.Request.ResultsDir}");
        GUI.color = Color.white;
        Rect header = new(rect.x, rect.y + 32f, rect.width, 26f);
        DrawColumns(header, "日時", "判定", "対象の MOD", "開始（result.json）");
        Widgets.DrawLineHorizontal(header.x, header.yMax, header.width);
        Rect outRect = new(rect.x, header.yMax + 4f, rect.width, rect.yMax - header.yMax - 4f);
        Rect view = new(0f, 0f, outRect.width - 16f, _entries.Count * RowHeight);
        Widgets.BeginScrollView(outRect, ref _scroll, view);
        for (int i = 0; i < _entries.Count; i++)
        {
            HistoryEntry entry = _entries[i];
            Rect row = new(0f, i * RowHeight, view.width, RowHeight);
            if (i % 2 == 1)
            {
                Widgets.DrawLightHighlight(row);
            }
            if (GuiState.ShownRunDir == entry.Dir)
            {
                Widgets.DrawHighlightSelected(row);
            }
            Widgets.DrawHighlightIfMouseover(row);
            string status = entry.HasResult ? ReasonCatalog.StatusLabel(entry.Status ?? "")
                : entry.Cancelled ? "中止" : RunController.Running && RunController.RunDir == entry.Dir ? "実行中" : "結果なし";
            GUI.color = entry.HasResult ? ResultsTab.StatusColor(entry.Status ?? "") : ColoredText.SubtleGrayColor;
            DrawColumns(row, Stamp(entry.Id), status, string.Join("、", entry.TargetLabels), entry.StartedAt ?? "");
            GUI.color = Color.white;
            if (Widgets.ButtonInvisible(row))
            {
                GuiState.OpenResult(entry.Dir);
                MainWindow.Instance?.Select("results");
            }
        }
        Widgets.EndScrollView();
    }

    private static void DrawColumns(Rect row, string when, string status, string targets, string started)
    {
        Text.Anchor = TextAnchor.MiddleLeft;
        Text.WordWrap = false;
        float x = row.x + 6f;
        foreach (var (text, width) in new[] { (when, 200f), (status, 120f), (targets, row.width - 600f), (started, 260f) })
        {
            Widgets.Label(new Rect(x, row.y, width - 10f, row.height), text.Truncate(width - 10f));
            x += width;
        }
        Text.WordWrap = true;
        Text.Anchor = TextAnchor.UpperLeft;
    }

    /// <summary>"20261026-141432-2" → "2026-10-26 14:14:32 (2)".</summary>
    private static string Stamp(string id) =>
        id.Length >= 15 && id[8] == '-'
            ? $"{id[..4]}-{id[4..6]}-{id[6..8]} {id[9..11]}:{id[11..13]}:{id[13..15]}{(id.Length > 16 ? $" ({id[16..]})" : "")}"
            : id;
}

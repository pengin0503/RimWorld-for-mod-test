using RimWorldValidation.Gui.Model;
using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// A run's progress log as a list: time, then the step; the game's errors in
/// red and warnings in yellow. Follows new lines while the list is scrolled to
/// the end. Shared by the progress window and the result tab.
/// </summary>
internal static class ProgressLogView
{
    private const float RowHeight = 22f, TimeWidth = 80f;

    public static void Draw(Rect rect, IReadOnlyList<ProgressEntry> entries, ref Vector2 scroll, ref int shown, string empty)
    {
        Widgets.DrawMenuSection(rect);
        Rect inner = rect.ContractedBy(6f);
        if (entries.Count == 0)
        {
            GUI.color = ColoredText.SubtleGrayColor;
            Widgets.Label(inner, empty);
            GUI.color = Color.white;
            return;
        }
        Rect view = new(0f, 0f, inner.width - 16f, entries.Count * RowHeight);
        float bottom = Mathf.Max(0f, view.height - inner.height);
        if (entries.Count != shown)
        {
            // New lines: follow them only when the reader was already at the end.
            if (scroll.y >= (shown * RowHeight - inner.height) - RowHeight)
            {
                scroll.y = bottom;
            }
            shown = entries.Count;
        }
        Widgets.BeginScrollView(inner, ref scroll, view);
        int first = Mathf.Max(0, (int)(scroll.y / RowHeight) - 1);
        int last = Mathf.Min(entries.Count - 1, (int)((scroll.y + inner.height) / RowHeight) + 1);
        Text.Anchor = TextAnchor.MiddleLeft;
        Text.WordWrap = false;
        for (int i = first; i <= last; i++)
        {
            ProgressEntry entry = entries[i];
            Rect row = new(0f, i * RowHeight, view.width, RowHeight);
            if (i % 2 == 1)
            {
                Widgets.DrawLightHighlight(row);
            }
            GUI.color = ColoredText.SubtleGrayColor;
            Widgets.Label(new Rect(row.x + 4f, row.y, TimeWidth - 8f, row.height), $"{entry.Seconds:F1} 秒");
            GUI.color = entry.Level switch
            {
                "error" => ColorLibrary.RedReadable,
                "warning" => new Color(1f, 0.8f, 0.35f),
                _ => Color.white,
            };
            Rect text = new(row.x + TimeWidth, row.y, row.width - TimeWidth, row.height);
            Widgets.Label(text, entry.Text.Truncate(text.width));
            GUI.color = Color.white;
            if (Mouse.IsOver(row))
            {
                Widgets.DrawHighlight(row);
                TooltipHandler.TipRegion(row, entry.Text);
            }
        }
        Text.WordWrap = true;
        Text.Anchor = TextAnchor.UpperLeft;
        Widgets.EndScrollView();
    }
}

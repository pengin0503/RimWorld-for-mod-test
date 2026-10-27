using RimWorld;
using UnityEngine;
using Verse;
using Verse.Sound;

namespace RimWorldValidation.Gui;

/// <summary>
/// Choose the MODs to load and mark the ones under test, laid out like the
/// game's own MOD list: unused on the left, used in load order on the right
/// (drag to reorder), details of the selected MOD beside them. A search box
/// filters both lists; the marks for the MODs under test can be painted by
/// dragging over them, as the game's checkboxes.
/// </summary>
internal sealed class ModsTab : IGuiTab
{
    private const float RowHeight = 26f, ListWidth = 320f, Gap = 12f, CheckSize = 24f, DoubleClickSeconds = 0.5f;
    private Vector2 _unusedScroll, _usedScroll, _infoScroll;
    private int _usedGroup = -1;
    private ModMetaData? _lastClicked;
    private float _lastClickTime;
    private string _search = "";
    // Painting the target marks: the value the first click set, applied to every mark the mouse passes over.
    private bool _painting, _paintValue;

    public string Id => "mods";

    public string Label => "MOD";

    public void Draw(Rect rect)
    {
        GuiState.EnsureInitialized();
        float y = rect.y;
        DrawOfficial(new Rect(rect.x, y, rect.width, 30f));
        y += 38f;

        Rect import = new(rect.x, y, 260f, 30f);
        if (Widgets.ButtonText(import, "本家の読み込み順を取り込む"))
        {
            GuiState.ImportUserModsConfig();
        }
        TooltipHandler.TipRegion(import, GuiState.Request.UserModsConfig is string config
            ? $"{config} を読むだけです（書き換えません）。"
            : "本家の ModsConfig.xml が見つかっていません。");
        if (Widgets.ButtonText(new Rect(import.xMax + 8f, y, 160f, 30f), "すべて外す"))
        {
            GuiState.ClearActive();
            GuiState.ModsNotice = null;
        }
        if (GuiState.ModsNotice != null)
        {
            Text.Anchor = TextAnchor.MiddleLeft;
            Widgets.Label(new Rect(import.xMax + 180f, y, rect.width - 440f, 30f), GuiState.ModsNotice);
            Text.Anchor = TextAnchor.UpperLeft;
        }
        y += 40f;

        if (_painting && (Event.current.rawType == EventType.MouseUp || !Input.GetMouseButton(0)))
        {
            _painting = false;
        }
        DrawSearch(new Rect(rect.x, y, ListWidth * 2f + Gap, 28f));
        y += 34f;
        bool filtering = !_search.NullOrEmpty();
        List<ModMetaData> unused = GuiState.CandidateMods.Where(m => !GuiState.Active.Contains(m) && Matches(m))
            .OrderBy(m => m.Name, StringComparer.OrdinalIgnoreCase).ToList();
        List<ModMetaData> used = filtering ? GuiState.Active.Where(Matches).ToList() : GuiState.Active;
        Widgets.Label(new Rect(rect.x, y, ListWidth, 26f), $"使わない（{unused.Count}）");
        Widgets.Label(new Rect(rect.x + ListWidth + Gap, y, ListWidth, 26f), filtering
            ? $"使う（{used.Count}／{GuiState.Active.Count}。検索中は並べ替えできません）"
            : $"使う・読み込み順（{GuiState.Active.Count}、対象 {GuiState.Active.Count(GuiState.IsTarget)}）");
        y += 28f;
        float listHeight = rect.yMax - y - 40f;
        Rect unusedRect = new(rect.x, y, ListWidth, listHeight);
        Rect usedRect = new(rect.x + ListWidth + Gap, y, ListWidth, listHeight);
        DrawList(unusedRect, unused, ref _unusedScroll, used: false);
        DrawList(usedRect, used, ref _usedScroll, used: true, reorderable: !filtering);

        ModMetaData? selected = GuiState.Selected;
        float buttonsY = rect.yMax - 32f;
        if (Widgets.ButtonText(new Rect(unusedRect.x, buttonsY, ListWidth, 30f), "使う一覧へ →", active: selected != null && !GuiState.Active.Contains(selected)))
        {
            GuiState.Activate(selected!);
        }
        if (Widgets.ButtonText(new Rect(usedRect.x, buttonsY, ListWidth, 30f), "← 外す", active: selected != null && GuiState.Active.Contains(selected)))
        {
            GuiState.Deactivate(selected!);
        }

        float infoX = usedRect.xMax + Gap * 2f;
        DrawInfo(new Rect(infoX, rect.y + 78f, rect.xMax - infoX, rect.yMax - rect.y - 78f));
    }

    private void DrawSearch(Rect rect)
    {
        Text.Anchor = TextAnchor.MiddleLeft;
        Widgets.Label(new Rect(rect.x, rect.y, 50f, rect.height), "検索");
        Text.Anchor = TextAnchor.UpperLeft;
        Rect field = new(rect.x + 50f, rect.y, rect.width - 50f - (_search.NullOrEmpty() ? 0f : 70f), rect.height);
        _search = Widgets.TextField(field, _search);
        TooltipHandler.TipRegion(field, "名前・packageId・作者の一部で、左右の一覧を絞り込みます。");
        if (!_search.NullOrEmpty() && Widgets.ButtonText(new Rect(field.xMax + 6f, rect.y, 64f, rect.height), "消す"))
        {
            _search = "";
        }
    }

    private bool Matches(ModMetaData mod)
    {
        string text = _search.Trim();
        return text.Length == 0
            || mod.Name.IndexOf(text, StringComparison.OrdinalIgnoreCase) >= 0
            || mod.PackageIdPlayerFacing.IndexOf(text, StringComparison.OrdinalIgnoreCase) >= 0
            || (mod.AuthorsString?.IndexOf(text, StringComparison.OrdinalIgnoreCase) ?? -1) >= 0;
    }

    private static void DrawOfficial(Rect rect)
    {
        Text.Anchor = TextAnchor.MiddleLeft;
        Widgets.Label(new Rect(rect.x, rect.y, 140f, rect.height), "公式コンテンツ");
        float x = rect.x + 140f;
        foreach (ModMetaData mod in GuiState.OfficialMods)
        {
            float width = Text.CalcSize(mod.Name).x + CheckSize + 16f;
            bool on = mod.IsCoreMod || GuiState.Expansions.Contains(mod.FolderName);
            bool before = on;
            Widgets.CheckboxLabeled(new Rect(x, rect.y + 3f, width, 24f), mod.Name, ref on, disabled: mod.IsCoreMod, placeCheckboxNearText: true);
            if (on != before)
            {
                if (on)
                {
                    GuiState.Expansions.Add(mod.FolderName);
                }
                else
                {
                    GuiState.Expansions.Remove(mod.FolderName);
                }
            }
            x += width + 16f;
        }
        Text.Anchor = TextAnchor.UpperLeft;
    }

    private void DrawList(Rect outRect, List<ModMetaData> mods, ref Vector2 scroll, bool used, bool reorderable = false)
    {
        Widgets.DrawMenuSection(outRect);
        Rect inner = outRect.ContractedBy(2f);
        Rect view = new(0f, 0f, inner.width - 16f, mods.Count * RowHeight);
        Widgets.BeginScrollView(inner, ref scroll, view);
        if (reorderable && Event.current.type == EventType.Repaint)
        {
            // As the game's MOD list: the group is made while painting, from the visible area.
            _usedGroup = ReorderableWidget.NewGroup(GuiState.Move, ReorderableDirection.Vertical, inner);
        }
        for (int i = 0; i < mods.Count; i++)
        {
            ModMetaData mod = mods[i];
            Rect row = new(0f, i * RowHeight, view.width, RowHeight);
            if (reorderable)
            {
                // The mark on the right is left out, so dragging over the marks paints them instead of moving the row.
                Rect handle = new(row.x, row.y, row.width - CheckSize - 14f, row.height);
                ReorderableWidget.Reorderable(_usedGroup, handle, useRightButton: false, highlightDragged: true);
            }
            if (row.yMax < scroll.y || row.y > scroll.y + inner.height)
            {
                continue;
            }
            DrawRow(row, mod, i, used);
        }
        Widgets.EndScrollView();
    }

    private void DrawRow(Rect row, ModMetaData mod, int index, bool used)
    {
        if (index % 2 == 1)
        {
            Widgets.DrawLightHighlight(row);
        }
        if (GuiState.Selected == mod)
        {
            Widgets.DrawHighlightSelected(row);
        }
        Widgets.DrawHighlightIfMouseover(row);
        Rect label = new(row.x + 6f, row.y, row.width - (used ? CheckSize + 14f : 12f), row.height);
        Text.Anchor = TextAnchor.MiddleLeft;
        Text.WordWrap = false;
        Widgets.Label(label, mod.Name.Truncate(label.width));
        Text.WordWrap = true;
        Text.Anchor = TextAnchor.UpperLeft;
        if (used)
        {
            Rect check = new(row.xMax - CheckSize - 6f, row.y + 1f, CheckSize, CheckSize);
            bool target = GuiState.IsTarget(mod);
            Widgets.CheckboxDraw(check.x, check.y, target, disabled: false, CheckSize);
            if (Event.current.type == EventType.MouseDown && Event.current.button == 0 && Mouse.IsOver(check))
            {
                // Event-based: inside the reorderable list, Widgets.Checkbox's frame-based toggle
                // missed real clicks (checked with xdotool). Pressing starts painting, as the game's
                // paintable checkboxes: every mark the mouse passes over while held gets the same value.
                _painting = true;
                _paintValue = !target;
                SetTarget(mod, _paintValue);
                Event.current.Use();
            }
            else if (_painting && target != _paintValue && Mouse.IsOver(check))
            {
                SetTarget(mod, _paintValue);
            }
            TooltipHandler.TipRegion(check, "検証の対象。印のない MOD は前提として読み込むだけです。");
        }
        if (Widgets.ButtonInvisible(label, doMouseoverSound: false))
        {
            float now = RealTime.LastRealTime;
            if (_lastClicked == mod && now - _lastClickTime < DoubleClickSeconds)
            {
                // Double click moves the MOD to the other list, as in the game's MOD list (same 0.5 s).
                if (used)
                {
                    GuiState.Deactivate(mod);
                }
                else
                {
                    GuiState.Activate(mod);
                }
            }
            GuiState.Selected = mod;
            _lastClicked = mod;
            _lastClickTime = now;
        }
    }

    private static void SetTarget(ModMetaData mod, bool target)
    {
        GuiState.SetTarget(mod, target);
        (target ? SoundDefOf.Checkbox_TurnedOn : SoundDefOf.Checkbox_TurnedOff).PlayOneShotOnCamera();
    }

    private void DrawInfo(Rect rect)
    {
        IReadOnlyList<(ModMetaData Mod, string Missing)> missing = GuiState.MissingDependencies();
        float warningHeight = 0f;
        if (missing.Count > 0)
        {
            string text = "前提の MOD が使う一覧にありません。このままでは検証を始められません：\n" + string.Join("\n",
                missing.Take(6).Select(m => $"・{m.Mod.Name} → {m.Missing}")) + (missing.Count > 6 ? $"\nほか {missing.Count - 6} 件" : "");
            warningHeight = Text.CalcHeight(text, rect.width - 16f) + 16f;
            Rect box = new(rect.x, rect.yMax - warningHeight, rect.width, warningHeight);
            Widgets.DrawBoxSolid(box, new Color(0.35f, 0.12f, 0.1f, 0.6f));
            Widgets.Label(box.ContractedBy(8f), text);
            warningHeight += 8f;
        }

        ModMetaData? mod = GuiState.Selected ?? GuiState.Active.FirstOrDefault();
        if (mod == null)
        {
            Widgets.Label(rect, "MOD を選ぶと、ここに詳細が出ます。");
            return;
        }
        Rect area = new(rect.x, rect.y, rect.width, rect.height - warningHeight);
        float y = area.y;
        Texture2D preview = mod.PreviewImage;
        if (preview != null)
        {
            float width = Mathf.Min(preview.width, area.width);
            float height = preview.height * (width / preview.width);
            float max = Mathf.Ceil(area.height * 0.35f);
            if (height > max)
            {
                width *= max / height;
                height = max;
            }
            GUI.DrawTexture(new Rect(area.x + (area.width - width) / 2f, y, width, height), preview, ScaleMode.ScaleToFit);
            y += height + 10f;
        }
        Text.Font = GameFont.Medium;
        Widgets.Label(new Rect(area.x, y, area.width, 36f), mod.Name.Truncate(area.width));
        Text.Font = GameFont.Small;
        y += 36f;
        string details = Line("作者", mod.AuthorsString) + Line("packageId", mod.PackageIdPlayerFacing)
            + Line("場所", GuiState.OriginalPath(mod))
            + Line("対応バージョン", string.Join(", ", mod.SupportedVersionsReadOnly.Select(v => $"{v.Major}.{v.Minor}"))).TrimEnd('\n');
        float detailsHeight = Text.CalcHeight(details, area.width);
        Widgets.Label(new Rect(area.x, y, area.width, detailsHeight), details);
        y += detailsHeight + 6f;
        Rect descriptionRect = new(area.x, y, area.width, area.yMax - y);
        string description = mod.Description ?? "";
        Rect view = new(0f, 0f, descriptionRect.width - 16f, Text.CalcHeight(description, descriptionRect.width - 16f));
        Widgets.BeginScrollView(descriptionRect, ref _infoScroll, view);
        Widgets.Label(view, description);
        Widgets.EndScrollView();
    }

    private static string Line(string name, string? value) =>
        value.NullOrEmpty() ? "" : $"{name.Colorize(ColoredText.SubtleGrayColor)}：{value}\n";
}

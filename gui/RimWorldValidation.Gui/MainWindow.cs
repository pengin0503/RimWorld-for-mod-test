using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>One page of the main window.</summary>
internal interface IGuiTab
{
    /// <summary>Name used by test scripts ({"tab": "mods"}).</summary>
    string Id { get; }

    string Label { get; }

    void Draw(Rect rect);
}

/// <summary>
/// The only window: fills the screen, cannot be closed by Escape or a click
/// outside, and holds the four tabs. Closing the program is the only way out.
/// </summary>
internal sealed class MainWindow : Window
{
    private const float HeaderHeight = 40f;
    private readonly List<IGuiTab> _tabs;
    private readonly List<TabRecord> _records;

    public static MainWindow? Instance { get; private set; }

    public IGuiTab Selected { get; private set; }

    public MainWindow()
    {
        doCloseX = false;
        closeOnAccept = false;
        closeOnCancel = false;
        closeOnClickedOutside = false;
        absorbInputAroundWindow = false;
        preventCameraMotion = false;
        draggable = false;
        resizeable = false;
        forcePause = false;
        _tabs =
        [
            new ModsTab(),
            new SettingsTab(),
            new PendingTab("results", "結果"),
            new PendingTab("history", "履歴"),
        ];
        Selected = _tabs[0];
        _records = _tabs.Select(tab => new TabRecord(tab.Label, () => Selected = tab, () => Selected == tab)).ToList();
        Instance = this;
    }

    public override Vector2 InitialSize => new(UI.screenWidth, UI.screenHeight);

    protected override float Margin => 12f;

    public bool Select(string id)
    {
        IGuiTab? tab = _tabs.FirstOrDefault(t => t.Id == id);
        if (tab == null)
        {
            return false;
        }
        Selected = tab;
        return true;
    }

    public override void DoWindowContents(Rect inRect)
    {
        Text.Font = GameFont.Medium;
        Text.Anchor = TextAnchor.MiddleLeft;
        Widgets.Label(new Rect(inRect.x, inRect.y, inRect.width - 160f, HeaderHeight), "RimWorld MOD 検証");
        Text.Font = GameFont.Small;
        GUI.color = ColoredText.SubtleGrayColor;
        Widgets.Label(new Rect(inRect.x + 230f, inRect.y, inRect.width - 400f, HeaderHeight),
            "テスト専用です。この画面からゲームを遊ぶことはできません。");
        GUI.color = Color.white;
        Text.Anchor = TextAnchor.UpperLeft;
        if (Widgets.ButtonText(new Rect(inRect.xMax - 150f, inRect.y + 4f, 150f, HeaderHeight - 8f), "終了"))
        {
            Boot.Stop(Program.Closed, "closed by the user");
        }

        Rect body = new(inRect.x, inRect.y + HeaderHeight + TabDrawer.TabHeight + 6f, inRect.width,
            inRect.height - HeaderHeight - TabDrawer.TabHeight - 6f);
        Widgets.DrawMenuSection(body);
        TabDrawer.DrawTabs(body, _records);
        Selected.Draw(body.ContractedBy(16f));
    }
}

/// <summary>Placeholder until the tab is implemented.</summary>
internal sealed class PendingTab(string id, string label) : IGuiTab
{
    public string Id => id;

    public string Label => label;

    public void Draw(Rect rect)
    {
        Widgets.Label(rect, "準備中です。");
    }
}

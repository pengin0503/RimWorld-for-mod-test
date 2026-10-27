using RimWorld;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// The GUI's UI root: the game's menu background and window stack with the
/// validation window, and nothing of UIRoot_Entry (no main menu, no dev tools).
/// </summary>
public sealed class ValidationUIRoot : UIRoot
{
    public override void Init()
    {
        base.Init();
        UIMenuBackgroundManager.background = new UI_BackgroundMain();
        windows.Add(new MainWindow());
    }

    public override void UIRootOnGUI()
    {
        base.UIRootOnGUI();
        UIMenuBackgroundManager.background.BackgroundOnGUI();
        ReorderableWidget.ReorderableWidgetOnGUI_BeforeWindowStack();
        DragAndDropWidget.DragAndDropWidgetOnGUI_BeforeWindowStack();
        windows.WindowStackOnGUI();
        DragAndDropWidget.DragAndDropWidgetOnGUI_AfterWindowStack();
        ReorderableWidget.ReorderableWidgetOnGUI_AfterWindowStack();
        Widgets.WidgetsOnGUI();
    }
}

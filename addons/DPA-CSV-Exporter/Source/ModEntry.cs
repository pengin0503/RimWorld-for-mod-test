using System;
using HarmonyLib;
using RimWorld;
using UnityEngine;
using Verse;

namespace DpaCsvExporter;

/// <summary>Inject a single export button into the Dubs Performance Analyzer window.</summary>
public sealed class DpaCsvExporterMod : Mod
{
    private string status = "Select a profiler entry in Dubs Performance Analyzer, then export all rows.";

    public DpaCsvExporterMod(ModContentPack content) : base(content)
    {
        LongEventHandler.ExecuteWhenFinished(() =>
        {
            try
            {
                var target = AccessTools.Method("Analyzer.Window_Analyzer:DoWindowContents");
                if (target == null)
                {
                    Log.Warning("[DPA CSV Exporter] Dubs Performance Analyzer window was not found.");
                    return;
                }
                new Harmony("pengin0503.dpa.csvexporter").Patch(target,
                    postfix: new HarmonyMethod(typeof(DpaCsvExporterMod), nameof(DrawExportButton)));
                Log.Message("[DPA CSV Exporter] Export CSV button attached.");
            }
            catch (Exception e)
            {
                Log.Error("[DPA CSV Exporter] Could not add export button: " + e);
            }
        });
    }

    public override string SettingsCategory() => "DPA CSV Exporter";

    public override void DoSettingsWindowContents(Rect rect)
    {
        var inner = rect.ContractedBy(12f);
        Widgets.Label(new Rect(inner.x, inner.y, inner.width, 65f),
            "Open Dubs Performance Analyzer and select a Tick, Update, GUI, or other profiler entry.\n" +
            "Export all rows in the active profiler, including rows hidden by its search filter.\n" +
            "CSV folder: RimWorld user data / AnalyzerExports");
        if (Widgets.ButtonText(new Rect(inner.x, inner.y + 75f, 250f, 34f), "Export all current measurements"))
            ExportWithFeedback();
        Widgets.Label(new Rect(inner.x, inner.y + 125f, inner.width, 75f), status);
    }

    // Harmony postfix to an existing window; never patch the measured code paths.
    public static void DrawExportButton(Rect rect)
    {
        try
        {
            // Clear the native close control; title-bar height is ~18 px.
            var button = new Rect(rect.xMax - 195f, rect.y + 1f, 118f, 18f);
            if (Widgets.ButtonText(button, "Export CSV"))
                ExportWithFeedback();
        }
        catch (Exception e)
        {
            Log.ErrorOnce("[DPA CSV Exporter] Export GUI error: " + e, 172890412);
        }
    }

    private static void ExportWithFeedback()
    {
        try
        {
            var path = Exporter.ExportCurrent();
            Log.Message("[DPA CSV Exporter] Saved: " + path);
            Messages.Message("DPA CSV saved: " + System.IO.Path.GetFileName(path),
                MessageTypeDefOf.TaskCompletion, false);
        }
        catch (Exception e)
        {
            Log.Warning("[DPA CSV Exporter] Export failed: " + e);
            Messages.Message("DPA CSV export failed: " + e.Message,
                MessageTypeDefOf.RejectInput, false);
        }
    }
}

using System;
using System.IO;
using System.Linq;
using Analyzer;
using DpaCsvExporter;
using HarmonyLib;
using RimWorld;
using UnityEngine;
using Verse;

static void Check(bool condition, string explanation)
{
    if (!condition) throw new InvalidOperationException(explanation);
}

string scratch = Path.Combine(Path.GetTempPath(), "rwmt-dpa-contract-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(scratch);
try
{
    // Only synthetic data. 1.7 game assemblies, private R2, and real DPA are absent.
    GenFilePaths.SaveDataFolderPath = scratch;
    Analyzer.Profiling.Analyzer.Logs.Add(new Analyzer.Profiling.ProfileLog());

    _ = new DpaCsvExporterMod(new ModContentPack());
    Check(Log.Errors.Count == 0, "DPA Harmony injection failed: " + string.Join("; ", Log.Errors));
    var original = AccessTools.Method(typeof(Window_Analyzer), nameof(Window_Analyzer.DoWindowContents));
    Check(original != null, "Synthetic DPA window target not found");
    var patch = Harmony.GetPatchInfo(original);
    Check(patch?.Postfixes.Any(p => p.owner == "pengin0503.dpa.csvexporter") == true,
        "Harmony exporter postfix is not installed on the synthetic DPA window");

    var window = new Window_Analyzer();
    window.DoWindowContents(new Rect(10f, 20f, 700f, 400f));
    Check(window.Calls == 1, "Synthetic DPA window original was skipped");
    Check(Widgets.ClickCount == 1, "Export CSV button was not drawn by Harmony");
    Check(Log.Errors.Count == 0, "Export failed: " + string.Join("; ", Log.Errors));
    Check(Messages.Notifications.Count == 1 && Messages.Notifications[0].StartsWith("DPA CSV saved: "),
        "Expected a successful export notification");

    var folder = Path.Combine(scratch, "AnalyzerExports");
    var files = Directory.GetFiles(folder, "*.csv", SearchOption.TopDirectoryOnly);
    Check(files.Length == 1, "Expected one exported CSV file");
    var bytes = File.ReadAllBytes(files[0]);
    Check(bytes.Length >= 3 && bytes[0] == 0xef && bytes[1] == 0xbb && bytes[2] == 0xbf,
        "CSV must have UTF-8 BOM for spreadsheet compatibility");
    var lines = File.ReadAllLines(files[0]);
    Check(lines.Length == 2, "Expected header and one DPA row");
    var header = lines[0].Split(',');
    var row = lines[1].Split(',');
    Check(header.Length == 29 && row.Length == 29, "Expected exactly 29 CSV columns");
    Check(header[9] == "measurement_cycles" && row[9] == "7",
        "DPA GetCurrentLogCount property not exported");
    Check(row[4] == "'=unsafe" && row[12] == "'=2+2",
        "Untrusted search/label text must be neutralized for spreadsheets");
    Check(row[5] == "85" && row[6] == "180" && row[7] == "360",
        "Synthetic FPS/TPS numeric metadata was not exported");
    Check(row[8] == "1.25" && row[27] == "3",
        "Numeric timing or phase information was not exported");
    Console.WriteLine("DPA Harmony injection and synthetic CSV end-to-end contract passed");
}
finally
{
    Directory.Delete(scratch, recursive: true);
}

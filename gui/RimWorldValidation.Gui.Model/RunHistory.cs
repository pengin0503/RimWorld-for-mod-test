using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace RimWorldValidation.Gui.Model;

public sealed record HistoryEntry(string Id, string Dir, bool HasResult, string? Status, string? StartedAt,
    IReadOnlyList<string> TargetLabels, bool Cancelled = false);

/// <summary>
/// The results folder holds one folder per GUI run: request.json and, once the
/// Controller finished, result/result.json. A run stopped from the GUI also
/// holds the empty file "cancelled".
/// </summary>
public static class RunHistory
{
    public const string RequestFile = "request.json";
    public const string ResultFolder = "result";
    public const string CancelledFile = "cancelled";

    public static string ResultJson(string runDir) => Path.Combine(runDir, ResultFolder, "result.json");

    public static IReadOnlyList<HistoryEntry> List(string resultsDir)
    {
        if (!Directory.Exists(resultsDir))
        {
            return [];
        }
        var entries = new List<HistoryEntry>();
        foreach (string dir in Directory.GetDirectories(resultsDir))
        {
            string id = Path.GetFileName(dir);
            if (id.StartsWith('.') || !File.Exists(Path.Combine(dir, RequestFile)) && !File.Exists(ResultJson(dir)))
            {
                continue;
            }
            ResultSummary? summary = null;
            if (File.Exists(ResultJson(dir)))
            {
                try
                {
                    summary = ResultSummary.Load(ResultJson(dir));
                }
                catch (Exception e) when (e is InvalidDataException or IOException)
                {
                    // A run still writing or broken: listed without a result.
                }
            }
            entries.Add(new HistoryEntry(id, dir, summary != null, summary?.Status, summary?.StartedAt,
                summary?.TargetLabels ?? RequestTargetNames(Path.Combine(dir, RequestFile)),
                File.Exists(Path.Combine(dir, CancelledFile))));
        }
        return entries.OrderByDescending(e => e.Id, StringComparer.Ordinal).ToList();
    }

    // Without a result (still running, stopped or crashed) the targets come from the request the GUI wrote.
    private static IReadOnlyList<string> RequestTargetNames(string requestPath)
    {
        try
        {
            return JsonNode.Parse(File.ReadAllText(requestPath))?["mods"] is JsonArray mods
                ? mods.OfType<JsonObject>().Where(m => ResultSummary.Bool(m["target"]) == true)
                    .Select(m => ResultSummary.LeafName(ResultSummary.Str(m["path"]))).ToList()
                : [];
        }
        catch (Exception e) when (e is JsonException or IOException or InvalidOperationException)
        {
            return [];
        }
    }

    public static string NewRunDir(string resultsDir, DateTime now)
    {
        string stamp = now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture);
        for (int n = 1; ; n++)
        {
            string dir = Path.Combine(resultsDir, n == 1 ? stamp : $"{stamp}-{n}");
            if (!Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
                return dir;
            }
        }
    }
}

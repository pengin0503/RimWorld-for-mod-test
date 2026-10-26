using System.Globalization;

namespace RimWorldValidation.Gui.Model;

public sealed record HistoryEntry(string Id, string Dir, bool HasResult, string? Status, string? StartedAt,
    IReadOnlyList<string> TargetNames);

/// <summary>
/// The results folder holds one folder per GUI run: request.json and, once the
/// Controller finished, result/result.json.
/// </summary>
public static class RunHistory
{
    public const string RequestFile = "request.json";
    public const string ResultFolder = "result";

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
            entries.Add(new HistoryEntry(id, dir, summary != null, summary?.Status, summary?.StartedAt, summary?.TargetNames ?? []));
        }
        return entries.OrderByDescending(e => e.Id, StringComparer.Ordinal).ToList();
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

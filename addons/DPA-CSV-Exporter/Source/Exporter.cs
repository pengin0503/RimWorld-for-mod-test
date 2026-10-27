using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Verse;

namespace DpaCsvExporter;

/// <summary>
/// Exports the complete published Analyzer.Logs table, including rows hidden by GUI filters.
/// No additional profiling is performed.
/// </summary>
public static class Exporter
{
    private const BindingFlags StaticPublic = BindingFlags.Public | BindingFlags.Static;
    private const BindingFlags InstancePublic = BindingFlags.Public | BindingFlags.Instance;
    private static readonly string[] Header = {
        "timestamp_utc", "rimworld_version", "category", "entry", "search_filter",
        "fps", "tps", "tps_target", "root_average_ms", "measurement_cycles", "rank",
        "key", "label", "mod", "assembly", "declaring_type", "method",
        "sample_entries", "average_ms_per_cycle", "self_ms_per_cycle", "max_ms_per_cycle",
        "total_ms", "total_calls", "calls_per_cycle", "fraction_of_root", "spike_count",
        "spike_severity", "phase_flags", "pinned"
    };
    private static readonly HashSet<int> Numeric = new() {
        5,6,7,8,9,10,17,18,19,20,21,22,23,24,25,26,27,28
    };

    private sealed class Row
    {
        public string Key = "", Label = "", Mod = "", Assembly = "", Type = "", Method = "";
        public int Entries, Spikes, Severity, Phase;
        public double Average, Self, Max, Total, Calls, Fraction;
        public bool Pinned;
    }

    private static Type RequireType(string name)
    {
        foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            var type = assembly.GetType(name, false);
            if (type != null) return type;
        }
        throw new InvalidOperationException("Dubs Performance Analyzer is not loaded: " + name);
    }

    private static object? Static(Type type, string name)
        => type.GetProperty(name, StaticPublic)?.GetValue(null)
           ?? type.GetField(name, StaticPublic)?.GetValue(null);

    private static object? Field(object instance, string name)
        => instance.GetType().GetField(name, InstancePublic)?.GetValue(instance);

    private static string Str(object? value) => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
    private static int Int(object? value) => value == null ? 0 : Convert.ToInt32(value, CultureInfo.InvariantCulture);
    private static double Num(object? value) => value == null ? 0 : Convert.ToDouble(value, CultureInfo.InvariantCulture);

    public static string ExportCurrent()
    {
        var analyzer = RequireType("Analyzer.Profiling.Analyzer");
        var gui = RequireType("Analyzer.Profiling.GUIController");
        var controller = RequireType("Analyzer.Profiling.ProfileController");
        var toolbar = RequireType("Analyzer.Profiling.Panel_TopRow");
        object? entry = Static(gui, "CurrentEntry");
        string category = Str(Static(gui, "CurrentCategory"));
        if (entry == null || category == "Settings")
            throw new InvalidOperationException("Select a Tick, Update, GUI or other profiling entry first.");

        var sync = Static(analyzer, "LogicLock")
                   ?? throw new InvalidOperationException("Dubs Analyzer.LogicLock not found.");
        var rows = new List<Row>();
        var modMap = ModAssemblyNames();

        // DPA swaps its entire log collection from a worker while holding this lock.
        // Do not hold references to mutable ProfileLog instances after leaving the lock.
        lock (sync)
        {
            var logs = Static(analyzer, "Logs") as IEnumerable
                       ?? throw new InvalidOperationException("Dubs Analyzer.Logs not found.");
            foreach (object? item in logs)
            {
                if (item == null) continue;
                var method = Field(item, "meth") as MethodBase;
                var type = Field(item, "type") as Type ?? method?.DeclaringType;
                string assFull = type?.Assembly.FullName ?? "";
                string mod = "";
                if (assFull.Length > 0 && modMap.TryGetValue(assFull, out var known))
                    mod = known;
                else if (assFull.StartsWith("Assembly-CSharp,", StringComparison.Ordinal))
                    mod = "RimWorld Core";
                rows.Add(new Row {
                    Key = Str(Field(item, "key")), Label = Str(Field(item, "label")), Mod = mod,
                    Assembly = type?.Assembly.GetName().Name ?? "", Type = type?.FullName ?? "",
                    Method = method?.ToString() ?? "",
                    Entries = Int(Field(item, "entries")),
                    Average = Num(Field(item, "average")),
                    Self = Num(Field(item, "self")),
                    Max = Num(Field(item, "max")),
                    Total = Num(Field(item, "total")),
                    Calls = Num(Field(item, "calls")),
                    Fraction = Num(Field(item, "percent")),
                    Spikes = Int(Field(item, "spikes")),
                    Severity = Int(Field(item, "spike")),
                    Phase = Int(Field(item, "seenIn")),
                    Pinned = Field(item, "pinned") is true
                });
            }
        }
        if (rows.Count == 0)
            throw new InvalidOperationException("No measurements yet. Start Dubs profiling and retry.");

        var now = DateTime.UtcNow;
        var timestamp = now.ToString("O", CultureInfo.InvariantCulture);
        string entryName = Str(Field(entry, "name"));
        int fps = Int(Static(toolbar, "fps")), tps = Int(Static(toolbar, "tps"));
        int tpsTarget = Int(Static(toolbar, "tpsTarget"));
        double rootAverage = Num(Static(controller, "updateAverage"));
        int cycles = Int(Static(analyzer, "GetCurrentLogCount"));
        string filter = Str(Static(toolbar, "TimesFilter"));

        string folder = Path.Combine(GenFilePaths.SaveDataFolderPath, "AnalyzerExports");
        Directory.CreateDirectory(folder);
        string fileName = now.ToString("yyyyMMdd-HHmmss-fff", CultureInfo.InvariantCulture)
            + "_" + SafeName(category) + "_" + SafeName(entryName)
            + "_" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".csv";
        string path = Path.Combine(folder, fileName);

        using var writer = new StreamWriter(path, false, new UTF8Encoding(true));
        writer.WriteLine(CsvFormat.Line(Header));
        for (int i = 0; i < rows.Count; i++)
        {
            var row = rows[i];
            string?[] fields = {
                timestamp, "1.7", category, entryName, filter,
                CsvFormat.Number(fps), CsvFormat.Number(tps), CsvFormat.Number(tpsTarget),
                CsvFormat.Number(rootAverage), CsvFormat.Number(cycles), CsvFormat.Number(i+1),
                row.Key, row.Label, row.Mod, row.Assembly, row.Type, row.Method,
                CsvFormat.Number(row.Entries), CsvFormat.Number(row.Average),
                CsvFormat.Number(row.Self), CsvFormat.Number(row.Max), CsvFormat.Number(row.Total),
                CsvFormat.Number(row.Calls),
                CsvFormat.Number(row.Entries == 0 ? 0 : row.Calls / row.Entries),
                CsvFormat.Number(row.Fraction), CsvFormat.Number(row.Spikes),
                CsvFormat.Number(row.Severity), CsvFormat.Number(row.Phase),
                row.Pinned ? "1" : "0"
            };
            writer.WriteLine(CsvFormat.Line(fields, Numeric));
        }
        return path;
    }

    private static Dictionary<string,string> ModAssemblyNames()
    {
        var mapping = new Dictionary<string,string>(StringComparer.Ordinal);
        var cache = AppDomain.CurrentDomain.GetAssemblies()
            .Select(a => a.GetType("Analyzer.ModInfoCache", false)).FirstOrDefault(t => t != null);
        if (cache != null && Static(cache, "AssemblyToModname") is IDictionary source)
            foreach (DictionaryEntry kv in source)
                if (kv.Key is string key && kv.Value is string value) mapping[key] = value;

        foreach (var mod in LoadedModManager.RunningMods)
            foreach (var assembly in mod.assemblies.loadedAssemblies)
                if (assembly.FullName != null && !mapping.ContainsKey(assembly.FullName))
                    mapping[assembly.FullName] = mod.Name;
        return mapping;
    }

    private static string SafeName(string text)
    {
        var invalid = Path.GetInvalidFileNameChars();
        string cleaned = new(text.Select(c =>
            Array.IndexOf(invalid, c) >= 0 || c == '/' || c == '\\' || c == ':' ? '_' : c).ToArray());
        cleaned = cleaned.Trim();
        return cleaned.Length == 0 ? "unknown" : cleaned.Length > 48 ? cleaned.Substring(0,48) : cleaned;
    }
}

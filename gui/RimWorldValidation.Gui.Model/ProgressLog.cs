using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace RimWorldValidation.Gui.Model;

/// <summary>One step of a run as the Controller logged it, with a Japanese line to show.</summary>
public sealed record ProgressEntry(double Seconds, string Kind, string? Run, string? Level, string Text);

/// <summary>
/// The progress log (progress.jsonl) the Controller appends to while a run goes:
/// one JSON object per line, flushed at once, kept when the run is stopped.
/// </summary>
public static class ProgressLog
{
    public const string FileName = "progress.jsonl";

    public static IReadOnlyList<ProgressEntry> ReadAll(string path) => new ProgressLogReader(path).ReadNew();

    public static ProgressEntry Describe(JsonObject e)
    {
        string kind = ResultSummary.Str(e["kind"]) ?? "unknown";
        string? run = ResultSummary.Str(e["run"]);
        string? level = ResultSummary.Str(e["level"]);
        string prefix = run switch
        {
            "baseline" => "［比較用（対象なし）］",
            "target" => "［対象あり］",
            null => "",
            _ => $"［{run}］",
        };
        string text = kind switch
        {
            "started" => "検証を始めました。",
            "modsInspectionProgress" => $"MOD の確認: {Int(e["completed"])} / {Int(e["total"])} 件。",
            "modsInspecting" => $"MOD {Int(e["count"])} 件の中身を確かめています（全ファイルのハッシュ）。",
            "modsInspected" => $"MOD {Int(e["count"])} 件（対象 {Int(e["targets"])}）、{Int(e["files"])} ファイル・{Size(e["bytes"])}を確かめました（{Seconds(e["seconds"])}）。",
            "baselineCached" => "比較用（対象なし）は、同じ条件の前回の結果を使います。",
            "runPreparing" => $"MOD {Int(e["mods"])} 件・{Size(e["bytes"])}を実行用のフォルダへコピーしています。",
            "runPrepared" => $"準備ができました（{Seconds(e["seconds"])}）。",
            "workerStarted" => $"ゲームの処理を始めました（上限 {Int(e["timeoutSeconds"])} 秒）。",
            "workerStage" => $"段階：{ResultSummary.Str(e["stage"])}",
            "event" => $"{(level == "error" ? "エラー" : "警告")}（{ResultSummary.Str(e["stage"])}）：{ResultSummary.Str(e["message"])}",
            "eventsCapped" => $"エラー・警告が {Int(e["limit"])} 件を超えたので、ここには以降を写しません（結果には残ります）。",
            "workerFinished" => $"ゲームの処理が終わりました（{Seconds(e["seconds"])}、終了コード {Int(e["exitCode"])}{Killed(ResultSummary.Str(e["killedFor"]))}）。"
                + (e["noiseSkipped"] is JsonValue noise && noise.TryGetValue(out int skipped) && skipped > 0
                    ? $"既知のエンジンのメッセージ {skipped} 件はここには写していません（判定にも入りません）。" : ""),
            "finished" => $"検証が終わりました：{ReasonCatalog.StatusLabel(ResultSummary.Str(e["status"]) ?? "")}（{Seconds(e["seconds"])}）。",
            _ => kind,
        };
        double t = e["t"] is JsonValue value && value.TryGetValue(out double seconds) ? seconds : 0;
        return new ProgressEntry(t, kind, run, kind == "event" ? level : null, prefix + text);
    }

    /// <summary>Bytes as people read them: "1.5 MB", "3.2 GB".</summary>
    public static string Size(JsonNode? node)
    {
        double bytes = node is JsonValue value && value.TryGetValue(out double number) ? number : 0;
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        int unit = 0;
        while (bytes >= 1024 && unit < units.Length - 1)
        {
            bytes /= 1024;
            unit++;
        }
        return unit == 0 ? $"{bytes:F0} B" : string.Create(CultureInfo.InvariantCulture, $"{bytes:F1} {units[unit]}");
    }

    private static string Int(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out double number) ? ((long)number).ToString(CultureInfo.InvariantCulture) : "－";

    private static string Seconds(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out double number)
            ? string.Create(CultureInfo.InvariantCulture, $"{number:F1} 秒") : "－";

    private static string Killed(string? reason) => reason switch
    {
        null => "",
        "timeout" => "、時間切れで止めました",
        "memoryLimit" => "、メモリの上限で止めました",
        "logLimit" => "、ログの上限で止めました",
        _ => $"、{reason} で止めました",
    };
}

/// <summary>Reads what was added to a progress log since the last call; an unfinished last line waits for the next call.</summary>
public sealed class ProgressLogReader(string path)
{
    private long _offset;
    private readonly List<byte> _pending = [];

    public string Path { get; } = path;

    public IReadOnlyList<ProgressEntry> ReadNew()
    {
        byte[] data;
        try
        {
            using var stream = new FileStream(Path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            stream.Seek(_offset, SeekOrigin.Begin);
            using var buffer = new MemoryStream();
            stream.CopyTo(buffer);
            data = buffer.ToArray();
        }
        catch (Exception e) when (e is FileNotFoundException or DirectoryNotFoundException or IOException or UnauthorizedAccessException)
        {
            return [];
        }
        _offset += data.Length;
        _pending.AddRange(data);
        var entries = new List<ProgressEntry>();
        int newline;
        while ((newline = _pending.IndexOf((byte)'\n')) >= 0)
        {
            string line = Encoding.UTF8.GetString(_pending.GetRange(0, newline).ToArray());
            _pending.RemoveRange(0, newline + 1);
            try
            {
                if (JsonNode.Parse(line) is JsonObject entry)
                {
                    entries.Add(ProgressLog.Describe(entry));
                }
            }
            catch (JsonException)
            {
                // A broken line (a crash mid-write) is skipped; the rest of the log still shows.
            }
        }
        return entries;
    }
}

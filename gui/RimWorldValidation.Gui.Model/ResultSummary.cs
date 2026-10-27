using System.Text.Json;
using System.Text.Json.Nodes;

namespace RimWorldValidation.Gui.Model;

public sealed record Reason(string Code, string Detail);

/// <summary>A diagnostic new in the target run. The Controller leaves the annotated ones out of the verdict.</summary>
public sealed record Diagnostic(string Level, string Category, string Stage, string FirstLine, string Text,
    string? KnownNoise, string? AllowedBy, string? SupersededBy = null)
{
    public bool Counted => KnownNoise == null && AllowedBy == null && SupersededBy == null;
}

public sealed record BillCheck(string Recipe, string Thing, bool? ExpectedVisible, bool? ActualVisible,
    bool? ExpectedAllowed, bool? ActualAllowed, string Outcome, IReadOnlyList<string> Reasons,
    string? ObservationReason, string? ObservationError);

/// <summary>
/// What the GUI shows of one result.json written by tools/validation_host.py.
/// It reads the Controller's verdict and never judges; sections the result
/// does not have are empty, so older or partial results still display.
/// </summary>
public sealed class ResultSummary
{
    public required string Status { get; init; }
    public string? ExecutionStatus { get; init; }
    public string? Fidelity { get; init; }
    public string? Platform { get; init; }
    public string? StartedAt { get; init; }
    public required IReadOnlyList<Reason> Reasons { get; init; }
    public required IReadOnlyList<string> TargetPackageIds { get; init; }
    public required IReadOnlyList<string> TargetNames { get; init; }

    /// <summary>Each target by its packageId, or by its folder when the result has none.</summary>
    public IReadOnlyList<string> TargetLabels =>
        TargetPackageIds.Zip(TargetNames, (id, name) => string.IsNullOrEmpty(id) ? name : id).ToList();
    public required IReadOnlyList<Diagnostic> NewDiagnostics { get; init; }
    public required IReadOnlyList<BillCheck> BillChecks { get; init; }
    public string? MapImage { get; init; }
    public string? MapBaselineImage { get; init; }
    public required IReadOnlyList<string> Checked { get; init; }
    public required IReadOnlyList<string> NotChecked { get; init; }
    public double? TotalSeconds { get; init; }

    public static ResultSummary Load(string path)
    {
        JsonObject root;
        try
        {
            root = JsonNode.Parse(File.ReadAllText(path))?.AsObject() ?? throw new InvalidDataException($"{path} is empty");
        }
        catch (Exception e) when (e is JsonException or InvalidOperationException)
        {
            throw new InvalidDataException($"{path} is not a JSON object: {e.Message}", e);
        }
        if (Str(root["recordType"]) != "modValidationResult")
        {
            throw new InvalidDataException($"{path} is not a modValidationResult");
        }
        var targets = Objects(root["mods"]).Where(m => Bool(m["target"]) == true).ToList();
        return new ResultSummary
        {
            Status = Str(root["status"]) ?? "unknown",
            ExecutionStatus = Str(root["executionStatus"]),
            Fidelity = Str(root["fidelity"]),
            Platform = Str(root["platform"]),
            StartedAt = Str(root["startedAt"]),
            Reasons = Objects(root["reasons"]).Select(r => new Reason(Str(r["code"]) ?? "unknown", Str(r["detail"]) ?? "")).ToList(),
            TargetPackageIds = targets.Select(m => Str(m["packageId"]) ?? "").ToList(),
            TargetNames = targets.Select(m => LeafName(Str(m["sourcePath"]))).ToList(),
            NewDiagnostics = Objects(root["diagnostics"]?["newInTarget"]).Select(ReadDiagnostic)
                .Concat(ReadTranslationErrors(root["diagnostics"]?["translationErrors"])).ToList(),
            BillChecks = Objects(root["checks"]?["billIngredients"]).Select(ReadBill).ToList(),
            MapImage = Str(root["map"]?["image"]),
            MapBaselineImage = Str(root["map"]?["baselineImage"]),
            Checked = Strings(root["scope"]?["checked"]),
            NotChecked = Strings(root["scope"]?["notChecked"]),
            TotalSeconds = Number(root["timings"]?["totalSeconds"]),
        };
    }

    internal static string LeafName(string? path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return "";
        }
        string trimmed = path.TrimEnd('/', '\\');
        int cut = trimmed.LastIndexOfAny(['/', '\\']);
        return cut < 0 ? trimmed : trimmed[(cut + 1)..];
    }

    private static Diagnostic ReadDiagnostic(JsonObject e)
    {
        string text = Str(e["message"]) ?? "";
        string firstLine = text.Split('\n', 2)[0].TrimEnd('\r');
        string? noise = e["knownNoise"] is JsonObject n ? Str(n["reason"]) ?? Str(n["id"]) : null;
        string? allowed = e["allowedBy"] is JsonObject a ? Str(a["reason"]) ?? Str(a["match"]) : null;
        return new Diagnostic(Str(e["level"]) ?? "", Str(e["category"]) ?? "", Str(e["stage"]) ?? "", firstLine, text, noise, allowed,
            Str(e["supersededBy"]));
    }

    private static BillCheck ReadBill(JsonObject c)
    {
        JsonNode? expected = c["expected"];
        JsonNode? actual = c["actual"];
        return new BillCheck(Str(expected?["recipe"]) ?? "", Str(expected?["thing"]) ?? "",
            Bool(expected?["visible"]), Bool(actual?["visible"]), Bool(expected?["allowed"]), Bool(actual?["allowed"]),
            Str(c["outcome"]) ?? "", Strings(actual?["reasons"]), Str(c["reason"]), Str(c["error"]));
    }

    private static IEnumerable<Diagnostic> ReadTranslationErrors(JsonNode? translation)
    {
        foreach (string error in Strings(translation?["notAllowed"]))
        {
            yield return TranslationDiagnostic(error, null);
        }
        foreach (JsonObject item in Objects(translation?["allowed"]))
        {
            yield return TranslationDiagnostic(Str(item["error"]) ?? "", Str(item["reason"]) ?? Str(item["match"]) ?? "allow");
        }
    }

    private static Diagnostic TranslationDiagnostic(string text, string? allowed) =>
        new("error", "translation", "loadPlayData", text.Split('\n', 2)[0].TrimEnd('\r'), text, null, allowed);

    internal static IEnumerable<JsonObject> Objects(JsonNode? node) =>
        node is JsonArray array ? array.OfType<JsonObject>() : [];

    internal static IReadOnlyList<string> Strings(JsonNode? node) =>
        node is JsonArray array ? array.Select(Str).OfType<string>().ToList() : [];

    internal static string? Str(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out string? text) ? text : null;

    internal static bool? Bool(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out bool flag) ? flag : null;

    private static double? Number(JsonNode? node) =>
        node is JsonValue value && value.TryGetValue(out double number) ? number : null;
}

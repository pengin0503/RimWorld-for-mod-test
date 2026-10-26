using System.Text.Json;
using System.Text.Json.Nodes;

namespace RimWorldValidation.Gui.Model;

/// <summary>
/// Written by tools/gui_host.py into the GUI's run directory: where the GUI's
/// private game layout is, where results go, and how to start the Controller.
/// </summary>
public sealed class GuiRequest
{
    public required string HostDir { get; init; }
    public required string UserDataDir { get; init; }
    public required string ResultsDir { get; init; }
    public required string SnapshotDir { get; init; }
    public required string Python { get; init; }
    public required string Controller { get; init; }
    public required string WorkerDir { get; init; }
    public required string BaselineCache { get; init; }
    /// <summary>Folder name under host/Mods → the mod's original folder (what a request must name).</summary>
    public required IReadOnlyDictionary<string, string> ModsMap { get; init; }
    public string? UserModsConfig { get; init; }
    /// <summary>Test-only list of steps (tab switches, screenshots, quit) run after the GUI is ready.</summary>
    public IReadOnlyList<JsonObject>? Script { get; init; }

    public static GuiRequest Load(string path)
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
        if (ResultSummary.Str(root["recordType"]) != "rwmtGuiRequest" || (int?)root["schemaVersion"] != 1)
        {
            throw new InvalidDataException($"{path} is not an rwmtGuiRequest v1");
        }
        string Required(string key) => ResultSummary.Str(root[key]) ?? throw new InvalidDataException($"{path}: {key} is missing");
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        if (root["modsMap"] is JsonObject mods)
        {
            foreach (var (name, value) in mods)
            {
                map[name] = ResultSummary.Str(value) ?? throw new InvalidDataException($"{path}: modsMap.{name} is not a string");
            }
        }
        return new GuiRequest
        {
            HostDir = Required("hostDir"),
            UserDataDir = Required("userDataDir"),
            ResultsDir = Required("resultsDir"),
            SnapshotDir = Required("snapshotDir"),
            Python = Required("python"),
            Controller = Required("controller"),
            WorkerDir = Required("workerDir"),
            BaselineCache = Required("baselineCache"),
            ModsMap = map,
            UserModsConfig = ResultSummary.Str(root["userModsConfig"]),
            Script = root["script"] is JsonArray steps ? steps.OfType<JsonObject>().ToList() : null,
        };
    }
}

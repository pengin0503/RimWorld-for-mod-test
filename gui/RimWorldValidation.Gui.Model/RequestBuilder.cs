using System.Text.Json;
using System.Text.Json.Nodes;

namespace RimWorldValidation.Gui.Model;

public sealed record ModChoice(string Path, bool Target);

public sealed record MapChoice(string Seed, string? Biome);

public sealed record BillChoice(string Recipe, string Thing, bool Visible, bool Allowed);

/// <summary>What the user chose on the GUI's tabs.</summary>
public sealed record RunSettings
{
    public IReadOnlyList<string> Official { get; init; } = ["Core"];
    public IReadOnlyList<ModChoice> Mods { get; init; } = [];
    public string Language { get; init; } = "English";
    public bool LevelB { get; init; }
    public MapChoice? Map { get; init; }
    public BillChoice? Bill { get; init; }
    /// <summary>Optional JSON object with "expectations" and/or "allow", for what the tabs do not cover.</summary>
    public string? ExtraJson { get; init; }
}

public sealed class RequestBuildException(string message) : Exception(message);

/// <summary>
/// Builds a modValidationRequest (docs/contracts/mod-validation-v1.md). The
/// Controller validates it again and stays the authority; this only catches
/// what the GUI can explain before starting a run.
/// </summary>
public static class RequestBuilder
{
    public const string BillCase = "bill-ingredient-options.v1";

    public static JsonObject Build(RunSettings settings)
    {
        if (settings.Mods.Count == 0)
        {
            throw new RequestBuildException("MOD を 1 つ以上選んでください。");
        }
        if (!settings.Mods.Any(m => m.Target))
        {
            throw new RequestBuildException("検証の対象にする MOD に印を付けてください。");
        }
        JsonObject extra = ParseExtra(settings.ExtraJson);
        var expectations = extra["expectations"] is JsonObject given ? (JsonObject)given.DeepClone() : new JsonObject();
        var levels = new JsonArray("A");
        if (settings.LevelB)
        {
            levels.Add("B");
        }
        var request = new JsonObject
        {
            ["recordType"] = "modValidationRequest",
            ["schemaVersion"] = 1,
            ["levels"] = levels,
            ["official"] = new JsonArray(settings.Official.Select(o => (JsonNode)JsonValue.Create(o)).ToArray()),
            ["mods"] = new JsonArray(settings.Mods.Select(m => (JsonNode)new JsonObject { ["path"] = m.Path, ["target"] = m.Target }).ToArray()),
            ["language"] = settings.Language,
        };
        if (settings.Bill is BillChoice bill)
        {
            levels.Add("C");
            request["tests"] = new JsonArray(BillCase);
            expectations["billIngredients"] = new JsonArray(new JsonObject
            {
                ["recipe"] = bill.Recipe, ["thing"] = bill.Thing, ["visible"] = bill.Visible, ["allowed"] = bill.Allowed,
            });
        }
        if (settings.Map is MapChoice map)
        {
            var mapObject = new JsonObject { ["seed"] = map.Seed };
            if (!string.IsNullOrWhiteSpace(map.Biome))
            {
                mapObject["biome"] = map.Biome;
            }
            request["map"] = mapObject;
        }
        if (expectations.Count > 0)
        {
            request["expectations"] = expectations;
        }
        if (extra["allow"] is JsonObject allow)
        {
            request["allow"] = allow.DeepClone();
        }
        return request;
    }

    private static JsonObject ParseExtra(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return [];
        }
        JsonNode? node;
        try
        {
            node = JsonNode.Parse(text);
        }
        catch (JsonException e)
        {
            throw new RequestBuildException($"追加の指定が JSON として読めません：{e.Message}");
        }
        if (node is not JsonObject extra)
        {
            throw new RequestBuildException("追加の指定は JSON のオブジェクト（{ ... }）で書いてください。");
        }
        foreach (var (key, value) in extra)
        {
            if (key is not ("expectations" or "allow"))
            {
                throw new RequestBuildException($"追加の指定に書けるのは expectations と allow だけです（{key} は画面で選んでください）。");
            }
            if (value is not JsonObject)
            {
                throw new RequestBuildException($"追加の指定の {key} はオブジェクトで書いてください。");
            }
        }
        if (extra["expectations"] is JsonObject e2 && e2.ContainsKey("billIngredients"))
        {
            throw new RequestBuildException("billIngredients は「製造指示の材料」の欄で指定してください。");
        }
        return extra;
    }
}

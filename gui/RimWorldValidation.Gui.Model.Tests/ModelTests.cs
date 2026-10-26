using System.Text.Json.Nodes;
using RimWorldValidation.Gui.Model;

namespace RimWorldValidation.Gui.Model.Tests;

public sealed class TempDir : IDisposable
{
    public string Path { get; } = Directory.CreateTempSubdirectory("rwmt-gui-").FullName;

    public string Write(string relative, string text)
    {
        string path = System.IO.Path.Combine(Path, relative);
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
        File.WriteAllText(path, text);
        return path;
    }

    public void Dispose() => Directory.Delete(Path, recursive: true);
}

public class ResultSummaryTests
{
    // The shape of a real Linux result (flour MOD, C mismatch), cut down to the fields the GUI shows.
    private const string FlourBug = """
    {
      "recordType": "modValidationResult", "schemaVersion": 1, "platform": "linux-x64",
      "startedAt": "2026-10-26T09:02:34Z",
      "status": "incomplete", "executionStatus": "completed", "fidelity": "experimental",
      "reasons": [
        {"code": "experimental", "detail": "this platform/runtime/build is not qualified"},
        {"code": "billIngredientMismatch", "detail": "1 ingredient option differs"}
      ],
      "mods": [{"packageId": "brrainz.harmony", "target": false, "sourcePath": "/m/2009463077"},
               {"packageId": "example.flour", "target": true, "sourcePath": "/m/flour"}],
      "checks": {"billIngredients": [{
        "caseId": "bill-ingredient-options.v1",
        "expected": {"recipe": "VCE_CookBakeSimple", "thing": "VCE_Flour", "visible": true, "allowed": true},
        "actual": {"visible": false, "allowed": true, "reasons": ["categoryNotVisible", "specialFilterDisallows"]},
        "outcome": "mismatch"}]},
      "diagnostics": {"newInTarget": [
        {"level": "warning", "category": "Verse", "stage": "loadPlayData",
         "message": "Could not resolve cross-reference\nsecond line"},
        {"level": "warning", "category": "Engine", "stage": "map", "message": "Persistent allocation",
         "knownNoise": {"id": "persistentAllocation", "reason": "engine shutdown"}}
      ]},
      "map": {"image": "/r/map.png", "baselineImage": "/r/map-baseline.png"},
      "scope": {"checked": ["loading"], "notChecked": ["ticks", "other platforms"]},
      "timings": {"totalSeconds": 8.095}
    }
    """;

    [Fact]
    public void reads_real_shape()
    {
        using var temp = new TempDir();
        var summary = ResultSummary.Load(temp.Write("result.json", FlourBug));
        Assert.Equal("incomplete", summary.Status);
        Assert.Equal("experimental", summary.Fidelity);
        Assert.Equal(["experimental", "billIngredientMismatch"], summary.Reasons.Select(r => r.Code));
        Assert.Equal(["example.flour"], summary.TargetPackageIds);
        Assert.Equal(["example.flour"], summary.TargetLabels);
        var bill = Assert.Single(summary.BillChecks);
        Assert.Equal(("VCE_CookBakeSimple", "VCE_Flour", true, false, "mismatch"),
            (bill.Recipe, bill.Thing, bill.ExpectedVisible, bill.ActualVisible, bill.Outcome));
        Assert.Equal(["categoryNotVisible", "specialFilterDisallows"], bill.Reasons);
        Assert.Equal(2, summary.NewDiagnostics.Count);
        Assert.Equal("Could not resolve cross-reference", summary.NewDiagnostics[0].FirstLine);
        Assert.Null(summary.NewDiagnostics[0].KnownNoise);
        Assert.Equal("engine shutdown", summary.NewDiagnostics[1].KnownNoise);
        Assert.Equal((true, false), (summary.NewDiagnostics[0].Counted, summary.NewDiagnostics[1].Counted));
        Assert.Equal("/r/map.png", summary.MapImage);
        Assert.Equal("/r/map-baseline.png", summary.MapBaselineImage);
        Assert.Equal(["ticks", "other platforms"], summary.NotChecked);
        Assert.Equal(8.095, summary.TotalSeconds);
        Assert.Equal("linux-x64", summary.Platform);
    }

    [Fact]
    public void missing_sections_are_empty()
    {
        using var temp = new TempDir();
        var summary = ResultSummary.Load(temp.Write("result.json",
            """{"recordType": "modValidationResult", "status": "blocked", "reasons": [{"code": "snapshotMissing"}]}"""));
        Assert.Equal("blocked", summary.Status);
        Assert.Equal("", summary.Reasons[0].Detail);
        Assert.Empty(summary.BillChecks);
        Assert.Empty(summary.NewDiagnostics);
        Assert.Empty(summary.NotChecked);
        Assert.Null(summary.MapImage);
        Assert.Null(summary.TotalSeconds);
    }

    [Fact]
    public void target_without_package_id_is_named_by_its_folder()
    {
        using var temp = new TempDir();
        var summary = ResultSummary.Load(temp.Write("result.json", """
            {"recordType": "modValidationResult", "status": "passed",
             "mods": [{"target": true, "sourcePath": "C:\\Mods\\Flour"}],
             "diagnostics": {"newInTarget": [{"level": "error", "message": "x", "allowedBy": {"match": "x"}},
                                              {"level": "warning", "message": "y", "supersededBy": "diagnostics.translationErrors"}]}}
            """));
        Assert.Equal(["Flour"], summary.TargetLabels);
        Assert.False(summary.NewDiagnostics[0].Counted);
        Assert.Equal((false, "diagnostics.translationErrors"), (summary.NewDiagnostics[1].Counted, summary.NewDiagnostics[1].SupersededBy));
    }

    [Fact]
    public void other_record_types_are_refused()
    {
        using var temp = new TempDir();
        Assert.Throws<InvalidDataException>(() => ResultSummary.Load(temp.Write("result.json", """{"recordType": "x"}""")));
        Assert.Throws<InvalidDataException>(() => ResultSummary.Load(temp.Write("broken.json", "{")));
    }
}

public class ReasonCatalogTests
{
    [Fact]
    public void unknown_reason_code_is_shown_as_is()
    {
        Assert.Equal("someFutureCode", ReasonCatalog.Describe("someFutureCode"));
    }

    [Fact]
    public void every_controller_reason_code_has_text()
    {
        foreach (string code in ReasonCatalog.KnownCodes)
        {
            string text = ReasonCatalog.Describe(code);
            Assert.NotEqual(code, text);
            Assert.False(string.IsNullOrWhiteSpace(text));
        }
        // Spot-check that the list follows tools/validation_host.py.
        Assert.Contains("platformMismatch", ReasonCatalog.KnownCodes);
        Assert.Contains("billIngredientMismatch", ReasonCatalog.KnownCodes);
        Assert.Contains("workerInterrupted", ReasonCatalog.KnownCodes);
        Assert.Contains("memoryLimit", ReasonCatalog.KnownCodes);
    }

    [Theory]
    [InlineData("passed", "合格")]
    [InlineData("failed", "不合格")]
    [InlineData("incomplete", "不完全")]
    [InlineData("blocked", "実行できず")]
    [InlineData("other", "other")]
    public void status_labels(string status, string label) => Assert.Equal(label, ReasonCatalog.StatusLabel(status));
}

public class RequestBuilderTests
{
    private static RunSettings Minimal() => new()
    {
        Official = ["Core", "Biotech"],
        Mods = [new ModChoice("/m/harmony", false), new ModChoice("/m/flour", true)],
        Language = "Japanese",
    };

    [Fact]
    public void builds_minimal_request()
    {
        JsonObject request = RequestBuilder.Build(Minimal());
        Assert.Equal("modValidationRequest", (string?)request["recordType"]);
        Assert.Equal(1, (int?)request["schemaVersion"]);
        Assert.Equal(["A"], request["levels"]!.AsArray().Select(n => (string?)n));
        Assert.Equal(["Core", "Biotech"], request["official"]!.AsArray().Select(n => (string?)n));
        Assert.Equal("Japanese", (string?)request["language"]);
        var mods = request["mods"]!.AsArray();
        Assert.Equal("/m/flour", (string?)mods[1]!["path"]);
        Assert.True((bool?)mods[1]!["target"]);
        Assert.False(request.ContainsKey("map"));
        Assert.False(request.ContainsKey("tests"));
    }

    [Fact]
    public void builds_map_and_bill_request()
    {
        RunSettings settings = Minimal() with
        {
            LevelB = true,
            Map = new MapChoice("rwmt", "TemperateForest"),
            Bill = new BillChoice("VCE_CookBakeSimple", "VCE_Flour", Visible: true, Allowed: true),
            ExtraJson = """
                {"expectations": {"defs": [{"type": "ThingDef", "defName": "VCE_Flour", "exists": true}]},
                 "allow": {"diagnostics": [{"level": "warning", "match": "x", "reason": "r"}]}}
                """,
        };
        JsonObject request = RequestBuilder.Build(settings);
        Assert.Equal(["A", "B", "C"], request["levels"]!.AsArray().Select(n => (string?)n));
        Assert.Equal(["bill-ingredient-options.v1"], request["tests"]!.AsArray().Select(n => (string?)n));
        Assert.Equal("TemperateForest", (string?)request["map"]!["biome"]);
        Assert.Equal("rwmt", (string?)request["map"]!["seed"]);
        var bill = request["expectations"]!["billIngredients"]!.AsArray().Single()!;
        Assert.Equal("VCE_Flour", (string?)bill["thing"]);
        Assert.True((bool?)bill["allowed"]);
        Assert.Equal("VCE_Flour", (string?)request["expectations"]!["defs"]![0]!["defName"]);
        Assert.Equal("r", (string?)request["allow"]!["diagnostics"]![0]!["reason"]);
    }

    [Fact]
    public void map_without_biome_leaves_the_choice_to_the_game()
    {
        JsonObject request = RequestBuilder.Build(Minimal() with { Map = new MapChoice("abc", null) });
        Assert.False(request["map"]!.AsObject().ContainsKey("biome"));
    }

    [Theory]
    [InlineData("{", "JSON")]
    [InlineData("[]", "オブジェクト")]
    [InlineData("""{"levels": ["A"]}""", "levels")]
    [InlineData("""{"expectations": []}""", "expectations")]
    [InlineData("""{"expectations": {"billIngredients": []}}""", "billIngredients")]
    public void invalid_extra_json_is_reported(string extra, string mentioned)
    {
        var error = Assert.Throws<RequestBuildException>(() => RequestBuilder.Build(Minimal() with { ExtraJson = extra }));
        Assert.Contains(mentioned, error.Message);
    }

    [Fact]
    public void mods_and_target_are_required()
    {
        Assert.Throws<RequestBuildException>(() => RequestBuilder.Build(Minimal() with { Mods = [] }));
        Assert.Throws<RequestBuildException>(() => RequestBuilder.Build(Minimal() with { Mods = [new ModChoice("/m/a", false)] }));
    }

    [Theory]
    [InlineData("", "BakeFlour", "レシピ")]
    [InlineData("Make_Flour", " ", "材料")]
    public void empty_bill_fields_are_reported(string recipe, string thing, string mentioned)
    {
        var error = Assert.Throws<RequestBuildException>(() =>
            RequestBuilder.Build(Minimal() with { Bill = new BillChoice(recipe, thing, true, true) }));
        Assert.Contains(mentioned, error.Message);
    }

    [Fact]
    public void empty_map_seed_is_reported()
    {
        var error = Assert.Throws<RequestBuildException>(() => RequestBuilder.Build(Minimal() with { Map = new MapChoice("  ", null) }));
        Assert.Contains("種", error.Message);
    }
}

public class ModsConfigReaderTests
{
    [Fact]
    public void reads_mods_config_active_list()
    {
        using var temp = new TempDir();
        string path = temp.Write("ModsConfig.xml", """
            <?xml version="1.0" encoding="utf-8"?>
            <ModsConfigData><version>1.7.4985 rev1269</version>
              <activeMods><li>brrainz.harmony</li><li>Ludeon.RimWorld</li><li> Example.Flour </li></activeMods>
              <knownExpansions><li>ludeon.rimworld.biotech</li></knownExpansions></ModsConfigData>
            """);
        Assert.Equal(["brrainz.harmony", "ludeon.rimworld", "example.flour"], ModsConfigReader.ReadActive(path));
    }

    [Fact]
    public void unreadable_config_is_an_error()
    {
        using var temp = new TempDir();
        Assert.Throws<InvalidDataException>(() => ModsConfigReader.ReadActive(temp.Write("ModsConfig.xml", "<ModsConfigData>")));
    }
}

public class RunHistoryTests
{
    [Fact]
    public void history_lists_unfinished_runs()
    {
        using var temp = new TempDir();
        temp.Write("20261026-100000/request.json", "{}");
        temp.Write("20261026-110000/request.json", "{}");
        temp.Write("20261026-110000/result/result.json", """
            {"recordType": "modValidationResult", "status": "passed", "startedAt": "2026-10-26T11:00:00Z",
             "mods": [{"packageId": "a.b", "target": true, "sourcePath": "/m/Flour"}]}
            """);
        temp.Write("20261026-120000/result/result.json", "{");
        temp.Write("not-a-run.txt", "");
        var entries = RunHistory.List(temp.Path);
        Assert.Equal(["20261026-120000", "20261026-110000", "20261026-100000"], entries.Select(e => e.Id));
        Assert.Equal((false, (string?)null), (entries[0].HasResult, entries[0].Status));
        Assert.Equal((true, "passed"), (entries[1].HasResult, entries[1].Status));
        Assert.Equal(["a.b"], entries[1].TargetLabels);
        Assert.False(entries[2].HasResult);
    }

    [Fact]
    public void history_marks_cancelled_runs_and_names_targets_from_the_request()
    {
        using var temp = new TempDir();
        temp.Write("20261026-130000/request.json", """
            {"mods": [{"path": "/m/Harmony", "target": false}, {"path": "C:\\Mods\\Flour", "target": true}]}
            """);
        File.WriteAllText(Path.Combine(temp.Path, "20261026-130000", RunHistory.CancelledFile), "");
        temp.Write("20261026-140000/request.json", "not json");
        var entries = RunHistory.List(temp.Path);
        Assert.Equal((false, false), (entries[0].HasResult, entries[0].Cancelled));
        Assert.Empty(entries[0].TargetLabels);
        Assert.Equal((false, true), (entries[1].HasResult, entries[1].Cancelled));
        Assert.Equal(["Flour"], entries[1].TargetLabels);
    }

    [Fact]
    public void missing_results_dir_is_empty_history() => Assert.Empty(RunHistory.List("/does/not/exist/rwmt"));

    [Fact]
    public void new_run_dir_is_unique()
    {
        using var temp = new TempDir();
        var now = new DateTime(2026, 10, 26, 10, 5, 7);
        string first = RunHistory.NewRunDir(temp.Path, now);
        string second = RunHistory.NewRunDir(temp.Path, now);
        Assert.Equal("20261026-100507", Path.GetFileName(first));
        Assert.Equal("20261026-100507-2", Path.GetFileName(second));
        Assert.True(Directory.Exists(first) && Directory.Exists(second));
    }
}

public class GuiRequestTests
{
    [Fact]
    public void gui_request_round_trip()
    {
        using var temp = new TempDir();
        string path = temp.Write("gui-request.json", """
            {"recordType": "rwmtGuiRequest", "schemaVersion": 1,
             "hostDir": "/run/host", "userDataDir": "/run/userdata", "resultsDir": "/r", "snapshotDir": "/s",
             "python": "/usr/bin/python3", "controller": "/repo/tools/validation_host.py", "workerDir": "/repo/worker/bin",
             "baselineCache": "/r/.baseline-cache", "modsMap": {"0-Harmony": "/m/harmony"},
             "userModsConfig": null, "script": [{"tab": "results"}, {"quit": true}]}
            """);
        GuiRequest request = GuiRequest.Load(path);
        Assert.Equal("/run/host", request.HostDir);
        Assert.Equal("/m/harmony", request.ModsMap["0-Harmony"]);
        Assert.Null(request.UserModsConfig);
        Assert.Equal(2, request.Script!.Count);
        Assert.Equal("results", (string?)request.Script[0]["tab"]);
    }

    [Fact]
    public void wrong_record_is_refused()
    {
        using var temp = new TempDir();
        Assert.Throws<InvalidDataException>(() => GuiRequest.Load(temp.Write("g.json", """{"recordType": "x", "schemaVersion": 1}""")));
    }
}

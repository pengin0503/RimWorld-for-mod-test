using System.Text.Json;
using System.Text.Json.Nodes;
using RimWorldValidation.Gui.Model;
using UnityEngine;

namespace RimWorldValidation.Gui;

/// <summary>
/// Test-only: runs the steps in gui-request.json's "script" once the GUI is
/// ready, so screens can be checked without a person at the window (cloud
/// screenshots). Each step is one object: {"tab": "mods"}, {"apply": RunSettings
/// as JSON}, {"importModsConfig": true}, {"selectMod": packageId},
/// {"run": true} (starts a validation), {"waitRun": true} (until it ends), {"waitSeconds": n} (time for input from outside, e.g. xdotool), {"screenshot": path}
/// or {"quit": true}. A step it does not know, or one that
/// cannot be done, ends the GUI with exit code 5.
/// </summary>
internal sealed class ScriptRunner(IReadOnlyList<JsonObject> steps)
{
    // Frames to let a tab switch lay out, and to let a screenshot be written.
    private const int SettleFrames = 10, CaptureFrames = 30;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private int _index, _waitUntil = -1;
    private float _waitUntilTime;
    private Func<bool>? _waitFor;

    public void Update(int frame)
    {
        if (_waitUntil < 0)
        {
            _waitUntil = frame + 60;  // the first frames after loading still settle textures
        }
        if (_waitFor != null)
        {
            if (!_waitFor())
            {
                return;
            }
            _waitFor = null;
            _waitUntil = frame + SettleFrames;
        }
        if (frame < _waitUntil || Time.realtimeSinceStartup < _waitUntilTime || _index >= steps.Count)
        {
            return;
        }
        JsonObject step = steps[_index++];
        try
        {
            _waitUntil = frame + Execute(step);
        }
        catch (Exception e) when (e is InvalidOperationException or FormatException or ArgumentException or JsonException)
        {
            Boot.Stop(Program.ScriptFailed, $"script step {_index} {step.ToJsonString()}: {e.Message}");
        }
    }

    private int Execute(JsonObject step)
    {
        if (step.Count != 1)
        {
            throw new InvalidOperationException("a step has exactly one key");
        }
        var (key, value) = step.First();
        switch (key)
        {
            case "tab":
                string id = value?.GetValue<string>() ?? throw new InvalidOperationException("tab needs a name");
                if (MainWindow.Instance?.Select(id) != true)
                {
                    throw new InvalidOperationException($"no tab {id}");
                }
                return SettleFrames;
            case "apply":
                GuiState.Apply(value?.Deserialize<RunSettings>(JsonOptions) ?? throw new InvalidOperationException("apply needs settings"));
                return SettleFrames;
            case "importModsConfig":
                GuiState.ImportUserModsConfig();
                return SettleFrames;
            case "selectMod":
                string packageId = value?.GetValue<string>() ?? throw new InvalidOperationException("selectMod needs a packageId");
                GuiState.Selected = GuiState.FindCandidate(packageId) ?? throw new InvalidOperationException($"no MOD {packageId}");
                return SettleFrames;
            case "screenshot":
                string path = value?.GetValue<string>() ?? throw new InvalidOperationException("screenshot needs a path");
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
                ScreenCapture.CaptureScreenshot(Path.GetFullPath(path));
                return CaptureFrames;
            case "run":
                if (!RunController.Start(GuiState.CurrentSettings()))
                {
                    throw new InvalidOperationException($"the validation did not start: {RunController.StartError}");
                }
                return SettleFrames;
            case "waitRun":
                _waitFor = () => !RunController.Running;
                return SettleFrames;
            case "waitSeconds":
                _waitUntilTime = Time.realtimeSinceStartup + (value?.GetValue<float>() ?? throw new InvalidOperationException("waitSeconds needs a number"));
                return SettleFrames;
            case "quit":
                Boot.Stop(Program.Closed, "test script finished");
                return CaptureFrames;
            default:
                throw new InvalidOperationException($"unknown step {key}");
        }
    }
}

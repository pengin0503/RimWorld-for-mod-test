using System.Text.Json.Nodes;
using UnityEngine;

namespace RimWorldValidation.Gui;

/// <summary>
/// Test-only: runs the steps in gui-request.json's "script" once the GUI is
/// ready, so screens can be checked without a person at the window (cloud
/// screenshots). Each step is one object: {"tab": "mods"}, {"screenshot": path}
/// or {"quit": true}. A step it does not know ends the GUI with exit code 5.
/// </summary>
internal sealed class ScriptRunner(IReadOnlyList<JsonObject> steps)
{
    // Frames to let a tab switch lay out, and to let a screenshot be written.
    private const int SettleFrames = 10, CaptureFrames = 30;
    private int _index, _waitUntil = -1;

    public void Update(int frame)
    {
        if (_waitUntil < 0)
        {
            _waitUntil = frame + 60;  // the first frames after loading still settle textures
        }
        if (frame < _waitUntil || _index >= steps.Count)
        {
            return;
        }
        JsonObject step = steps[_index++];
        try
        {
            _waitUntil = frame + Execute(step);
        }
        catch (Exception e) when (e is InvalidOperationException or FormatException or ArgumentException)
        {
            Boot.Stop(Program.ScriptFailed, $"script step {_index} {step.ToJsonString()}: {e.Message}");
        }
    }

    private static int Execute(JsonObject step)
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
            case "screenshot":
                string path = value?.GetValue<string>() ?? throw new InvalidOperationException("screenshot needs a path");
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
                ScreenCapture.CaptureScreenshot(Path.GetFullPath(path));
                return CaptureFrames;
            case "quit":
                Boot.Stop(Program.Closed, "test script finished");
                return CaptureFrames;
            default:
                throw new InvalidOperationException($"unknown step {key}");
        }
    }
}

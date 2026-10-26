using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;
using RimWorldValidation.Gui.Model;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// Starts one validation at a time: writes request.json into a new folder of
/// the results directory and runs the Controller (validation_host.py run) on
/// it. The GUI judges nothing; the Controller writes result/result.json.
/// </summary>
internal static class RunController
{
    private const int MaxOutputLines = 200;
    private static Process? _process;
    private static readonly ConcurrentQueue<string> Incoming = new();

    public static string? RunDir { get; private set; }

    public static DateTime StartedAt { get; private set; }

    public static int? ExitCode { get; private set; }

    public static bool Cancelled { get; private set; }

    public static string? StartError { get; private set; }

    public static List<string> Output { get; } = [];

    public static bool Running => _process is { HasExited: false };

    /// <summary>True while a run is going or its end has not been shown yet.</summary>
    public static bool Busy => _process != null;

    public static string ResultDir => Path.Combine(RunDir!, RunHistory.ResultFolder);

    /// <summary>Builds the request and starts the Controller. False (with StartError) when nothing was started.</summary>
    public static bool Start(RunSettings settings)
    {
        StartError = null;
        if (Busy)
        {
            StartError = "検証が実行中です。";
            return false;
        }
        GuiRequest request = GuiState.Request;
        string json;
        try
        {
            json = RequestBuilder.Build(settings).ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        }
        catch (RequestBuildException e)
        {
            StartError = e.Message;
            return false;
        }
        string runDir = RunHistory.NewRunDir(request.ResultsDir, DateTime.Now);
        string requestPath = Path.Combine(runDir, RunHistory.RequestFile);
        File.WriteAllText(requestPath, json);
        var start = new ProcessStartInfo(request.Python)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = runDir,
        };
        foreach (string argument in new[]
                 {
                     request.Controller, "run", "--snapshot", request.SnapshotDir, "--request", requestPath,
                     "--out", Path.Combine(runDir, RunHistory.ResultFolder), "--worker", request.WorkerDir,
                     "--baseline-cache", request.BaselineCache,
                 })
        {
            start.ArgumentList.Add(argument);
        }
        // The Controller prints UTF-8 whatever the console's code page is.
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        Output.Clear();
        Incoming.Clear();
        ExitCode = null;
        Cancelled = false;
        RunDir = runDir;
        StartedAt = DateTime.Now;
        try
        {
            _process = Process.Start(start) ?? throw new InvalidOperationException("the process did not start");
        }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            StartError = $"検証を始められませんでした（{request.Python}）：{e.Message}";
            File.WriteAllText(Path.Combine(runDir, RunHistory.CancelledFile), StartError);
            _process = null;
            return false;
        }
        _process.OutputDataReceived += (_, e) => { if (e.Data != null) Incoming.Enqueue(e.Data); };
        _process.ErrorDataReceived += (_, e) => { if (e.Data != null) Incoming.Enqueue(e.Data); };
        _process.BeginOutputReadLine();
        _process.BeginErrorReadLine();
        Find.WindowStack.Add(new RunProgressWindow());
        return true;
    }

    /// <summary>Called every frame by the progress window: collects output and notices the end.</summary>
    public static void Update()
    {
        while (Incoming.TryDequeue(out string? line))
        {
            Output.Add(line);
            if (Output.Count > MaxOutputLines)
            {
                Output.RemoveAt(0);
            }
        }
        if (_process is { HasExited: true } && ExitCode == null)
        {
            _process.WaitForExit();  // drains the redirected output
            ExitCode = _process.ExitCode;
        }
    }

    /// <summary>The phase, from the folders the Controller makes in its output directory.</summary>
    public static string Phase()
    {
        if (RunDir == null)
        {
            return "";
        }
        string result = ResultDir;
        if (File.Exists(Path.Combine(result, "result.json")))
        {
            return "結果を書き終えました";
        }
        if (Directory.Exists(Path.Combine(result, "target")))
        {
            return "対象の MOD を入れて実行中";
        }
        if (Directory.Exists(Path.Combine(result, "baseline")))
        {
            return "比較用（対象なし）を実行中";
        }
        return "準備中（入力の確認・MOD の写し）";
    }

    /// <summary>Stops the Controller and everything it started (the Worker runs in its own group or job under it).</summary>
    public static void Cancel()
    {
        if (!Running)
        {
            return;
        }
        Cancelled = true;
        try
        {
            _process!.Kill(entireProcessTree: true);
        }
        catch (Exception e) when (e is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            // Ended on its own meanwhile.
        }
        File.WriteAllText(Path.Combine(RunDir!, RunHistory.CancelledFile), $"stopped from the GUI at {DateTime.Now:O}\n");
        RemoveRunHosts();
    }

    // A stopped Controller leaves its runs' host/ folders: links into the read-only snapshot. They are
    // removed with the Controller's own routine, which never enters a link and never clears the
    // read-only attribute a Windows hard link shares with the snapshot.
    private static void RemoveRunHosts()
    {
        _process!.WaitForExit(10_000);
        var start = new ProcessStartInfo(GuiState.Request.Python) { UseShellExecute = false, CreateNoWindow = true };
        foreach (string argument in new[]
                 {
                     "-c",
                     "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import validation_host as vh; "
                     + "[vh.remove_run_host(host) for host in Path(sys.argv[2]).glob('*/host')]",
                     Path.GetDirectoryName(GuiState.Request.Controller)!, ResultDir,
                 })
        {
            start.ArgumentList.Add(argument);
        }
        try
        {
            Process.Start(start)?.Dispose();
        }
        catch (System.ComponentModel.Win32Exception e)
        {
            Output.Add($"後片付けを始められませんでした：{e.Message}");
        }
    }

    /// <summary>Forgets the finished run so a new one can start.</summary>
    public static void Clear()
    {
        _process?.Dispose();
        _process = null;
    }
}

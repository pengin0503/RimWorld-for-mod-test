using System.Diagnostics;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// Entry point of the validation worker. It is started only by the Controller
/// (tools/validation_host.py) inside a prepared run directory, with
/// <c>--worker-request &lt;path&gt;</c>. It never shows a window, never accepts
/// interactive input and always exits after one finite load.
/// Exit codes: 0 completed, 2 bad invocation or request, 3 failed/interrupted,
/// 4 adapter mismatch (this game build lacks a member the worker needs).
/// </summary>
public static class Program
{
    public static int Main(string[] args)
    {
        var clock = Stopwatch.StartNew();
        if (args.Length != 2 || args[0] != "--worker-request")
        {
            Console.Error.WriteLine("usage: RimWorldValidationWorker --worker-request <path>");
            Console.Error.WriteLine("This program is started by tools/validation_host.py; it is not a game launcher.");
            return 2;
        }
        WorkerRequest request;
        try
        {
            request = WorkerRequest.Load(args[1]);
        }
        catch (Exception e) when (e is IOException or JsonException or InvalidDataException or KeyNotFoundException or InvalidOperationException or UnauthorizedAccessException)
        {
            Console.Error.WriteLine($"invalid worker request: {e.Message}");
            return 2;
        }

        if (!System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription.Contains("waylithclr", StringComparison.OrdinalIgnoreCase))
        {
            InstallStandardRuntimeRedirects(request.HostDir);
        }
        return RunWorker(request, clock);
    }

    // Separate method so that the usage/request checks above work without the
    // game's Microsoft.Extensions.Logging assemblies, which this method needs.
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    private static int RunWorker(WorkerRequest request, Stopwatch clock)
    {
        GameApi api;
        try
        {
            api = GameApi.Bind();
        }
        catch (AdapterMismatchException e)
        {
            WriteMinimalResult(request, clock, "adapterMismatch", e.Message);
            return 4;
        }

        using var diagnostics = new Diagnostics(request.EventsPath, clock, request.MaxDiagnostics, request.MaxMessageBytes, request.MaxEventBytes);
        var host = new Host(request, api, diagnostics, clock);
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            // Last chance: keep the evidence. The process terminates after this handler.
            diagnostics.Record("error", "Worker", "unhandled exception", e.ExceptionObject as Exception);
            try
            {
                host.WriteResult("failed", $"unhandled exception: {(e.ExceptionObject as Exception)?.GetType().FullName}");
            }
            catch (Exception)
            {
                // The Controller treats a missing result as a crash.
            }
        };
        int code;
        try
        {
            code = host.Run();
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            diagnostics.Record("error", "Worker", "worker failed before the engine loop ended", e);
            host.WriteResult("failed", $"worker failed: {e.GetType().Name}: {e.Message}");
            code = 3;
        }
        diagnostics.Dispose();
        // Engine and game threads (audio, jobs, long events) must not keep the process alive.
        Environment.Exit(code);
        return code;
    }

    // Experimental standard .NET mode only. WaylithClr redirects these names itself
    // (runtimeconfig WaylithClr.AssemblyNameRedirects); the stock runtime does not, and
    // its other WaylithClr behaviours (lax binding, Mono hash codes, ...) are not
    // reproduced at all, which is why the Controller never qualifies such a run.
    private static void InstallStandardRuntimeRedirects(string hostDir)
    {
        string stubs = Path.Combine(hostDir, "UnityStubs.dll");
        System.Runtime.Loader.AssemblyLoadContext.Default.Resolving += (context, name) =>
        {
            string simple = name.Name ?? "";
            if (simple.StartsWith("UnityEngine", StringComparison.Ordinal) || simple.StartsWith("Unity.", StringComparison.Ordinal)
                || simple == "Assembly-CSharp-firstpass")
            {
                return context.LoadFromAssemblyPath(stubs);
            }
            return null;
        };
    }

    private static void WriteMinimalResult(WorkerRequest request, Stopwatch clock, string executionStatus, string failure)
    {
        string temp = request.ResultPath + ".tmp";
        using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write))
        using (var json = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = true }))
        {
            json.WriteStartObject();
            json.WriteString("recordType", "rwmtWorkerResult");
            json.WriteNumber("schemaVersion", 1);
            json.WriteString("runId", request.RunId);
            json.WriteString("nonce", request.Nonce);
            json.WriteString("executionStatus", executionStatus);
            json.WriteString("failure", failure);
            json.WriteNumber("elapsedSeconds", Math.Round(clock.Elapsed.TotalSeconds, 3));
            json.WriteEndObject();
        }
        File.Move(temp, request.ResultPath, overwrite: true);
    }
}

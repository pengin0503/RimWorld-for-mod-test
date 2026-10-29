using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace RimWorldValidation.Worker;

/// <summary>
/// Drives the real engine in headless mode through a finite, ordered subset of
/// the official boot (Program.Main → EngineApplication → Bootstrap.Initialize →
/// Root.Start/CheckGlobalInit), replacing only the Entry scene (main menu,
/// autostart save, UI/sound roots) with a fixed sequence that ends the process.
/// The order and every skipped step are listed in docs/research/test-host-entrypoints.md.
/// </summary>
public sealed class Host(WorkerRequest request, GameApi api, MapApi? mapApi, Diagnostics diagnostics, Stopwatch clock)
{
    public static readonly string[] SkippedOfficialSteps =
    [
        "Verse.Steam.SteamManager.InitIfNeeded: not called; Steam and Workshop content are outside the run so only the requested mods can be found",
        "RimWorldWaylith.Bootstrap.SpawnEntryScene / Root_Entry: not created; no main menu, music, UIRoot or SoundRoot",
        "Root_Entry autostart save loading: not executed",
        "Root.Start 'InitializingInterface' long event (UIRoot/SoundRoot init): not queued",
        "RimWorldWaylith.Bootstrap.RegisterResources (WorldText prefab, AudioMixer) and RegisterExecutionOrders: not executed",
        "AssetBakeHooks.RaiseBootComplete (texture cache sweep) and after-boot switches: not executed",
    ];

    public static readonly string[] Deviations =
    [
        "Prefs devMode=true so the official ErrorCheckAllDefs pass runs (default installs skip it)",
        "Prefs resetModsConfigOnCrash=false so a load exception is reported instead of silently retrying with Core only",
        "Shader prewarm disabled, as the official headless path also does",
    ];

    private readonly List<Stage> _stages = [];
    private object? _app;
    private object? _unityRuntime;
    private Action<float, float>? _beginFrame;
    private Action<float, float>? _update;
    private int _frames;
    private bool _queued;
    private volatile bool _markerRan;
    private volatile Exception? _loadException;
    private int _finished;
    private Stage? _loadStage;
    private Stage? _lateStage;
    private Stage? _mapStage;
    private MapStage? _map;
    private readonly EventChoice _eventChoice = new();
    private volatile Exception? _mapException;
    private Dictionary<string, object?>? _mapSummary;

    private BoundedTickRunner? _ticks;
    private TickApi? _tickApi;
    private string? _tickInitialization;
    private string? _tickError;
    private int _tickErrorsBefore;

    public int ExitCode { get; private set; } = 3;

    private sealed class Stage(string name, double start)
    {
        public string Name { get; } = name;
        public double Start { get; } = start;
        public double? End { get; set; }
        public string Status { get; set; } = "started";
        public Dictionary<string, object?> Evidence { get; } = new();
    }

    private Stage Begin(string name)
    {
        Diagnostics.Stage = name;
        var stage = new Stage(name, clock.Elapsed.TotalSeconds);
        lock (_stages)
        {
            _stages.Add(stage);
        }
        return stage;
    }

    private void Complete(Stage stage, string status = "completed")
    {
        stage.End = clock.Elapsed.TotalSeconds;
        stage.Status = status;
    }

    public int Run()
    {
        Diagnostics.MainThreadId = Environment.CurrentManagedThreadId;
        api.LogSystemIsEnabled.SetValue(null, true);
        api.LogSystemInitialize.Invoke(null, [(Action<ILoggingBuilder>)(builder =>
        {
            builder.AddProvider(diagnostics);
            builder.SetMinimumLevel(LogLevel.Debug);
        })]);
        Environment.SetEnvironmentVariable("MONOMOD_DMDType", "dynamicmethod");
        api.FileLogSetDirectory(Path.Combine(request.UserDataDir, "logs"));

        object options = Activator.CreateInstance(api.EngineApplicationOptions)!;
        Set(options, "Title", "RimWorld MOD validation worker");
        Set(options, "Headless", true);
        Set(options, "ShowCrashDialog", false);
        Set(options, "AudioBackend", Activator.CreateInstance(api.MiniAudioBackend));
        Type initType = typeof(Action<>).MakeGenericType(api.EngineApplication);
        Delegate init = Delegate.CreateDelegate(initType, this, typeof(Host).GetMethod(nameof(OnEngineInit), BindingFlags.NonPublic | BindingFlags.Instance)!);
        Stage engine = Begin("engineInit");
        // Game code can hold the main thread for seconds (static constructors, atlas
        // baking), so the per-frame deadline check alone cannot always stop the run.
        // A dedicated thread, because the loader can keep the thread pool busy.
        new Thread(() =>
        {
            Thread.Sleep(TimeSpan.FromSeconds(request.DeadlineSeconds + WatchdogGraceSeconds));
            Watchdog();
        }) { IsBackground = true, Name = "rwmt-watchdog" }.Start();
        int rc = (int)api.EngineRun.Invoke(null, [options, init])!;
        if (engine.Status == "started")
        {
            Complete(engine, "failed");
        }
        if (TryFinish())
        {
            WriteResult("failed", $"engine run loop ended before the worker finished (engine exit code {rc})");
            ExitCode = 3;
        }
        return ExitCode;
    }

    private static void Set(object target, string property, object? value)
    {
        Reflect.InstanceProperty(target.GetType(), property).SetValue(target, value);
    }

    // Mirrors Bootstrap.Initialize/ConfigureRuntime for the headless case with explicit paths
    // under the run directory instead of the user's profile.
    private void OnEngineInit(object app)
    {
        _app = app;
        Stage stage = _stages[^1];
        object runtime = api.AppRuntime.GetValue(app)!;
        _unityRuntime = api.UnityRuntimeCtor.Invoke([runtime]);
        Type unityType = _unityRuntime.GetType();
        object appState = Reflect.InstanceProperty(unityType, "App").GetValue(_unityRuntime)!;
        Set(appState, "ProductName", "RimWorld by Ludeon Studios");
        Set(appState, "Version", typeof(Host).Assembly.GetName().Version?.ToString() ?? "0.0.0");
        Set(appState, "IsEditor", false);
        string userData = request.UserDataDir;
        Reflect.InstanceMethod(unityType, "ConfigurePaths", typeof(string), typeof(string), typeof(string), typeof(string), typeof(string))
            .Invoke(_unityRuntime, [Path.Combine(request.HostDir, "RimWorld_Data"), userData, Path.Combine(userData, "tmp"), Path.Combine(userData, "logs"), userData]);
        api.ShaderCacheDirectory(Path.Combine(userData, "ShaderCache"));

        string dataPath = (string)Reflect.InstanceProperty(appState.GetType(), "DataPath").GetValue(appState)!;
        object commandLine = Reflect.InstanceProperty(api.EngineApplicationOptions, "CommandLineAccessor")
            .GetValue(Reflect.InstanceProperty(api.EngineApplication, "Options").GetValue(app))!;
        string packPath = Path.Combine(request.HostDir, "Assets.zip");
        object? pack = api.AssetPackOpen.Invoke(null, [dataPath, commandLine, packPath]);
        int hashes = pack == null ? 0 : ((System.Collections.ICollection)Reflect.Member(pack, "ContentHashes")!).Count;
        stage.Evidence["assetPackEntries"] = pack == null ? null : Reflect.Member(pack, "Count");
        stage.Evidence["assetPackManifestEntries"] = hashes;
        // Same rule as Bootstrap.ConfigureRuntime, minus the -NoAssetPack escape hatch.
        if (hashes == 0 && !Directory.Exists(Path.Combine(dataPath, "Resources", "Textures")))
        {
            throw new InvalidOperationException($"asset pack {packPath} is missing or has no manifest");
        }

        Action<string> error = message => diagnostics.Record("error", "Engine", message, null);
        Action<string> warning = message => diagnostics.Record("warning", "Engine", message, null);
        api.JobErrorHandler(error);
        api.GraphicsErrorHandler(error);
        api.GraphicsWarningHandler(warning);

        MethodInfo registerQuit = Reflect.InstanceMethod(appState.GetType(), "RegisterQuitHandler", typeof(Action<string>));
        registerQuit.Invoke(appState, [(Action<string>)(reason =>
        {
            diagnostics.Record("warning", "Worker", $"game code requested application quit: {reason}", null);
            Quit(3);
        })]);

        SetShaderWarmup(false);
        api.RegisterShaderSourceDirectory(Path.Combine(request.HostDir, "Rendering", "Shaders"));
        Type preType = api.AppPrePollEvents.EventHandlerType!;
        api.AppPrePollEvents.AddEventHandler(app, Delegate.CreateDelegate(preType, this,
            typeof(Host).GetMethod(nameof(OnPrePoll), BindingFlags.NonPublic | BindingFlags.Instance)!));
        _beginFrame = Reflect.Delegate<Action<float, float>>(Reflect.InstanceMethod(unityType, "BeginFrame", typeof(float), typeof(float)), _unityRuntime);
        _update = Reflect.Delegate<Action<float, float>>(Reflect.InstanceMethod(unityType, "Update", typeof(float), typeof(float)), _unityRuntime);
        var onUpdate = (Action?)api.AppOnUpdate.GetValue(app);
        api.AppOnUpdate.SetValue(app, (Action)Delegate.Combine(onUpdate, (Action)Tick));
        stage.Evidence["runtime"] = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription;
        Complete(stage);
    }

    private static void SetShaderWarmup(bool enabled)
    {
        Type warmup = Reflect.Type("Verse.ShaderWarmup, Assembly-CSharp");
        PropertyInfo? property = warmup.GetProperty("PrewarmEnabled", BindingFlags.Public | BindingFlags.Static);
        if (property != null)
        {
            property.SetValue(null, enabled);
            return;
        }
        Reflect.StaticField(warmup, "PrewarmEnabled").SetValue(null, enabled);
    }

    private void OnPrePoll(object app)
    {
        api.ClearFrameSubmissions();
        api.InputBeginFrame();
    }

    private void Tick()
    {
        if (Volatile.Read(ref _finished) != 0)
        {
            return;
        }
        try
        {
            _frames++;
            api.EndOfFrameRun();
            api.FrameStartRun();
            float dt = api.DeltaTime();
            float elapsed = api.Elapsed();
            _beginFrame!(dt, elapsed);
            _update!(dt, elapsed);
            if (!_queued)
            {
                _queued = true;
                GlobalInit();
            }
            object?[] args = [false];
            api.LongEventsUpdate.Invoke(null, args);
            if ((bool)args[0]!)
            {
                Finish("failed", "a scene change was requested; the worker never loads a playable scene");
                return;
            }
            // Only the map stage may create a Game, and it never starts play.
            if (_mapStage == null && api.CurrentGame.GetValue(null) != null)
            {
                Finish("failed", "game code created a Game instance; the worker never enters play");
                return;
            }
            api.AudioListenerSync();
            if (api.AudioBackendCurrent.GetValue(null) is object audio)
            {
                api.AudioBackendUpdate.Invoke(audio, null);
            }
            if (_markerRan && !api.AnyEventNowOrWaiting())
            {
                Finish("completed", null);
                return;
            }
            if (clock.Elapsed.TotalSeconds > request.DeadlineSeconds)
            {
                Finish("interrupted", $"worker deadline of {request.DeadlineSeconds.ToString(CultureInfo.InvariantCulture)} s reached");
                return;
            }
            // The loader runs on a long-event thread; don't spin a core while it works.
            Thread.Sleep(1);
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            diagnostics.Record("error", "Worker", "worker frame failed", e);
            Finish("failed", $"worker frame failed: {e.GetType().Name}: {e.Message}");
        }
    }

    // Root.Start + Root.CheckGlobalInit, minus Steam and the UI/sound roots.
    private void GlobalInit()
    {
        Stage stage = Begin("globalInit");
        api.EnsureEnglish();
        api.CopyUnityData();
        api.LogVersionNumber();
        api.PrefsInit();
        bool devMode = api.PrefsDevMode();
        bool reset = api.PrefsResetModsConfigOnCrash();
        string language = api.PrefsLangFolderName();
        stage.Evidence["devMode"] = devMode;
        stage.Evidence["resetModsConfigOnCrash"] = reset;
        stage.Evidence["language"] = language;
        Type handlerType = api.LogMessageReceivedThreaded.EventHandlerType!;
        api.LogMessageReceivedThreaded.AddEventHandler(null, Delegate.CreateDelegate(handlerType, api.VerseLogNotifyThreaded));
        if (devMode)
        {
            api.ReportProbablyMissingAttributes();
        }
        if (!devMode || reset || language != request.Language)
        {
            Complete(stage, "failed");
            Finish("failed", $"prefs not applied as requested (devMode={devMode}, resetModsConfigOnCrash={reset}, language={language})");
            return;
        }
        Complete(stage);

        Stage early = Begin("staticConstructorsEarly");
        Queue(() =>
        {
            Diagnostics.Stage = "staticConstructorsEarly";
            api.StaticConstructorsCallAll();
            Complete(early);
        }, async: false, handler: null);
        Queue(() =>
        {
            _loadStage = Begin("loadPlayData");
            try
            {
                api.LoadAllPlayData(false);
            }
            finally
            {
                Complete(_loadStage, api.PlayDataLoaded() ? "completed" : "failed");
                // Bios, late translation injection, static constructors, atlas baking
                // and GC run on the main thread right after this event finishes.
                _lateStage = Begin("lateLoadActions");
            }
        }, async: true, handler: e => _loadException = e);
        Queue(() =>
        {
            if (_lateStage != null)
            {
                _lateStage.Evidence["coreStaticAssetsLoaded"] = api.CoreStaticAssetsLoaded.GetValue(null);
                Complete(_lateStage, _loadStage?.Status == "completed" ? "completed" : "failed");
            }
            if (request.Map != null && mapApi != null && _lateStage?.Status == "completed")
            {
                QueueMap(request.Map, mapApi);
            }
            else
            {
                _markerRan = true;
            }
        }, async: false, handler: null);
    }

    // Like the official "GeneratingMap" long event, generation runs asynchronously;
    // the observation runs on the main thread after the game's when-finished actions.
    private void QueueMap(MapRequest mapRequest, MapApi bound)
    {
        _mapStage = Begin("mapGeneration");
        _map = new MapStage(mapRequest, bound);
        Queue(() =>
        {
            _map.InstallPlayRoot();
        }, async: false, handler: e => _mapException = e);
        Queue(() =>
        {
            if (_mapException != null)
            {
                return;
            }
            _map.Generate();
            Diagnostics.Stage = "map.whenFinished";
        }, async: true, handler: e => _mapException = e);
        Queue(() =>
        {
            Diagnostics.Stage = "map.observe";
            foreach ((string key, object? value) in _map.Evidence)
            {
                _mapStage.Evidence[key] = value;
            }
            if (_mapException == null && _map.Map != null)
            {
                try
                {
                    _mapSummary = new MapObservation(bound, _map, mapRequest.MaxListedThings).Write(mapRequest.ObservationPath);
                    _eventChoice.Observe(request.Expectations, bound, _map.Map);
                }
                catch (Exception e) when (e is not OutOfMemoryException)
                {
                    _mapException = e;
                }
            }
            Complete(_mapStage, _mapException == null && _mapSummary != null ? "completed" : "failed");
            if (request.Tick == null) _markerRan = true;
        }, async: false, handler: null);
        if (request.Tick is { } tickRequest)
        {
            _ticks = new BoundedTickRunner(tickRequest.Count, tickRequest.ObserveAt);
            Queue(() =>
            {
                if (_mapException != null || _map?.Game == null) { _tickError = "map unavailable"; return; }
                try
                {
                    _tickErrorsBefore = diagnostics.ErrorCount;
                    _tickApi = new TickApi(bound);
                    _tickApi.Initialize(_map.Game);
                    _tickInitialization = "gameFinalizeInitAndStartedNewGame";
                }
                catch (Exception error) when (error is not OutOfMemoryException)
                {
                    _tickError = error.ToString();
                    diagnostics.Record("error", "Worker", "bounded tick initialization failed", error);
                }
            }, async: false, handler: error => _tickError = error.ToString());
            // The next long event runs after game-start when-finished callbacks.
            Queue(() =>
            {
                Diagnostics.Stage = "tick.run";
                try
                {
                    if (_tickError == null && _tickApi != null && _map?.Game is object game)
                    {
                        if (diagnostics.ErrorCount != _tickErrorsBefore)
                            throw new InvalidOperationException("game initialization emitted an error");
                        Func<long> probe = _tickApi.Probe(game);
                        _ticks.Run(() => _tickApi.ReadTick(game), () =>
                        {
                            _tickApi.SingleTick(game);
                            // The game's component utility catches exceptions and logs them.
                            // They still invalidate completion even when the tick counter advanced.
                            if (diagnostics.ErrorCount != _tickErrorsBefore)
                                throw new InvalidOperationException("game tick emitted an error");
                        }, probe, () => clock.Elapsed.TotalSeconds >= request.DeadlineSeconds
                            || Volatile.Read(ref _finished) != 0, WriteTickCheckpoint);
                    }
                }
                catch (Exception error) when (error is not OutOfMemoryException)
                {
                    _tickError = error.ToString();
                }
                _markerRan = true;
            }, async: false, handler: error => { _tickError = error.ToString(); _markerRan = true; });
        }
    }

    private Dictionary<string, object?> TickCheckpointEvidence()
    {
        Dictionary<string, object?> evidence = _ticks!.Evidence(_tickInitialization);
        evidence["camera"] = _tickApi?.CameraContext;
        return evidence;
    }

    private void WriteTickCheckpoint()
    {
        string path = Path.Combine(Path.GetDirectoryName(request.ResultPath)!, "tick-evidence.json");
        string temp = path + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(new Dictionary<string, object?>
        {
            ["recordType"] = "rwmtTickCheckpoint", ["schemaVersion"] = 1,
            ["runId"] = request.RunId, ["nonce"] = request.Nonce,
            ["tick"] = TickCheckpointEvidence()
        }));
        File.Move(temp, path, overwrite: true);
    }

    private void Queue(Action action, bool async, Action<Exception>? handler)
    {
        api.QueueLongEvent.Invoke(null, [action, null, async, handler, false, true, null]);
    }

    private void Finish(string executionStatus, string? failure)
    {
        if (!TryFinish())
        {
            return;
        }
        Diagnostics.Stage = "checks";
        WriteResult(executionStatus, failure);
        Quit(executionStatus == "completed" ? 0 : 3);
    }

    private const double WatchdogGraceSeconds = 2;

    private bool TryFinish() => Interlocked.CompareExchange(ref _finished, 1, 0) == 0;

    // Runs on a timer thread while the main thread is still inside game code. Only
    // the stage list and diagnostics counters are read; no game state is touched.
    private void Watchdog()
    {
        if (!TryFinish())
        {
            return;
        }
        string stage = Diagnostics.Stage;
        diagnostics.Record("warning", "Worker", $"worker deadline passed while the main thread was busy in stage {stage}", null);
        WriteResult("interrupted", $"worker deadline of {request.DeadlineSeconds.ToString(CultureInfo.InvariantCulture)} s passed during stage {stage}", observeGame: false);
        diagnostics.Dispose();
        Environment.Exit(3);
    }

    private void Quit(int code)
    {
        ExitCode = code;
        if (_app != null)
        {
            api.AppQuit.Invoke(_app, [code]);
        }
    }

    public void WriteResult(string executionStatus, string? failure, bool observeGame = true)
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
            json.WriteNumber("frames", _frames);
            json.WriteNumber("elapsedSeconds", Math.Round(clock.Elapsed.TotalSeconds, 3));
            WriteRuntime(json);
            WriteStages(json);
            if (request.Tick != null)
            {
                json.WritePropertyName("tick");
                Dictionary<string, object?> evidence = _ticks?.Evidence(_tickInitialization) ?? new();
                evidence["camera"] = _tickApi?.CameraContext;
                if (_tickError != null) { evidence["status"] = "incomplete"; evidence["error"] = _tickError; }
                JsonSerializer.Serialize(json, evidence);
            }
            json.WriteStartArray("skippedOfficialSteps");
            foreach (string step in SkippedOfficialSteps)
            {
                json.WriteStringValue(step);
            }
            json.WriteEndArray();
            json.WriteStartArray("deviations");
            foreach (string deviation in Deviations)
            {
                json.WriteStringValue(deviation);
            }
            json.WriteEndArray();
            if (observeGame)
            {
                WriteGameObservations(json, executionStatus);
            }
            else
            {
                json.WriteBoolean("gameObserved", false);
            }
            json.WriteStartObject("diagnosticsSummary");
            json.WriteNumber("written", diagnostics.Written);
            json.WriteNumber("dropped", diagnostics.Dropped);
            json.WriteNumber("truncated", diagnostics.Truncated);
            json.WriteStartObject("byLevel");
            foreach ((string level, int count) in diagnostics.CountsByLevel)
            {
                json.WriteNumber(level, count);
            }
            json.WriteEndObject();
            json.WriteEndObject();
            json.WriteEndObject();
        }
        File.Move(temp, request.ResultPath, overwrite: true);
    }

    private void WriteGameObservations(Utf8JsonWriter json, string executionStatus)
    {
        if (_loadException != null)
        {
            json.WriteString("loadException", _loadException.ToString());
        }
        bool loaded = SafeBool(() => api.PlayDataLoaded());
        json.WriteBoolean("playDataLoaded", loaded);
        json.WriteBoolean("verseLogLimitReached", SafeBool(() => (bool)api.LogReachedMaxMessages.GetValue(null)!));
        Guard(json, "activeLanguageError", () =>
        {
            object? language = api.ActiveLanguage.GetValue(null);
            json.WriteString("activeLanguage", language == null ? null : (string?)Reflect.Member(language, "folderName"));
        });
        if (loaded)
        {
            Guard(json, "translationErrorsError", () =>
                Checks.WriteTranslationErrors(json, api.ActiveLanguage.GetValue(null), request.MaxDiagnostics, request.MaxMessageBytes));
        }
        if (executionStatus == "completed")
        {
            var checks = new Checks(api);
            Guard(json, "runningModsError", () => checks.WriteRunningMods(json));
            Guard(json, "modOrderError", () =>
            {
                List<string> actual = checks.RunningModIds();
                json.WriteStartObject("modOrder");
                json.WriteBoolean("matches", actual.SequenceEqual(request.ExpectedModOrder));
                json.WriteStartArray("expected");
                request.ExpectedModOrder.ToList().ForEach(json.WriteStringValue);
                json.WriteEndArray();
                json.WriteStartArray("actual");
                actual.ForEach(json.WriteStringValue);
                json.WriteEndArray();
                json.WriteEndObject();
            });
            if (loaded)
            {
                Guard(json, "checksError", () => checks.WriteExpectations(json, request.Expectations, _eventChoice.Row));
            }
        }
        if (request.Map != null)
        {
            WriteMap(json);
        }
    }

    private void WriteMap(Utf8JsonWriter json)
    {
        json.WriteStartObject("map");
        json.WriteString("status", _mapStage?.Status ?? "notStarted");
        Exception? error = _mapException is TargetInvocationException { InnerException: { } inner } ? inner : _mapException;
        if (error != null)
        {
            json.WriteString("setupError", error is MapSetupException ? error.Message : null);
            json.WriteString("exception", error is MapSetupException ? null : error.ToString());
        }
        if (_mapSummary != null)
        {
            json.WritePropertyName("summary");
            JsonSerializer.Serialize(json, _mapSummary);
        }
        json.WriteStartArray("skippedOfficialSteps");
        IEnumerable<string> skipped = request.Tick == null ? MapStage.SkippedOfficialSteps :
            new[] { MapStage.SkippedOfficialSteps[0],
                "D: a non-attached real CameraDriver supplies a fixed player-start view at default zoom for tick-rate predicates; no camera Update/input/render callbacks, CurrentMap UI/ambient notifications, pause-on-load extra tick, interactive scene or save" };
        foreach (string step in skipped)
        {
            json.WriteStringValue(step);
        }
        json.WriteEndArray();
        json.WriteEndObject();
    }

    // A failing observation must not lose the rest of the result.
    private static void Guard(Utf8JsonWriter json, string errorProperty, Action write)
    {
        int depth = json.CurrentDepth;
        try
        {
            write();
        }
        catch (Exception e) when (e is not OutOfMemoryException && json.CurrentDepth == depth)
        {
            json.WriteString(errorProperty, e.ToString());
        }
    }

    private static bool SafeBool(Func<bool> read)
    {
        try
        {
            return read();
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            return false;
        }
    }

    private void WriteStages(Utf8JsonWriter json)
    {
        json.WriteStartArray("stages");
        Stage[] stages;
        lock (_stages)
        {
            stages = _stages.ToArray();
        }
        foreach (Stage stage in stages)
        {
            json.WriteStartObject();
            json.WriteString("name", stage.Name);
            json.WriteString("status", stage.Status);
            json.WriteNumber("startSeconds", Math.Round(stage.Start, 3));
            if (stage.End is double end)
            {
                json.WriteNumber("seconds", Math.Round(end - stage.Start, 3));
            }
            json.WriteStartObject("evidence");
            foreach ((string key, object? value) in stage.Evidence)
            {
                json.WritePropertyName(key);
                JsonSerializer.Serialize(json, value is bool or int or float or double or System.Collections.IEnumerable and not string ? value : value?.ToString());
            }
            json.WriteEndObject();
            json.WriteEndObject();
        }
        json.WriteEndArray();
    }

    private void WriteRuntime(Utf8JsonWriter json)
    {
        json.WriteStartObject("runtime");
        json.WriteString("frameworkDescription", System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription);
        json.WriteString("osDescription", System.Runtime.InteropServices.RuntimeInformation.OSDescription);
        json.WriteString("runtimeIdentifier", System.Runtime.InteropServices.RuntimeInformation.RuntimeIdentifier);
        json.WriteString("processArchitecture", System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString());
        json.WriteString("jitPatchableAssemblies", AppContext.GetData("WaylithClr.JitPatchableAssemblies") as string);
        json.WriteString("assemblyNameRedirects", AppContext.GetData("WaylithClr.AssemblyNameRedirects") as string);
        json.WriteEndObject();
        json.WriteStartArray("assemblies");
        string hostDir = Path.GetFullPath(request.HostDir);
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies().OrderBy(a => a.GetName().Name, StringComparer.Ordinal))
        {
            string location = assembly.IsDynamic ? "" : assembly.Location;
            if (location.Length == 0 || !Path.GetFullPath(location).StartsWith(hostDir, StringComparison.Ordinal))
            {
                continue;
            }
            json.WriteStartObject();
            json.WriteString("name", assembly.GetName().Name);
            json.WriteString("version", assembly.GetName().Version?.ToString());
            json.WriteString("mvid", assembly.ManifestModule.ModuleVersionId.ToString());
            json.WriteString("path", Path.GetRelativePath(hostDir, location));
            json.WriteEndObject();
        }
        json.WriteEndArray();
    }
}

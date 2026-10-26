using System.Reflection;
using Microsoft.Extensions.Logging;
using RimWorldValidation.Gui.Model;
using UnityEngine;
using UnityEngine.SceneManagement;
using Verse;
using Waylith;
using Waylith.UnityCompat;

namespace RimWorldValidation.Gui;

/// <summary>
/// Starts the engine with a window, as the game's own bootstrap does
/// (RimWorldWaylith.Bootstrap.Initialize), but with the validation scene in
/// place of the game's Entry scene: no main menu, no Game, no Steam. Settings,
/// logs and caches go to the run directory, never to the user's game profile.
/// </summary>
internal static class Boot
{
    public const string SceneName = "Validation";
    private const string BootstrapTypeName = "RimWorldWaylith.Bootstrap, RimWorld";
    private const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;

    // Non-public members of the game's bootstrap the GUI calls; all are checked before the engine starts.
    private static readonly (string Name, Type Parameter)[] BootstrapMethods =
    [
        ("ConfigureTextureRuntime", typeof(EngineApplication)),
        ("ConfigureInput", typeof(EngineApplication)),
        ("ConfigureFrameRenderer", typeof(EngineApplication)),
        ("RegisterExecutionOrders", typeof(UnityWorld)),
        ("RegisterResources", typeof(EngineApplication)),
        ("SyncWindowSizeIfChanged", typeof(EngineApplication)),
    ];

    private static Type? _bootstrap;
    private static EngineApplication? _app;
    private static UnityRuntime? _unity;
    private static int? _stopCode;

    public static GuiRequest Request { get; private set; } = null!;

    public static IReadOnlyList<string> MissingMembers()
    {
        var missing = new List<string>();
        Type? boot;
        try
        {
            boot = Type.GetType(BootstrapTypeName, false);
        }
        catch (Exception e) when (e is FileNotFoundException or FileLoadException or BadImageFormatException)
        {
            return [$"a loadable RimWorld.dll ({e.GetType().Name})"];
        }
        if (boot == null)
        {
            return ["type RimWorldWaylith.Bootstrap in RimWorld.dll"];
        }
        foreach (var (name, parameter) in BootstrapMethods)
        {
            if (boot.GetMethod(name, Any, [parameter]) is not { IsStatic: true })
            {
                missing.Add($"Bootstrap.{name}({parameter.Name})");
            }
        }
        FieldInfo? runtime = boot.GetField("_unityRuntime", Any);
        if (runtime?.FieldType != typeof(UnityRuntime))
        {
            missing.Add("Bootstrap._unityRuntime");
        }
        FieldInfo? dispatch = boot.GetField("_imguiDispatch", Any);
        FieldInfo? host = boot.GetField("_imguiHost", Any);
        if (dispatch == null || host == null || dispatch.FieldType.GetMethod("DispatchInput", Any, [host.FieldType]) == null)
        {
            missing.Add("Bootstrap._imguiDispatch.DispatchInput(_imguiHost)");
        }
        if (typeof(Current).GetField("cameraInt", Any)?.FieldType != typeof(Camera))
        {
            missing.Add("Verse.Current.cameraInt");
        }
        if (typeof(Current).GetField("rootInt", Any)?.FieldType != typeof(Root))
        {
            missing.Add("Verse.Current.rootInt");
        }
        if (missing.Count == 0)
        {
            _bootstrap = boot;
        }
        return missing;
    }

    public static int Run(GuiRequest request)
    {
        Request = request;
        Brutal.Logging.LogSystem.IsEnabled = true;
        Brutal.Logging.LogSystem.Initialize(builder =>
        {
            builder.AddSimpleConsole();
            builder.SetMinimumLevel(LogLevel.Information);
        });
        Environment.SetEnvironmentVariable("MONOMOD_DMDType", "dynamicmethod");
        Waylith.Logging.FileLog.SetDirectory(Path.Combine(request.UserDataDir, "logs"));
        int code = EngineApplication.Run(new EngineApplicationOptions
        {
            Title = "RimWorld MOD 検証（テスト専用）",
            Headless = false,
            ShowCrashDialog = false,
            AudioBackend = new Waylith.Audio.MiniAudio.MiniAudioBackend(),
            // As the game's own Program: Windows uses the Vulkan loader shipped with the game.
            BundledVulkanLoaderPath = OperatingSystem.IsWindows() ? Path.Combine(request.HostDir, "vulkan", "vulkan-1.dll") : null,
        }, Initialize);
        return _stopCode ?? code;
    }

    /// <summary>Ends the GUI with the given exit code (see <see cref="Program"/>).</summary>
    public static void Stop(int code, string reason)
    {
        if (_stopCode != null)
        {
            return;
        }
        _stopCode = code;
        Console.Error.WriteLine($"stopping ({code}): {reason}");
        _app?.Quit(code);
    }

    private static object? Call(string name, object argument) => _bootstrap!.GetMethod(name, Any, [argument.GetType()])!.Invoke(null, [argument]);

    private static void Initialize(EngineApplication app)
    {
        _app = app;
        string host = Request.HostDir, userData = Request.UserDataDir;
        _unity = new UnityRuntime(app.Runtime);
        _bootstrap!.GetField("_unityRuntime", Any)!.SetValue(null, _unity);
        _unity.App.ProductName = "RimWorld by Ludeon Studios";
        _unity.App.Version = _bootstrap.Assembly.GetName().Version?.ToString() ?? "0.0.0";
        _unity.App.IsEditor = false;
        _unity.ConfigurePaths(Path.Combine(host, "RimWorld_Data"), userData, Path.Combine(userData, "tmp"),
            Path.Combine(userData, "logs"), userData);
        Waylith.Rendering.RuntimeShaderCompiler.ConfigureCacheDirectory(Path.Combine(userData, "ShaderCache"));
        string packPath = Path.Combine(host, "Assets.zip");
        var pack = Waylith.Assets.AssetPackBoot.Open(_unity.App.DataPath, app.Options.CommandLineAccessor, packPath);
        // Same rule as Bootstrap.ConfigureRuntime, minus the -NoAssetPack escape hatch.
        if ((pack == null || pack.ContentHashes.Count == 0) && !Directory.Exists(Path.Combine(_unity.App.DataPath, "Resources", "Textures")))
        {
            throw new InvalidOperationException($"asset pack {packPath} is missing or has no manifest");
        }
        Waylith.Jobs.WaylithJobRuntime.SetErrorHandler(message => Verse.Log.Error(message));
        Waylith.Graphics.GraphicsDevice.SetErrorHandler(message => Verse.Log.Error(message));
        Waylith.Graphics.GraphicsDevice.SetWarningHandler(message => Verse.Log.Warning(message));
        _unity.App.RegisterQuitHandler(_ => app.Quit(_stopCode ?? _unity.App.ExitCode));

        Waylith.Rendering.ShaderSourceLoader.RegisterShaderSourceDirectory(Path.Combine(host, "Rendering", "Shaders"));
        Call("ConfigureTextureRuntime", app);
        Call("ConfigureInput", app);
        Call("ConfigureFrameRenderer", app);
        Call("RegisterExecutionOrders", _unity.World);
        Call("RegisterResources", app);

        FieldInfo dispatchField = _bootstrap.GetField("_imguiDispatch", Any)!;
        FieldInfo hostField = _bootstrap.GetField("_imguiHost", Any)!;
        MethodInfo dispatchInput = dispatchField.FieldType.GetMethod("DispatchInput", Any, [hostField.FieldType])!;
        app.OnUpdate += () =>
        {
            Call("SyncWindowSizeIfChanged", app);
            UnityStubs.EndOfFrame.Run();
            UnityStubs.FrameStart.Run();
            _unity.BeginFrame(Waylith.Time.DeltaTime, Waylith.Time.Elapsed);
            object? dispatch = dispatchField.GetValue(null), imgui = hostField.GetValue(null);
            if (dispatch != null && imgui != null)
            {
                dispatchInput.Invoke(dispatch, [imgui]);
            }
            _unity.Update(Waylith.Time.DeltaTime, Waylith.Time.Elapsed);
            AudioListener.SyncToBackend();
            Waylith.Audio.AudioBackend.Current?.Update();
            if (Current.Game != null)
            {
                Stop(Program.PlayableBlocked, "a Game was created; the GUI is never playable");
            }
        };

        // The game's own scenes are never built: asking for them ends the GUI.
        SceneManager.RegisterScene("Entry", () => Stop(Program.PlayableBlocked, "the main menu scene was requested"));
        SceneManager.RegisterScene("Play", () => Stop(Program.PlayableBlocked, "the play scene was requested"));
        SceneManager.sceneUnloaded += scene =>
        {
            if (scene.name == SceneName)
            {
                Stop(Program.PlayableBlocked, "the validation scene was unloaded");
            }
        };
        SceneManager.RegisterScene(SceneName, () =>
        {
            Camera camera = new GameObject("Camera", typeof(Camera), typeof(AudioListener)).GetComponent<Camera>();
            camera.clearFlags = CameraClearFlags.Color;
            camera.backgroundColor = new UnityEngine.Color(0f, 0f, 0f, 0f);
            camera.allowHDR = false;
            new GameObject("GameRoot").AddComponent<ValidationRoot>();
        });
        SceneManager.SetInitialScene(SceneName);
    }
}

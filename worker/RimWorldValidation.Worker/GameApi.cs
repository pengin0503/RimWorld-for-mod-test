using System.Collections;
using System.Reflection;
using Microsoft.Extensions.Logging;

namespace RimWorldValidation.Worker;

/// <summary>
/// Every engine and game member the Worker touches, bound by reflection in one
/// place. Binding happens before the engine starts, so a game build that lacks
/// a member is reported as an adapter mismatch instead of failing mid-run.
/// Names are from RimWorld 1.7.4985 rev1269 (Assembly-CSharp 1.7.9790,
/// commit 535691cc); see docs/research/test-host-entrypoints.md.
/// </summary>
public sealed class GameApi
{
    private const string Waylith = "Waylith";
    private const string Stubs = "UnityStubs";
    private const string Game = "Assembly-CSharp";

    // Engine (Waylith.dll)
    public required Type EngineApplication { get; init; }
    public required Type EngineApplicationOptions { get; init; }
    public required MethodInfo EngineRun { get; init; }
    public required Type MiniAudioBackend { get; init; }
    public required PropertyInfo AppRuntime { get; init; }
    public required FieldInfo AppOnUpdate { get; init; }
    public required EventInfo AppPrePollEvents { get; init; }
    public required MethodInfo AppQuit { get; init; }
    public required Func<float> DeltaTime { get; init; }
    public required Func<float> Elapsed { get; init; }
    public required Action<string> FileLogSetDirectory { get; init; }
    public required MethodInfo AssetPackOpen { get; init; }
    public required Action<string> ShaderCacheDirectory { get; init; }
    public required Action<string> RegisterShaderSourceDirectory { get; init; }
    public required Action ClearFrameSubmissions { get; init; }
    public required Action<Action<string>> JobErrorHandler { get; init; }
    public required Action<Action<string>> GraphicsErrorHandler { get; init; }
    public required Action<Action<string>> GraphicsWarningHandler { get; init; }
    public required PropertyInfo AudioBackendCurrent { get; init; }
    public required MethodInfo AudioBackendUpdate { get; init; }
    public required FieldInfo LogSystemIsEnabled { get; init; }
    public required MethodInfo LogSystemInitialize { get; init; }

    // Unity compatibility layer (UnityStubs.dll)
    public required ConstructorInfo UnityRuntimeCtor { get; init; }
    public required Action EndOfFrameRun { get; init; }
    public required Action FrameStartRun { get; init; }
    public required Action InputBeginFrame { get; init; }
    public required Action AudioListenerSync { get; init; }
    public required EventInfo LogMessageReceivedThreaded { get; init; }

    // Game (Assembly-CSharp.dll)
    public required Type Def { get; init; }
    public required Action EnsureEnglish { get; init; }
    public required Action CopyUnityData { get; init; }
    public required Action LogVersionNumber { get; init; }
    public required Action PrefsInit { get; init; }
    public required Func<bool> PrefsDevMode { get; init; }
    public required Func<bool> PrefsResetModsConfigOnCrash { get; init; }
    public required Func<string> PrefsLangFolderName { get; init; }
    public required MethodInfo VerseLogNotifyThreaded { get; init; }
    public required Action StaticConstructorsCallAll { get; init; }
    public required Action ReportProbablyMissingAttributes { get; init; }
    public required FieldInfo CoreStaticAssetsLoaded { get; init; }
    public required MethodInfo QueueLongEvent { get; init; }
    public required MethodInfo LongEventsUpdate { get; init; }
    public required Func<bool> AnyEventNowOrWaiting { get; init; }
    public required Action<bool> LoadAllPlayData { get; init; }
    public required Func<bool> PlayDataLoaded { get; init; }
    public required PropertyInfo RunningMods { get; init; }
    public required PropertyInfo ModHandles { get; init; }
    public required FieldInfo LogReachedMaxMessages { get; init; }
    public required FieldInfo ActiveLanguage { get; init; }
    public required PropertyInfo CurrentGame { get; init; }
    public required MethodInfo AllSubclasses { get; init; }

    public static GameApi Bind()
    {
        Type engine = Reflect.Type($"Waylith.EngineApplication, {Waylith}");
        Type options = Reflect.Type($"Waylith.EngineApplicationOptions, {Waylith}");
        Type time = Reflect.Type($"Waylith.Time, {Waylith}");
        Type fileLog = Reflect.Type($"Waylith.Logging.FileLog, {Waylith}");
        Type commandLine = Reflect.Type($"Waylith.CLI.ICommandLine, {Waylith}");
        Type assetPackBoot = Reflect.Type($"Waylith.Assets.AssetPackBoot, {Waylith}");
        Type shaderCompiler = Reflect.Type($"Waylith.Rendering.RuntimeShaderCompiler, {Waylith}");
        Type shaderSources = Reflect.Type($"Waylith.Rendering.ShaderSourceLoader, {Waylith}");
        Type meshSubmission = Reflect.Type($"Waylith.Rendering.MeshDrawSubmission, {Waylith}");
        Type jobRuntime = Reflect.Type($"Waylith.Jobs.WaylithJobRuntime, {Waylith}");
        Type graphicsDevice = Reflect.Type($"Waylith.Graphics.GraphicsDevice, {Waylith}");
        Type audioBackend = Reflect.Type($"Waylith.Audio.AudioBackend, {Waylith}");
        Type logSystem = Reflect.Type("Brutal.Logging.LogSystem, Brutal.Core.Logging");
        Type waylithRuntime = Reflect.InstanceProperty(engine, "Runtime").PropertyType;

        Type unityRuntime = Reflect.Type($"Waylith.UnityCompat.UnityRuntime, {Stubs}");
        Type endOfFrame = Reflect.Type($"UnityStubs.EndOfFrame, {Stubs}");
        Type frameStart = Reflect.Type($"UnityStubs.FrameStart, {Stubs}");
        Type inputSystem = Reflect.Type($"UnityEngine.InputSystem.InputSystem, {Stubs}");
        Type audioListener = Reflect.Type($"UnityEngine.AudioListener, {Stubs}");
        Type application = Reflect.Type($"UnityEngine.Application, {Stubs}");

        Type def = Reflect.Type($"Verse.Def, {Game}");
        Type prefs = Reflect.Type($"Verse.Prefs, {Game}");
        Type staticCtors = Reflect.Type($"Verse.StaticConstructorOnStartupUtility, {Game}");
        Type longEvents = Reflect.Type($"Verse.LongEventHandler, {Game}");
        Type playData = Reflect.Type($"Verse.PlayDataLoader, {Game}");
        Type modManager = Reflect.Type($"Verse.LoadedModManager, {Game}");
        Type verseLog = Reflect.Type($"Verse.Log, {Game}");
        Type languages = Reflect.Type($"Verse.LanguageDatabase, {Game}");
        Type current = Reflect.Type($"Verse.Current, {Game}");
        Type genTypes = Reflect.Type($"Verse.GenTypes, {Game}");

        return new GameApi
        {
            EngineApplication = engine,
            EngineApplicationOptions = options,
            EngineRun = Reflect.StaticMethod(engine, "Run", options, typeof(Action<>).MakeGenericType(engine)),
            MiniAudioBackend = Reflect.Type($"Waylith.Audio.MiniAudio.MiniAudioBackend, {Waylith}"),
            AppRuntime = Reflect.InstanceProperty(engine, "Runtime"),
            AppOnUpdate = Reflect.InstanceField(engine, "OnUpdate"),
            AppPrePollEvents = Reflect.InstanceEvent(engine, "PrePollEvents"),
            AppQuit = Reflect.InstanceMethod(engine, "Quit", typeof(int)),
            DeltaTime = Reflect.Delegate<Func<float>>(Reflect.StaticProperty(time, "DeltaTime").GetMethod!),
            Elapsed = Reflect.Delegate<Func<float>>(Reflect.StaticProperty(time, "Elapsed").GetMethod!),
            FileLogSetDirectory = Reflect.Delegate<Action<string>>(Reflect.StaticMethod(fileLog, "SetDirectory", typeof(string))),
            AssetPackOpen = Reflect.StaticMethod(assetPackBoot, "Open", typeof(string), commandLine, typeof(string)),
            ShaderCacheDirectory = Reflect.Delegate<Action<string>>(Reflect.StaticMethod(shaderCompiler, "ConfigureCacheDirectory", typeof(string))),
            RegisterShaderSourceDirectory = Reflect.Delegate<Action<string>>(Reflect.StaticMethod(shaderSources, "RegisterShaderSourceDirectory", typeof(string))),
            ClearFrameSubmissions = Reflect.Delegate<Action>(Reflect.StaticMethod(meshSubmission, "ClearFrameSubmissions")),
            JobErrorHandler = Reflect.Delegate<Action<Action<string>>>(Reflect.StaticMethod(jobRuntime, "SetErrorHandler", typeof(Action<string>))),
            GraphicsErrorHandler = Reflect.Delegate<Action<Action<string>>>(Reflect.StaticMethod(graphicsDevice, "SetErrorHandler", typeof(Action<string>))),
            GraphicsWarningHandler = Reflect.Delegate<Action<Action<string>>>(Reflect.StaticMethod(graphicsDevice, "SetWarningHandler", typeof(Action<string>))),
            AudioBackendCurrent = Reflect.StaticProperty(audioBackend, "Current"),
            AudioBackendUpdate = Reflect.InstanceMethod(audioBackend, "Update"),
            LogSystemIsEnabled = Reflect.StaticField(logSystem, "IsEnabled"),
            LogSystemInitialize = Reflect.StaticMethod(logSystem, "Initialize", typeof(Action<ILoggingBuilder>)),

            UnityRuntimeCtor = unityRuntime.GetConstructor([waylithRuntime])
                ?? throw new AdapterMismatchException("Waylith.UnityCompat.UnityRuntime(WaylithRuntime)"),
            EndOfFrameRun = Reflect.Delegate<Action>(Reflect.StaticMethod(endOfFrame, "Run")),
            FrameStartRun = Reflect.Delegate<Action>(Reflect.StaticMethod(frameStart, "Run")),
            InputBeginFrame = Reflect.Delegate<Action>(Reflect.StaticMethod(inputSystem, "BeginFrame")),
            AudioListenerSync = Reflect.Delegate<Action>(Reflect.StaticMethod(audioListener, "SyncToBackend")),
            LogMessageReceivedThreaded = Reflect.StaticEvent(application, "logMessageReceivedThreaded"),

            Def = def,
            EnsureEnglish = Reflect.Delegate<Action>(Reflect.StaticMethod(Reflect.Type($"Verse.CultureInfoUtility, {Game}"), "EnsureEnglish")),
            CopyUnityData = Reflect.Delegate<Action>(Reflect.StaticMethod(Reflect.Type($"Verse.UnityDataInitializer, {Game}"), "CopyUnityData")),
            LogVersionNumber = Reflect.Delegate<Action>(Reflect.StaticMethod(Reflect.Type($"RimWorld.VersionControl, {Game}"), "LogVersionNumber")),
            PrefsInit = Reflect.Delegate<Action>(Reflect.StaticMethod(prefs, "Init")),
            PrefsDevMode = Reflect.Delegate<Func<bool>>(Reflect.StaticProperty(prefs, "DevMode").GetMethod!),
            PrefsResetModsConfigOnCrash = Reflect.Delegate<Func<bool>>(Reflect.StaticProperty(prefs, "ResetModsConfigOnCrash").GetMethod!),
            PrefsLangFolderName = Reflect.Delegate<Func<string>>(Reflect.StaticProperty(prefs, "LangFolderName").GetMethod!),
            VerseLogNotifyThreaded = Reflect.StaticMethod(verseLog, "Notify_MessageReceivedThreadedInternal",
                typeof(string), typeof(string), Reflect.Type($"UnityEngine.LogType, {Stubs}")),
            StaticConstructorsCallAll = Reflect.Delegate<Action>(Reflect.StaticMethod(staticCtors, "CallAll")),
            ReportProbablyMissingAttributes = Reflect.Delegate<Action>(Reflect.StaticMethod(staticCtors, "ReportProbablyMissingAttributes")),
            CoreStaticAssetsLoaded = Reflect.StaticField(staticCtors, "coreStaticAssetsLoaded"),
            QueueLongEvent = Reflect.StaticMethod(longEvents, "QueueLongEvent",
                typeof(Action), typeof(string), typeof(bool), typeof(Action<Exception>), typeof(bool), typeof(bool), typeof(Action)),
            LongEventsUpdate = Reflect.StaticMethod(longEvents, "LongEventsUpdate", typeof(bool).MakeByRefType()),
            AnyEventNowOrWaiting = Reflect.Delegate<Func<bool>>(Reflect.StaticProperty(longEvents, "AnyEventNowOrWaiting").GetMethod!),
            LoadAllPlayData = Reflect.Delegate<Action<bool>>(Reflect.StaticMethod(playData, "LoadAllPlayData", typeof(bool))),
            PlayDataLoaded = Reflect.Delegate<Func<bool>>(Reflect.StaticProperty(playData, "Loaded").GetMethod!),
            RunningMods = Reflect.StaticProperty(modManager, "RunningMods"),
            ModHandles = Reflect.StaticProperty(modManager, "ModHandles"),
            LogReachedMaxMessages = Reflect.StaticField(verseLog, "reachedMaxMessagesLimit"),
            ActiveLanguage = Reflect.StaticField(languages, "activeLanguage"),
            CurrentGame = Reflect.StaticProperty(current, "Game"),
            AllSubclasses = Reflect.StaticMethod(genTypes, "AllSubclasses", typeof(Type)),
        };
    }

    public IEnumerable<Type> DefTypes()
    {
        return ((IEnumerable)AllSubclasses.Invoke(null, [Def])!).Cast<Type>().Prepend(Def);
    }
}

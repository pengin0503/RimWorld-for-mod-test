using System.Collections;
using System.Reflection;

namespace RimWorldValidation.Worker;

/// <summary>Build-specific real game initialization. UI/camera transitions remain excluded.</summary>
public sealed class TickApi
{
    private readonly MapApi _map;
    private readonly MethodInfo _finalize, _thoughts, _scenarioStart, _historyFinalize, _research, _started, _single;
    private readonly FieldInfo _optimism, _currentMapIndex, _history, _components;
    private readonly PropertyInfo _ticks;

    public TickApi(MapApi map)
    {
        _map = map;
        Type game = map.GameType;
        _finalize = Reflect.InstanceMethod(game, "FinalizeInit");
        _thoughts = Reflect.StaticMethod(Reflect.Type("RimWorld.PawnUtility, Assembly-CSharp"), "GiveAllStartingPlayerPawnsThought",
            Reflect.Type("RimWorld.ThoughtDef, Assembly-CSharp"));
        _optimism = Reflect.StaticField(Reflect.Type("RimWorld.ThoughtDefOf, Assembly-CSharp"), "NewColonyOptimism");
        _currentMapIndex = Reflect.InstanceField(game, "currentMapIndex");
        _scenarioStart = Reflect.InstanceMethod(Reflect.Type("RimWorld.Scenario, Assembly-CSharp"), "PostGameStart");
        _history = Reflect.InstanceField(game, "history");
        _historyFinalize = Reflect.InstanceMethod(_history.FieldType, "FinalizeInit");
        _research = Reflect.StaticMethod(Reflect.Type("ResearchUtility, Assembly-CSharp"), "ApplyPlayerStartingResearch");
        Type components = Reflect.Type("Verse.GameComponentUtility, Assembly-CSharp");
        _started = Reflect.StaticMethod(components, "StartedNewGame");
        _components = Reflect.InstanceField(game, "components");
        Type manager = map.TickManager.FieldType;
        _single = Reflect.InstanceMethod(manager, "DoSingleTick");
        _ticks = Reflect.InstanceProperty(manager, "TicksGame");
    }

    public void Initialize(object game)
    {
        Diagnostics.Stage = "tick.initialize";
        _thoughts.Invoke(null, [_optimism.GetValue(null)]);
        _finalize.Invoke(game, null);
        // One generated map: select it without the CurrentMap setter's MapUI and
        // ambient-sound notifications. No camera or interactive scene is created.
        _currentMapIndex.SetValue(game, (sbyte)0);
        _scenarioStart.Invoke(_map.Scenario.GetValue(game), null);
        _historyFinalize.Invoke(_history.GetValue(game), null);
        _research.Invoke(null, null);
        _started.Invoke(null, null);
        _map.InitData.SetValue(game, null);
    }

    public int ReadTick(object game) => (int)_ticks.GetValue(_map.TickManager.GetValue(game))!;
    public void SingleTick(object game) => _single.Invoke(_map.TickManager.GetValue(game), null);

    public Func<long> Probe(object game)
    {
        object[] matches = ((IEnumerable)_components.GetValue(game)!).Cast<object>()
            .Where(c => c.GetType().FullName == "RWMT.TickProbe.TickProbeComponent"
                && c.GetType().Assembly.GetName().Name == "RWMT.TickProbe").ToArray();
        if (matches.Length != 1) throw new InvalidOperationException("registered tick probe is absent or ambiguous");
        object probe = matches[0];
        FieldInfo counter = Reflect.InstanceField(probe.GetType(), "Counter");
        FieldInfo started = Reflect.InstanceField(probe.GetType(), "Started");
        if (counter.FieldType != typeof(long) || started.FieldType != typeof(bool) || !(bool)started.GetValue(probe)!)
            throw new InvalidOperationException("tick probe did not receive StartedNewGame");
        return () => (long)counter.GetValue(probe)!;
    }
}

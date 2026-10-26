using System.Collections;
using System.Linq.Expressions;
using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>The optional "map" part of the worker request: one temporary world and map after the load.</summary>
public sealed class MapRequest
{
    public required string Seed { get; init; }
    public required int Size { get; init; }
    public required float PlanetCoverage { get; init; }
    public required string Scenario { get; init; }
    public required string Storyteller { get; init; }
    public required string Difficulty { get; init; }
    public string? Biome { get; init; }
    public int? Tile { get; init; }
    public string? MapGenerator { get; init; }
    public required IReadOnlyList<string> ExtraGenSteps { get; init; }
    public required int MaxListedThings { get; init; }
    public required string ObservationPath { get; init; }

    public static MapRequest? Load(JsonElement root)
    {
        if (!root.TryGetProperty("map", out JsonElement map) || map.ValueKind == JsonValueKind.Null)
        {
            return null;
        }
        return new MapRequest
        {
            Seed = map.GetProperty("seed").GetString()!,
            Size = map.GetProperty("size").GetInt32(),
            PlanetCoverage = map.GetProperty("planetCoverage").GetSingle(),
            Scenario = map.GetProperty("scenario").GetString()!,
            Storyteller = map.GetProperty("storyteller").GetString()!,
            Difficulty = map.GetProperty("difficulty").GetString()!,
            Biome = map.TryGetProperty("biome", out JsonElement biome) ? biome.GetString() : null,
            Tile = map.TryGetProperty("tile", out JsonElement tile) && tile.ValueKind == JsonValueKind.Number ? tile.GetInt32() : null,
            MapGenerator = map.TryGetProperty("mapGenerator", out JsonElement generator) ? generator.GetString() : null,
            ExtraGenSteps = map.GetProperty("extraGenSteps").EnumerateArray().Select(e => e.GetString()!).ToArray(),
            MaxListedThings = map.GetProperty("maxListedThings").GetInt32(),
            ObservationPath = map.GetProperty("observationPath").GetString()!,
        };
    }
}

/// <summary>Thrown when the requested map cannot be set up (unknown def, no tile with the biome, ...).</summary>
public sealed class MapSetupException(string message) : Exception(message);

/// <summary>
/// Game members the map stage touches, bound by reflection before the engine
/// starts (like <see cref="GameApi"/>), so a build without them is an adapter
/// mismatch instead of a failure halfway through a generated map.
/// </summary>
public sealed class MapApi
{
    private const string Game = "Assembly-CSharp";
    private const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

    public required Type GameType { get; init; }
    public required Type GameInitData { get; init; }
    public required Type PlanetTile { get; init; }
    public required Type GenStepWithParams { get; init; }
    public required Type GenStepParams { get; init; }
    public required PropertyInfo ProgramState { get; init; }
    public required Type RootPlay { get; init; }
    public required FieldInfo CurrentRoot { get; init; }
    public required FieldInfo CurrentCamera { get; init; }
    public required ConstructorInfo GameObjectCtor { get; init; }
    public required MethodInfo GetComponent { get; init; }
    public required Type[] CameraComponents { get; init; }
    public required FieldInfo CurrentRootPlay { get; init; }
    public required FieldInfo RootSoundRoot { get; init; }
    public required FieldInfo RootUiRoot { get; init; }
    public required Type UIRootPlay { get; init; }
    public required ConstructorInfo SoundRootCtor { get; init; }
    public required FieldInfo RootPlayMusicManager { get; init; }
    public required ConstructorInfo MusicManagerPlayCtor { get; init; }
    public required object ProgramStateEntry { get; init; }
    public required object ProgramStateMapInitializing { get; init; }
    public required PropertyInfo CurrentGame { get; init; }
    public required MethodInfo ClearCaches { get; init; }
    public required PropertyInfo InitData { get; init; }
    public required PropertyInfo Scenario { get; init; }
    public required FieldInfo Storyteller { get; init; }
    public required ConstructorInfo StorytellerCtor { get; init; }
    public required PropertyInfo World { get; init; }
    public required FieldInfo GameInfo { get; init; }
    public required FieldInfo TickManager { get; init; }
    public required FieldInfo ScenarioOfDef { get; init; }
    public required MethodInfo ScenarioPreConfigure { get; init; }
    public required MethodInfo ScenarioPostIdeoChosen { get; init; }
    public required MethodInfo ScenarioPreMapGenerate { get; init; }
    public required MethodInfo GenerateWorld { get; init; }
    public required object[] WorldDefaults { get; init; }
    public required FieldInfo InitStartingTile { get; init; }
    public required FieldInfo InitMapSize { get; init; }
    public required FieldInfo InitMapGeneratorDef { get; init; }
    public required FieldInfo InitPawns { get; init; }
    public required MethodInfo InitChooseRandomStartingTile { get; init; }
    public required MethodInfo InitPrepForMapGen { get; init; }
    public required MethodInfo RandomSettlementTileFor { get; init; }
    public required MethodInfo IsValidTileForNewSettlement { get; init; }
    public required FieldInfo WorldGrid { get; init; }
    public required FieldInfo WorldObjects { get; init; }
    public required FieldInfo WorldInfo { get; init; }
    public required FieldInfo InitialMapSize { get; init; }
    public required PropertyInfo GridSurface { get; init; }
    public required PropertyInfo GridTileAt { get; init; }
    public required PropertyInfo LayerTilesCount { get; init; }
    public required MethodInfo LayerPlanetTile { get; init; }
    public required FieldInfo PlanetTileId { get; init; }
    public required PropertyInfo PlanetTileValid { get; init; }
    public required PropertyInfo TilePrimaryBiome { get; init; }
    public required FieldInfo TileHilliness { get; init; }
    public required PropertyInfo TileMutators { get; init; }
    public required FieldInfo InfoStartingTile { get; init; }
    public required FieldInfo InfoPawns { get; init; }
    public required FieldInfo GameStartAbsTick { get; init; }
    public required PropertyInfo ConfiguredTicksAbsAtGameStart { get; init; }
    public required PropertyInfo Settlements { get; init; }
    public required PropertyInfo FactionOfPlayer { get; init; }
    public required PropertyInfo WorldObjectFaction { get; init; }
    public required PropertyInfo ParentMapGeneratorDef { get; init; }
    public required PropertyInfo ParentExtraGenStepDefs { get; init; }
    public required ConstructorInfo IntVec3Ctor { get; init; }
    public required MethodInfo GenerateMap { get; init; }
    public required FieldInfo TmpGenSteps { get; init; }
    public required MethodInfo RandPushState { get; init; }
    public required MethodInfo RandPopState { get; init; }
    public required Func<Type, string, object?> DefNamed { get; init; }
    public required Type ScenarioDef { get; init; }
    public required Type StorytellerDef { get; init; }
    public required Type DifficultyDef { get; init; }
    public required Type BiomeDef { get; init; }
    public required Type MapGeneratorDef { get; init; }
    public required Type GenStepDef { get; init; }

    // Observation (read only)
    public required PropertyInfo MapSize { get; init; }
    public required PropertyInfo MapTile { get; init; }
    public required PropertyInfo MapBiome { get; init; }
    public required PropertyInfo MapTileInfo { get; init; }
    public required FieldInfo MapGeneratorOfMap { get; init; }
    public required FieldInfo MapTerrainGrid { get; init; }
    public required FieldInfo MapRoofGrid { get; init; }
    public required FieldInfo MapListerThings { get; init; }
    public required MethodInfo TerrainAt { get; init; }
    public required MethodInfo RoofAt { get; init; }
    public required PropertyInfo AllThings { get; init; }
    public required MethodInfo OccupiedRect { get; init; }

    public static MapApi Bind()
    {
        Type current = Reflect.Type($"Verse.Current, {Game}");
        Type game = Reflect.Type($"Verse.Game, {Game}");
        Type initData = Reflect.Type($"Verse.GameInitData, {Game}");
        Type programState = Reflect.Type($"Verse.ProgramState, {Game}");
        Type root = Reflect.Type($"Verse.Root, {Game}");
        Type gameObject = Reflect.Type("UnityEngine.GameObject, UnityStubs");
        Type camera = Reflect.Type("UnityEngine.Camera, UnityStubs");
        Type rootPlay = Reflect.Type($"Verse.Root_Play, {Game}");
        Type soundRoot = Reflect.Type($"Verse.Sound.SoundRoot, {Game}");
        Type musicManagerPlay = Reflect.Type($"RimWorld.MusicManagerPlay, {Game}");
        Type scenarioDef = Reflect.Type($"RimWorld.ScenarioDef, {Game}");
        Type scenario = Reflect.Type($"RimWorld.Scenario, {Game}");
        Type storyteller = Reflect.Type($"RimWorld.Storyteller, {Game}");
        Type storytellerDef = Reflect.Type($"RimWorld.StorytellerDef, {Game}");
        Type difficultyDef = Reflect.Type($"RimWorld.DifficultyDef, {Game}");
        Type worldGenerator = Reflect.Type($"RimWorld.Planet.WorldGenerator, {Game}");
        Type world = Reflect.Type($"RimWorld.Planet.World, {Game}");
        Type worldInfo = Reflect.Type($"RimWorld.Planet.WorldInfo, {Game}");
        Type worldGrid = Reflect.Type($"RimWorld.Planet.WorldGrid, {Game}");
        Type planetLayer = Reflect.Type($"RimWorld.Planet.PlanetLayer, {Game}");
        Type planetTile = Reflect.Type($"RimWorld.Planet.PlanetTile, {Game}");
        Type tile = Reflect.Type($"RimWorld.Planet.Tile, {Game}");
        Type tileFinder = Reflect.Type($"RimWorld.Planet.TileFinder, {Game}");
        Type worldObjects = Reflect.Type($"RimWorld.Planet.WorldObjectsHolder, {Game}");
        Type worldObject = Reflect.Type($"RimWorld.Planet.WorldObject, {Game}");
        Type mapParent = Reflect.Type($"RimWorld.Planet.MapParent, {Game}");
        Type faction = Reflect.Type($"RimWorld.Faction, {Game}");
        Type gameInfo = Reflect.Type($"Verse.GameInfo, {Game}");
        Type tickManager = Reflect.Type($"Verse.TickManager, {Game}");
        Type genTicks = Reflect.Type($"Verse.GenTicks, {Game}");
        Type intVec3 = Reflect.Type($"Verse.IntVec3, {Game}");
        Type map = Reflect.Type($"Verse.Map, {Game}");
        Type mapGenerator = Reflect.Type($"Verse.MapGenerator, {Game}");
        Type mapGeneratorDef = Reflect.Type($"Verse.MapGeneratorDef, {Game}");
        Type genStepDef = Reflect.Type($"Verse.GenStepDef, {Game}");
        Type genStepWithParams = Reflect.Type($"Verse.GenStepWithParams, {Game}");
        Type genStepParams = Reflect.Type($"Verse.GenStepParams, {Game}");
        Type terrainGrid = Reflect.Type($"Verse.TerrainGrid, {Game}");
        Type roofGrid = Reflect.Type($"Verse.RoofGrid, {Game}");
        Type listerThings = Reflect.Type($"Verse.ListerThings, {Game}");
        Type rand = Reflect.Type($"Verse.Rand, {Game}");
        Type biomeDef = Reflect.Type($"RimWorld.BiomeDef, {Game}");
        Type defDatabase = Reflect.Type($"Verse.DefDatabase`1, {Game}");
        Type genStepsList = typeof(IEnumerable<>).MakeGenericType(genStepWithParams);
        Type predicate = typeof(Predicate<>).MakeGenericType(planetTile);

        Type rainfall = Reflect.Type($"RimWorld.Planet.OverallRainfall, {Game}");
        Type temperature = Reflect.Type($"RimWorld.Planet.OverallTemperature, {Game}");
        Type population = Reflect.Type($"RimWorld.Planet.OverallPopulation, {Game}");
        Type landmarks = Reflect.Type($"RimWorld.Planet.LandmarkDensity, {Game}");
        Type factionDefs = typeof(List<>).MakeGenericType(Reflect.Type($"RimWorld.FactionDef, {Game}"));

        return new MapApi
        {
            GameType = game,
            GameInitData = initData,
            PlanetTile = planetTile,
            GenStepWithParams = genStepWithParams,
            GenStepParams = genStepParams,
            ProgramState = Reflect.StaticProperty(current, "ProgramState"),
            RootPlay = rootPlay,
            CurrentRoot = Reflect.StaticField(current, "rootInt"),
            CurrentCamera = Reflect.StaticField(current, "cameraInt"),
            GameObjectCtor = gameObject.GetConstructor([typeof(string), typeof(Type[])])
                ?? throw new AdapterMismatchException("UnityEngine.GameObject(string, Type[])"),
            GetComponent = Reflect.InstanceMethod(gameObject, "GetComponent", typeof(Type)),
            CameraComponents = [camera, Reflect.Type("UnityEngine.AudioListener, UnityStubs")],
            CurrentRootPlay = Reflect.StaticField(current, "rootPlayInt"),
            RootSoundRoot = Reflect.InstanceField(root, "soundRoot"),
            RootUiRoot = Reflect.InstanceField(root, "uiRoot"),
            UIRootPlay = Reflect.Type($"RimWorld.UIRoot_Play, {Game}"),
            SoundRootCtor = soundRoot.GetConstructor(Type.EmptyTypes) ?? throw new AdapterMismatchException("Verse.Sound.SoundRoot()"),
            RootPlayMusicManager = Reflect.InstanceField(rootPlay, "musicManagerPlay"),
            MusicManagerPlayCtor = musicManagerPlay.GetConstructor(Type.EmptyTypes) ?? throw new AdapterMismatchException("RimWorld.MusicManagerPlay()"),
            ProgramStateEntry = EnumValue(programState, "Entry"),
            ProgramStateMapInitializing = EnumValue(programState, "MapInitializing"),
            CurrentGame = Reflect.StaticProperty(current, "Game"),
            ClearCaches = Reflect.StaticMethod(game, "ClearCaches"),
            InitData = Reflect.InstanceProperty(game, "InitData"),
            Scenario = Reflect.InstanceProperty(game, "Scenario"),
            Storyteller = Reflect.InstanceField(game, "storyteller"),
            StorytellerCtor = storyteller.GetConstructor([storytellerDef, difficultyDef])
                ?? throw new AdapterMismatchException("RimWorld.Storyteller(StorytellerDef, DifficultyDef)"),
            World = Reflect.InstanceProperty(game, "World"),
            GameInfo = Reflect.InstanceField(game, "info"),
            TickManager = Reflect.InstanceField(game, "tickManager"),
            ScenarioOfDef = Reflect.InstanceField(scenarioDef, "scenario"),
            ScenarioPreConfigure = Reflect.InstanceMethod(scenario, "PreConfigure"),
            ScenarioPostIdeoChosen = Reflect.InstanceMethod(scenario, "PostIdeoChosen"),
            ScenarioPreMapGenerate = Reflect.InstanceMethod(scenario, "PreMapGenerate"),
            GenerateWorld = Reflect.StaticMethod(worldGenerator, "GenerateWorld",
                typeof(float), typeof(string), rainfall, temperature, population, landmarks, factionDefs, typeof(float)),
            WorldDefaults = [EnumValue(rainfall, "Normal"), EnumValue(temperature, "Normal"), EnumValue(population, "Normal"), EnumValue(landmarks, "Normal")],
            InitStartingTile = Reflect.InstanceField(initData, "startingTile"),
            InitMapSize = Reflect.InstanceField(initData, "mapSize"),
            InitMapGeneratorDef = Reflect.InstanceField(initData, "mapGeneratorDef"),
            InitPawns = Reflect.InstanceField(initData, "startingAndOptionalPawns"),
            InitChooseRandomStartingTile = Reflect.InstanceMethod(initData, "ChooseRandomStartingTile"),
            InitPrepForMapGen = Reflect.InstanceMethod(initData, "PrepForMapGen"),
            RandomSettlementTileFor = Reflect.StaticMethod(tileFinder, "RandomSettlementTileFor", planetLayer, faction, typeof(bool), predicate),
            IsValidTileForNewSettlement = Reflect.StaticMethod(tileFinder, "IsValidTileForNewSettlement", planetTile, typeof(System.Text.StringBuilder), typeof(bool)),
            WorldGrid = Reflect.InstanceField(world, "grid"),
            WorldObjects = Reflect.InstanceField(world, "worldObjects"),
            WorldInfo = Reflect.InstanceField(world, "info"),
            InitialMapSize = Reflect.InstanceField(worldInfo, "initialMapSize"),
            GridSurface = Reflect.InstanceProperty(worldGrid, "Surface"),
            GridTileAt = worldGrid.GetProperties(Any).SingleOrDefault(p => p.GetIndexParameters() is [{ } only] && only.ParameterType == planetTile)
                ?? throw new AdapterMismatchException("RimWorld.Planet.WorldGrid[PlanetTile]"),
            LayerTilesCount = Reflect.InstanceProperty(planetLayer, "TilesCount"),
            LayerPlanetTile = Reflect.InstanceMethod(planetLayer, "PlanetTileForID", typeof(int)),
            PlanetTileId = Reflect.InstanceField(planetTile, "tileId"),
            PlanetTileValid = Reflect.InstanceProperty(planetTile, "Valid"),
            TilePrimaryBiome = Reflect.InstanceProperty(tile, "PrimaryBiome"),
            TileHilliness = Reflect.InstanceField(tile, "hilliness"),
            TileMutators = Reflect.InstanceProperty(tile, "Mutators"),
            InfoStartingTile = Reflect.InstanceField(gameInfo, "startingTile"),
            InfoPawns = Reflect.InstanceField(gameInfo, "startingAndOptionalPawns"),
            GameStartAbsTick = Reflect.InstanceField(tickManager, "gameStartAbsTick"),
            ConfiguredTicksAbsAtGameStart = Reflect.StaticProperty(genTicks, "ConfiguredTicksAbsAtGameStart"),
            Settlements = Reflect.InstanceProperty(worldObjects, "Settlements"),
            FactionOfPlayer = Reflect.StaticProperty(faction, "OfPlayer"),
            WorldObjectFaction = Reflect.InstanceProperty(worldObject, "Faction"),
            ParentMapGeneratorDef = Reflect.InstanceProperty(mapParent, "MapGeneratorDef"),
            ParentExtraGenStepDefs = Reflect.InstanceProperty(mapParent, "ExtraGenStepDefs"),
            IntVec3Ctor = intVec3.GetConstructor([typeof(int), typeof(int), typeof(int)])
                ?? throw new AdapterMismatchException("Verse.IntVec3(int, int, int)"),
            GenerateMap = Reflect.StaticMethod(mapGenerator, "GenerateMap", intVec3, mapParent, mapGeneratorDef, genStepsList,
                typeof(Action<>).MakeGenericType(map), typeof(bool), typeof(bool)),
            TmpGenSteps = Reflect.StaticField(mapGenerator, "tmpGenSteps"),
            RandPushState = Reflect.StaticMethod(rand, "PushState", typeof(int)),
            RandPopState = Reflect.StaticMethod(rand, "PopState"),
            DefNamed = (type, name) => Reflect.StaticMethod(defDatabase.MakeGenericType(type), "GetNamedSilentFail", typeof(string)).Invoke(null, [name]),
            ScenarioDef = scenarioDef,
            StorytellerDef = storytellerDef,
            DifficultyDef = difficultyDef,
            BiomeDef = biomeDef,
            MapGeneratorDef = mapGeneratorDef,
            GenStepDef = genStepDef,

            MapSize = Reflect.InstanceProperty(map, "Size"),
            MapTile = Reflect.InstanceProperty(map, "Tile"),
            MapBiome = Reflect.InstanceProperty(map, "Biome"),
            MapTileInfo = Reflect.InstanceProperty(map, "TileInfo"),
            MapGeneratorOfMap = Reflect.InstanceField(map, "generatorDef"),
            MapTerrainGrid = Reflect.InstanceField(map, "terrainGrid"),
            MapRoofGrid = Reflect.InstanceField(map, "roofGrid"),
            MapListerThings = Reflect.InstanceField(map, "listerThings"),
            TerrainAt = Reflect.InstanceMethod(terrainGrid, "TerrainAt", typeof(int)),
            RoofAt = Reflect.InstanceMethod(roofGrid, "RoofAt", typeof(int)),
            AllThings = Reflect.InstanceProperty(listerThings, "AllThings"),
            OccupiedRect = Reflect.StaticMethod(Reflect.Type($"Verse.GenAdj, {Game}"), "OccupiedRect", Reflect.Type($"Verse.Thing, {Game}")),
        };
    }

    private static object EnumValue(Type type, string name)
    {
        return Enum.GetNames(type).Contains(name) ? Enum.Parse(type, name) : throw new AdapterMismatchException($"{type.FullName}.{name}");
    }
}

/// <summary>
/// Generates one temporary world and one map with the game's own code after the
/// load, following the official developer quick-test setup
/// (Root_Play.SetupForQuickTestPlay → GameInitData.PrepForMapGen →
/// Scenario.PreMapGenerate → the map part of Game.InitNewGame), with the seed,
/// sizes and defs taken from the request instead of random/fixed values.
/// It stops when MapGenerator.GenerateMap returns: no camera, no Game.FinalizeInit
/// (ProgramState stays out of Playing), no game start, no ticks, no UI.
/// </summary>
public sealed class MapStage(MapRequest request, MapApi api)
{
    public static readonly string[] SkippedOfficialSteps =
    [
        "Root_Play scene, camera and UI: not created; the map is generated from a worker long event. Instead the worker creates a bare Camera object (Camera + AudioListener) and a Root_Play object whose Start is never called, holding a SoundRoot, a MusicManagerPlay and a UIRoot_Play that is constructed but never initialised or drawn: the parts of the Play scene that world and map generation touch",
        "Game.InitNewGame after MapGenerator.GenerateMap: not executed (starting thoughts, Game.FinalizeInit, camera jump, Scenario.PostGameStart, starting research, GameComponent.StartedNewGame); ProgramState never becomes Playing",
        "ticks: none run, so nothing that happens after the first tick is observed",
    ];

    public Dictionary<string, object?> Evidence { get; } = new();
    public object? Map { get; private set; }
    private object? _game;
    private readonly List<(string Name, double Seconds)> _steps = [];

    /// <summary>
    /// World.FinalizeInit and the map's when-finished actions reach the sound and
    /// music managers through Current.Root, which the official Play scene sets up.
    /// The worker has no scene, so it installs a Root_Play object whose Start is
    /// never called, with just those two parts, built on the main thread like
    /// Root.Start does. Runs as a synchronous long event before Generate.
    /// </summary>
    public void InstallPlayRoot()
    {
        Diagnostics.Stage = "map.installPlayRoot";
        // The "Camera" object of the Play scene, without CameraDriver: the sound
        // pool parents its camera sources to it.
        object cameraObject = api.GameObjectCtor.Invoke(["Camera", api.CameraComponents]);
        api.CurrentCamera.SetValue(null, api.GetComponent.Invoke(cameraObject, [api.CameraComponents[0]]));
        object root = Activator.CreateInstance(api.RootPlay)!;
        api.RootSoundRoot.SetValue(root, api.SoundRootCtor.Invoke(null));
        api.RootPlayMusicManager.SetValue(root, api.MusicManagerPlayCtor.Invoke(null));
        // Constructed but not Init()ed (Init clears messages and opens the dev palette).
        api.RootUiRoot.SetValue(root, Activator.CreateInstance(api.UIRootPlay));
        api.CurrentRoot.SetValue(null, root);
        api.CurrentRootPlay.SetValue(null, root);
    }

    public void Generate()
    {
        int seed = StableHash(request.Seed);
        api.RandPushState.Invoke(null, [seed]);
        try
        {
            Step("setupGame", SetupGame);
            Step("generateWorld", GenerateWorld);
            Step("chooseTile", ChooseTile);
            Step("prepareMapGeneration", PrepareMapGeneration);
            Step("generateMap", GenerateMap);
        }
        finally
        {
            api.RandPopState.Invoke(null, null);
            Evidence["steps"] = _steps.Select(s => new Dictionary<string, object> { ["name"] = s.Name, ["seconds"] = Math.Round(s.Seconds, 3) }).ToList();
        }
    }

    private void Step(string name, Action action)
    {
        var clock = System.Diagnostics.Stopwatch.StartNew();
        Diagnostics.Stage = $"map.{name}";
        try
        {
            action();
        }
        finally
        {
            _steps.Add((name, clock.Elapsed.TotalSeconds));
        }
    }

    private object Def(Type type, string name, string role)
    {
        return api.DefNamed(type, name) ?? throw new MapSetupException($"{role} def {name} ({type.Name}) is not loaded");
    }

    // Root_Play.SetupForQuickTestPlay, with request values for the scenario,
    // storyteller, difficulty, world seed, coverage and map size.
    private void SetupGame()
    {
        object scenario = api.ScenarioOfDef.GetValue(Def(api.ScenarioDef, request.Scenario, "scenario"))!;
        object storytellerDef = Def(api.StorytellerDef, request.Storyteller, "storyteller");
        object difficulty = Def(api.DifficultyDef, request.Difficulty, "difficulty");
        api.ProgramState.SetValue(null, api.ProgramStateEntry);
        api.ClearCaches.Invoke(null, null);
        _game = Activator.CreateInstance(api.GameType)!;
        api.CurrentGame.SetValue(null, _game);
        api.InitData.SetValue(_game, Activator.CreateInstance(api.GameInitData));
        api.Scenario.SetValue(_game, scenario);
        api.ScenarioPreConfigure.Invoke(scenario, null);
        api.Storyteller.SetValue(_game, api.StorytellerCtor.Invoke([storytellerDef, difficulty]));
    }

    private void GenerateWorld()
    {
        object world = api.GenerateWorld.Invoke(null, [request.PlanetCoverage, request.Seed, .. api.WorldDefaults, null, 0f])!;
        api.World.SetValue(_game, world);
        Evidence["worldSeed"] = request.Seed;
        Evidence["planetCoverage"] = request.PlanetCoverage;
    }

    private void ChooseTile()
    {
        object init = api.InitData.GetValue(_game)!;
        object world = api.World.GetValue(_game)!;
        object grid = api.WorldGrid.GetValue(world)!;
        object surface = api.GridSurface.GetValue(grid)!;
        object chosen;
        if (request.Tile is int id)
        {
            int count = (int)api.LayerTilesCount.GetValue(surface)!;
            if (id < 0 || id >= count)
            {
                throw new MapSetupException($"tile {id} is outside the surface layer (0..{count - 1})");
            }
            chosen = api.LayerPlanetTile.Invoke(surface, [id])!;
            if (!(bool)api.IsValidTileForNewSettlement.Invoke(null, [chosen, null, false])!)
            {
                throw new MapSetupException($"tile {id} cannot hold a new settlement (biome, impassable terrain or occupied)");
            }
        }
        else if (request.Biome is string biomeName)
        {
            object biome = Def(api.BiomeDef, biomeName, "biome");
            Func<object, bool> matches = t => ReferenceEquals(api.TilePrimaryBiome.GetValue(api.GridTileAt.GetValue(grid, [t])), biome);
            ParameterExpression parameter = Expression.Parameter(api.PlanetTile);
            Delegate validator = Expression.Lambda(typeof(Predicate<>).MakeGenericType(api.PlanetTile),
                Expression.Invoke(Expression.Constant(matches), Expression.Convert(parameter, typeof(object))), parameter).Compile();
            chosen = api.RandomSettlementTileFor.Invoke(null, [surface, api.FactionOfPlayer.GetValue(null), false, validator])!;
            if (!(bool)api.PlanetTileValid.GetValue(chosen)!)
            {
                throw new MapSetupException($"no tile with biome {biomeName} can hold a settlement in this world; try another seed or a larger planetCoverage");
            }
        }
        else
        {
            api.InitChooseRandomStartingTile.Invoke(init, null);
            chosen = api.InitStartingTile.GetValue(init)!;
            if (!(bool)api.PlanetTileValid.GetValue(chosen)!)
            {
                throw new MapSetupException("the game found no starting tile in this world");
            }
        }
        api.InitStartingTile.SetValue(init, chosen);
        api.InitMapSize.SetValue(init, request.Size);
        if (request.MapGenerator != null)
        {
            api.InitMapGeneratorDef.SetValue(init, Def(api.MapGeneratorDef, request.MapGenerator, "map generator"));
        }
        api.ScenarioPostIdeoChosen.Invoke(api.Scenario.GetValue(_game), null);
        Evidence["tile"] = api.PlanetTileId.GetValue(chosen);
    }

    private void PrepareMapGeneration()
    {
        api.InitPrepForMapGen.Invoke(api.InitData.GetValue(_game), null);
        api.ScenarioPreMapGenerate.Invoke(api.Scenario.GetValue(_game), null);
    }

    // The map part of Game.InitNewGame.
    private void GenerateMap()
    {
        object game = _game!;
        object init = api.InitData.GetValue(game)!;
        object world = api.World.GetValue(game)!;
        api.ClearCaches.Invoke(null, null);
        api.ProgramState.SetValue(null, api.ProgramStateMapInitializing);
        int size = (int)api.InitMapSize.GetValue(init)!;
        object mapSize = api.IntVec3Ctor.Invoke([size, 1, size]);
        object player = api.FactionOfPlayer.GetValue(null)!;
        object settlement = ((IEnumerable)api.Settlements.GetValue(api.WorldObjects.GetValue(world))!).Cast<object>()
            .FirstOrDefault(s => ReferenceEquals(api.WorldObjectFaction.GetValue(s), player))
            ?? throw new MapSetupException("the scenario created no player settlement on the world (needs a ScenPart_PlayerFaction)");
        object tickManager = api.TickManager.GetValue(game)!;
        api.GameStartAbsTick.SetValue(tickManager, api.ConfiguredTicksAbsAtGameStart.GetValue(null));
        object info = api.GameInfo.GetValue(game)!;
        api.InfoStartingTile.SetValue(info, api.InitStartingTile.GetValue(init));
        api.InfoPawns.SetValue(info, api.InitPawns.GetValue(init));
        object generator = api.InitMapGeneratorDef.GetValue(init) ?? api.ParentMapGeneratorDef.GetValue(settlement)!;
        IList extra = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(api.GenStepWithParams))!;
        foreach (object step in (IEnumerable)api.ParentExtraGenStepDefs.GetValue(settlement)!)
        {
            extra.Add(step);
        }
        foreach (string name in request.ExtraGenSteps)
        {
            extra.Add(Activator.CreateInstance(api.GenStepWithParams, Def(api.GenStepDef, name, "gen step"), Activator.CreateInstance(api.GenStepParams)));
        }
        Evidence["mapGenerator"] = DefName(generator);
        Map = api.GenerateMap.Invoke(null, [mapSize, settlement, generator, extra, null, false, false]);
        api.InitialMapSize.SetValue(api.WorldInfo.GetValue(world), mapSize);
        api.ProgramState.SetValue(null, api.ProgramStateEntry);
    }

    /// <summary>Run order of the gen steps of the last generated map (MapGenerator keeps it until the next map).</summary>
    public List<object> GenSteps()
    {
        return ((IEnumerable)api.TmpGenSteps.GetValue(null)!).Cast<object>().Select(s => Reflect.Member(s, "def")!).ToList();
    }

    internal static string? DefName(object? def) => def == null ? null : (string?)Reflect.Member(def, "defName");

    internal static string? ModOf(object? def)
    {
        object? pack = def == null ? null : Reflect.Member(def, "modContentPack");
        return pack == null ? null : ((string?)Reflect.Member(pack, "PackageId"))?.ToLowerInvariant();
    }

    // string.GetHashCode is randomized per process; the seed must be stable across runs.
    internal static int StableHash(string text)
    {
        unchecked
        {
            uint hash = 2166136261;
            foreach (char c in text)
            {
                hash = (hash ^ c) * 16777619;
            }
            return (int)hash;
        }
    }

    public object? Game => _game;
}

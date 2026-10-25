using System.Collections;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// Reads the generated map (never changes it) and writes map-observation.json:
/// per-cell layers (terrain, roof, the most visible thing) as base64 little-endian
/// palette indices, def palettes with their mod, per-def counts, and a list of
/// the placed things that are not plants, filth or natural rock. The Controller
/// renders the image and judges map expectations from this file.
/// </summary>
public sealed class MapObservation(MapApi api, MapStage stage, int maxListed)
{
    // Which thing is shown for a cell when several share it.
    private static readonly Dictionary<string, int> Priority = new()
    {
        ["Pawn"] = 6, ["Building"] = 5, ["Item"] = 4, ["Plant"] = 3, ["Filth"] = 2,
    };

    private sealed class ThingInfo(int index, object def, string category, int priority)
    {
        public int Index { get; } = index;
        public object Def { get; } = def;
        public string Category { get; } = category;
        public int Priority { get; } = priority;
        public int Count { get; set; }
    }

    private readonly Dictionary<object, ThingInfo> _things = new(ReferenceEqualityComparer.Instance);
    private readonly Dictionary<object, int> _terrain = new(ReferenceEqualityComparer.Instance);
    private readonly Dictionary<object, int> _roofs = new(ReferenceEqualityComparer.Instance);

    public Dictionary<string, object?> Write(string path)
    {
        object map = stage.Map!;
        object size = api.MapSize.GetValue(map)!;
        int width = (int)Reflect.Member(size, "x")!;
        int height = (int)Reflect.Member(size, "z")!;
        int cells = width * height;

        var terrainCells = new ushort[cells];
        var terrainCounts = new List<int>();
        var terrainDefs = new List<object>();
        object terrainGrid = api.MapTerrainGrid.GetValue(map)!;
        for (int i = 0; i < cells; i++)
        {
            object def = api.TerrainAt.Invoke(terrainGrid, [i])!;
            if (!_terrain.TryGetValue(def, out int index))
            {
                index = terrainDefs.Count;
                _terrain[def] = index;
                terrainDefs.Add(def);
                terrainCounts.Add(0);
            }
            terrainCells[i] = (ushort)index;
            terrainCounts[index]++;
        }

        var roofCells = new byte[cells];
        var roofDefs = new List<object>();
        var roofCounts = new List<int>();
        object roofGrid = api.MapRoofGrid.GetValue(map)!;
        for (int i = 0; i < cells; i++)
        {
            object? def = api.RoofAt.Invoke(roofGrid, [i]);
            if (def == null)
            {
                continue;
            }
            if (!_roofs.TryGetValue(def, out int index))
            {
                roofDefs.Add(def);
                roofCounts.Add(0);
                index = roofDefs.Count;
                _roofs[def] = index;
            }
            roofCells[i] = (byte)index;
            roofCounts[index - 1]++;
        }

        // Index 0 means "no thing"; palette entry i describes index i + 1.
        var thingCells = new ushort[cells];
        var cellPriority = new byte[cells];
        var thingDefs = new List<ThingInfo>();
        var listed = new List<Dictionary<string, object?>>();
        int unlisted = 0;
        IList all = (IList)api.AllThings.GetValue(api.MapListerThings.GetValue(map))!;
        foreach (object thing in all)
        {
            object def = Reflect.Member(thing, "def")!;
            if (!_things.TryGetValue(def, out ThingInfo? info))
            {
                string category = Reflect.Member(def, "category")!.ToString()!;
                info = new ThingInfo(thingDefs.Count + 1, def, category, Priority.GetValueOrDefault(category));
                _things[def] = info;
                thingDefs.Add(info);
            }
            info.Count++;
            object rect = api.OccupiedRect.Invoke(null, [thing])!;
            int minX = Math.Max(0, (int)Reflect.Member(rect, "minX")!), maxX = Math.Min(width - 1, (int)Reflect.Member(rect, "maxX")!);
            int minZ = Math.Max(0, (int)Reflect.Member(rect, "minZ")!), maxZ = Math.Min(height - 1, (int)Reflect.Member(rect, "maxZ")!);
            if (info.Priority > 0)
            {
                for (int z = minZ; z <= maxZ; z++)
                {
                    for (int x = minX; x <= maxX; x++)
                    {
                        int cell = z * width + x;
                        if (info.Priority > cellPriority[cell])
                        {
                            cellPriority[cell] = (byte)info.Priority;
                            thingCells[cell] = (ushort)info.Index;
                        }
                    }
                }
            }
            if (!IsListed(info))
            {
                continue;
            }
            if (listed.Count >= maxListed)
            {
                unlisted++;
                continue;
            }
            object position = Reflect.Member(thing, "Position")!;
            object? faction = Reflect.Member(thing, "Faction");
            object? stuff = Reflect.Member(thing, "Stuff");
            var entry = new Dictionary<string, object?>
            {
                ["def"] = info.Index,
                ["x"] = Reflect.Member(position, "x"),
                ["z"] = Reflect.Member(position, "z"),
                ["rect"] = new[] { minX, minZ, maxX, maxZ },
                ["rotation"] = Reflect.Member(Reflect.Member(thing, "Rotation")!, "AsInt"),
                ["faction"] = faction == null ? null : MapStage.DefName(Reflect.Member(faction, "def")),
                ["playerFaction"] = faction != null && (bool)Reflect.Member(faction, "IsPlayer")!,
                ["stuff"] = MapStage.DefName(stuff),
            };
            if (info.Category == "Pawn")
            {
                entry["kind"] = MapStage.DefName(Reflect.Member(thing, "kindDef"));
            }
            listed.Add(entry);
        }

        object tileInfo = api.MapTileInfo.GetValue(map)!;
        var genSteps = stage.GenSteps().Select(d => new Dictionary<string, object?>
        {
            ["defName"] = MapStage.DefName(d), ["mod"] = MapStage.ModOf(d), ["order"] = Reflect.Member(d, "order"),
        }).ToList();
        var header = new Dictionary<string, object?>
        {
            ["width"] = width,
            ["height"] = height,
            ["tile"] = stage.Evidence.GetValueOrDefault("tile"),
            ["biome"] = MapStage.DefName(api.MapBiome.GetValue(map)),
            ["hilliness"] = api.TileHilliness.GetValue(tileInfo)?.ToString(),
            ["tileMutators"] = ((IEnumerable)api.TileMutators.GetValue(tileInfo)!).Cast<object>().Select(MapStage.DefName).ToList(),
            ["mapGenerator"] = MapStage.DefName(api.MapGeneratorOfMap.GetValue(map)),
            ["genSteps"] = genSteps,
            ["thingCount"] = all.Count,
            ["listedThings"] = listed.Count,
            ["unlistedThings"] = unlisted,
        };

        using (var stream = new FileStream(path + ".tmp", FileMode.Create, FileAccess.Write))
        using (var json = new Utf8JsonWriter(stream))
        {
            json.WriteStartObject();
            json.WriteString("recordType", "rwmtMapObservation");
            json.WriteNumber("schemaVersion", 1);
            foreach ((string key, object? value) in header)
            {
                json.WritePropertyName(key);
                JsonSerializer.Serialize(json, value);
            }
            json.WriteStartObject("palettes");
            json.WriteStartArray("terrain");
            for (int i = 0; i < terrainDefs.Count; i++)
            {
                WriteTerrain(json, terrainDefs[i], terrainCounts[i]);
            }
            json.WriteEndArray();
            json.WriteStartArray("roof");
            for (int i = 0; i < roofDefs.Count; i++)
            {
                json.WriteStartObject();
                json.WriteString("defName", MapStage.DefName(roofDefs[i]));
                json.WriteString("mod", MapStage.ModOf(roofDefs[i]));
                json.WriteBoolean("thick", (bool)Reflect.Member(roofDefs[i], "isThickRoof")!);
                json.WriteBoolean("natural", (bool)Reflect.Member(roofDefs[i], "isNatural")!);
                json.WriteNumber("cells", roofCounts[i]);
                json.WriteEndObject();
            }
            json.WriteEndArray();
            json.WriteStartArray("thing");
            foreach (ThingInfo info in thingDefs)
            {
                WriteThing(json, info);
            }
            json.WriteEndArray();
            json.WriteEndObject();
            json.WriteStartObject("layers");
            json.WriteString("encoding", "base64 little-endian, row-major from z=0 (south) upwards, x from west");
            json.WriteBase64String("terrain", LittleEndian(terrainCells));
            json.WriteBase64String("roof", roofCells);
            json.WriteBase64String("thing", LittleEndian(thingCells));
            json.WriteEndObject();
            json.WritePropertyName("things");
            JsonSerializer.Serialize(json, listed);
            json.WriteEndObject();
        }
        File.Move(path + ".tmp", path, overwrite: true);
        header.Remove("genSteps");
        header["genSteps"] = genSteps.Count;
        header["observationFile"] = Path.GetFileName(path);
        return header;
    }

    // Natural rock, plants and filth are summarized by the layers and counts only.
    private static bool IsListed(ThingInfo info)
    {
        if (info.Category is "Plant" or "Filth" or "Mote" or "Gas" or "Ethereal" or "Projectile" or "Attachment")
        {
            return false;
        }
        object? building = Reflect.Member(info.Def, "building");
        return building == null || !(bool)Reflect.Member(building, "isNaturalRock")!;
    }

    private static void WriteTerrain(Utf8JsonWriter json, object def, int cells)
    {
        json.WriteStartObject();
        json.WriteString("defName", MapStage.DefName(def));
        json.WriteString("mod", MapStage.ModOf(def));
        json.WriteNumber("cells", cells);
        json.WriteNumber("fertility", Convert.ToDouble(Reflect.Member(def, "fertility")));
        json.WriteString("passability", Reflect.Member(def, "passability")?.ToString());
        json.WriteBoolean("natural", (bool)Reflect.Member(def, "natural")!);
        json.WriteBoolean("water", (bool)Reflect.Member(def, "IsWater")!);
        json.WriteBoolean("ice", (bool)Reflect.Member(def, "IsIce")!);
        json.WriteBoolean("rock", (bool)Reflect.Member(def, "IsRock")!);
        json.WriteBoolean("soil", (bool)Reflect.Member(def, "IsSoil")!);
        json.WriteBoolean("floor", (bool)Reflect.Member(def, "IsFloor")!);
        json.WriteBoolean("constructed", Reflect.Member(def, "costList") != null || (int)Reflect.Member(def, "costStuffCount")! > 0);
        WriteColor(json, Reflect.Member(def, "color"));
        json.WriteEndObject();
    }

    private static void WriteThing(Utf8JsonWriter json, ThingInfo info)
    {
        object def = info.Def;
        json.WriteStartObject();
        json.WriteString("defName", MapStage.DefName(def));
        json.WriteString("mod", MapStage.ModOf(def));
        json.WriteString("category", info.Category);
        json.WriteNumber("count", info.Count);
        object? building = Reflect.Member(def, "building");
        json.WriteBoolean("naturalRock", building != null && (bool)Reflect.Member(building, "isNaturalRock")!);
        json.WriteBoolean("resourceRock", building != null && (bool)Reflect.Member(building, "isResourceRock")!);
        object? plant = Reflect.Member(def, "plant");
        json.WriteBoolean("tree", plant != null && (bool)Reflect.Member(plant, "IsTree")!);
        object? race = Reflect.Member(def, "race");
        json.WriteBoolean("humanlike", race != null && (bool)Reflect.Member(race, "Humanlike")!);
        json.WriteBoolean("animal", race != null && (bool)Reflect.Member(race, "Animal")!);
        json.WriteEndObject();
    }

    private static void WriteColor(Utf8JsonWriter json, object? color)
    {
        if (color == null)
        {
            json.WriteNull("color");
            return;
        }
        json.WriteStartArray("color");
        foreach (string channel in new[] { "r", "g", "b", "a" })
        {
            json.WriteNumberValue(Math.Round(Convert.ToDouble(Reflect.Member(color, channel)), 4));
        }
        json.WriteEndArray();
    }

    private static byte[] LittleEndian(ushort[] values)
    {
        var bytes = new byte[values.Length * 2];
        for (int i = 0; i < values.Length; i++)
        {
            bytes[2 * i] = (byte)values[i];
            bytes[2 * i + 1] = (byte)(values[i] >> 8);
        }
        return bytes;
    }
}

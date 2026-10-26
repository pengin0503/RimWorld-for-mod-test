using RimWorldValidation.Gui.Model;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// What the user chose, shared by the tabs. MODs are the game's own
/// ModMetaData for the links under host/Mods; a validation request names
/// their original folders (GuiRequest.ModsMap).
/// </summary>
internal static class GuiState
{
    /// <summary>MODs the validation loads, in load order.</summary>
    public static readonly List<ModMetaData> Active = [];

    /// <summary>packageIds (lowercase) of the active MODs under test; the others are loaded as prerequisites.</summary>
    public static readonly HashSet<string> Targets = [];

    /// <summary>Official content folders besides Core (Royalty, Ideology, ...) the validation loads.</summary>
    public static readonly HashSet<string> Expansions = [];

    public static ModMetaData? Selected;

    /// <summary>Last message about the MOD list (an import, a MOD not found), shown on the MOD tab.</summary>
    public static string? ModsNotice;

    /// <summary>The choices of the other tabs (levels, language, map, bill, extra JSON); MODs and official content are above.</summary>
    public static RunSettings Options = new() { Language = "Japanese" };

    private static bool _initialized;

    public static GuiRequest Request => Boot.Request;

    // Release order, as the Controller's official list; content it does not know goes last.
    private static readonly string[] OfficialOrder = ["Core", "Royalty", "Ideology", "Biotech", "Anomaly", "Odyssey"];

    public static IEnumerable<ModMetaData> OfficialMods => ModLister.AllInstalledMods.Where(m => m.Official)
        .OrderBy(m => Array.IndexOf(OfficialOrder, m.FolderName) is int i and >= 0 ? i : OfficialOrder.Length)
        .ThenBy(m => m.FolderName, StringComparer.Ordinal);

    public static IEnumerable<ModMetaData> CandidateMods => ModLister.AllInstalledMods.Where(m => !m.Official);

    /// <summary>Once the game knows its installed MODs: all installed official content is selected.</summary>
    public static void EnsureInitialized()
    {
        if (_initialized)
        {
            return;
        }
        _initialized = true;
        foreach (ModMetaData mod in OfficialMods.Where(m => !m.IsCoreMod))
        {
            Expansions.Add(mod.FolderName);
        }
    }

    /// <summary>The MOD's original folder (what the Controller is given), not the link in the GUI's run directory.</summary>
    public static string OriginalPath(ModMetaData mod) =>
        Request.ModsMap.TryGetValue(mod.FolderName, out string? path) ? path : mod.RootDir.FullName;

    public static ModMetaData? FindByOriginalPath(string path)
    {
        string full = Path.GetFullPath(path);
        return CandidateMods.FirstOrDefault(m => string.Equals(Path.GetFullPath(OriginalPath(m)), full,
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal));
    }

    public static ModMetaData? FindCandidate(string packageId) =>
        CandidateMods.FirstOrDefault(m => m.packageIdLowerCase == Normalize(packageId));

    /// <summary>Lowercase packageId without the "_steam"/"_copy" postfix the game adds to duplicates.</summary>
    public static string Normalize(string packageId)
    {
        string id = packageId.Trim().ToLowerInvariant();
        foreach (string postfix in new[] { "_steam", "_copy" })
        {
            if (id.EndsWith(postfix, StringComparison.Ordinal))
            {
                return id[..^postfix.Length];
            }
        }
        return id;
    }

    public static bool IsTarget(ModMetaData mod) => Targets.Contains(mod.packageIdLowerCase);

    public static void SetTarget(ModMetaData mod, bool target)
    {
        if (target)
        {
            Targets.Add(mod.packageIdLowerCase);
        }
        else
        {
            Targets.Remove(mod.packageIdLowerCase);
        }
    }

    public static void Activate(ModMetaData mod)
    {
        if (!Active.Contains(mod))
        {
            Active.Add(mod);
        }
    }

    public static void Deactivate(ModMetaData mod)
    {
        Active.Remove(mod);
        Targets.Remove(mod.packageIdLowerCase);
    }

    public static void Move(int from, int to)
    {
        if (from < 0 || from >= Active.Count)
        {
            return;
        }
        ModMetaData mod = Active[from];
        Active.RemoveAt(from);
        Active.Insert(Math.Clamp(to > from ? to - 1 : to, 0, Active.Count), mod);
    }

    /// <summary>packageIds the active MODs depend on that are neither active nor selected official content.</summary>
    public static IReadOnlyList<(ModMetaData Mod, string Missing)> MissingDependencies()
    {
        var loaded = new HashSet<string>(Active.Select(m => m.packageIdLowerCase));
        foreach (ModMetaData official in OfficialMods.Where(m => m.IsCoreMod || Expansions.Contains(m.FolderName)))
        {
            loaded.Add(official.packageIdLowerCase);
        }
        var missing = new List<(ModMetaData, string)>();
        foreach (ModMetaData mod in Active)
        {
            foreach (ModDependency dependency in mod.Dependencies)
            {
                IEnumerable<string> ids = new[] { dependency.packageId }.Concat(dependency.alternativePackageIds ?? []);
                if (!ids.Any(id => loaded.Contains(Normalize(id ?? ""))))
                {
                    missing.Add((mod, dependency.displayName.NullOrEmpty() ? dependency.packageId : $"{dependency.displayName}（{dependency.packageId}）"));
                }
            }
        }
        return missing;
    }

    /// <summary>Sets every choice at once (test scripts). A MOD path the GUI does not offer is an error.</summary>
    public static void Apply(RunSettings settings)
    {
        EnsureInitialized();
        var mods = new List<(ModMetaData Mod, bool Target)>();
        foreach (ModChoice choice in settings.Mods)
        {
            ModMetaData mod = FindByOriginalPath(choice.Path) ?? throw new InvalidOperationException($"no MOD folder {choice.Path} in the GUI's list");
            mods.Add((mod, choice.Target));
        }
        var official = OfficialMods.ToDictionary(m => m.FolderName, m => m);
        foreach (string folder in settings.Official.Where(f => !official.ContainsKey(f)))
        {
            throw new InvalidOperationException($"no official content {folder}");
        }
        Expansions.Clear();
        Expansions.UnionWith(settings.Official.Where(f => !official[f].IsCoreMod));
        Active.Clear();
        Targets.Clear();
        foreach (var (mod, target) in mods)
        {
            Activate(mod);
            SetTarget(mod, target);
        }
        Selected = Active.FirstOrDefault();
        ModsNotice = null;
        Options = settings with { Official = [], Mods = [] };
    }

    /// <summary>
    /// Takes the load order from the game's own ModsConfig.xml (read only):
    /// the official content it lists and, in its order, the MODs found here.
    /// </summary>
    public static void ImportUserModsConfig()
    {
        if (Request.UserModsConfig == null)
        {
            ModsNotice = "本家の ModsConfig.xml が見つかりません（gui_host.py setup --mods-config で指定できます）。";
            return;
        }
        IReadOnlyList<string> ids;
        try
        {
            ids = ModsConfigReader.ReadActive(Request.UserModsConfig);
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException)
        {
            ModsNotice = $"本家の ModsConfig.xml を読めませんでした：{e.Message}";
            return;
        }
        var official = OfficialMods.ToDictionary(m => m.packageIdLowerCase, m => m);
        var missing = new List<string>();
        Active.Clear();
        Targets.Clear();
        Expansions.Clear();
        foreach (string id in ids)
        {
            if (official.TryGetValue(Normalize(id), out ModMetaData? content))
            {
                if (!content.IsCoreMod)
                {
                    Expansions.Add(content.FolderName);
                }
            }
            else if (FindCandidate(id) is ModMetaData mod)
            {
                Activate(mod);
            }
            else
            {
                missing.Add(id);
            }
        }
        Selected = Active.FirstOrDefault();
        ModsNotice = $"本家の読み込み順から {Active.Count} 件を取り込みました。"
            + (missing.Count > 0 ? $"見つからない {missing.Count} 件は除きました：{string.Join(", ", missing.Take(5))}{(missing.Count > 5 ? " ほか" : "")}" : "");
    }
}

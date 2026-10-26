using RimWorld;
using RimWorldValidation.Gui.Model;
using UnityEngine;
using Verse;

namespace RimWorldValidation.Gui;

/// <summary>
/// What to check: A always, B, the language, one generated map, the crafting
/// ingredients case (C, experimental) and extra expectations as JSON. Starts
/// the validation.
/// </summary>
internal sealed class SettingsTab : IGuiTab
{
    private const float ColumnGap = 30f;
    private const int MaxCandidates = 30;
    private Vector2 _extraScroll;

    public string Id => "settings";

    public string Label => "検証内容";

    public void Draw(Rect rect)
    {
        GuiState.EnsureInitialized();
        float columnWidth = (rect.width - ColumnGap) / 2f;
        Rect left = new(rect.x, rect.y, columnWidth, rect.height - 70f);
        Rect right = new(left.xMax + ColumnGap, rect.y, columnWidth, rect.height - 70f);
        DrawLeft(left);
        DrawRight(right);
        DrawStart(new Rect(rect.x, rect.yMax - 60f, rect.width, 60f));
    }

    private static void DrawLeft(Rect rect)
    {
        var list = new Listing_Standard();
        list.Begin(rect);
        Text.Font = GameFont.Medium;
        list.Label("検証の段階");
        Text.Font = GameFont.Small;
        bool levelA = true;
        list.CheckboxLabeled("A 読み込み（XML・Def・翻訳のエラー）　常に実行", ref levelA, "必ず実行します。");
        list.CheckboxLabeled("B DLL の読み込みと Harmony パッチの登録", ref GuiState.LevelB,
            "期待するパッチは右下の「追加の期待値」に expectations.harmony として書けます。");
        list.Gap();
        if (list.ButtonTextLabeledPct("言語", LanguageLabel(GuiState.Language), 0.4f))
        {
            Find.WindowStack.Add(new FloatMenu(LanguageDatabase.AllLoadedLanguages
                .Select(language => new FloatMenuOption($"{language.FriendlyNameNative}（{RequestName(language)}）",
                    () => GuiState.Language = RequestName(language)))
                .ToList()));
        }
        list.GapLine();

        Text.Font = GameFont.Medium;
        list.Label("マップ");
        Text.Font = GameFont.Small;
        list.CheckboxLabeled("マップを 1 枚作り、対象の MOD が置いた物を確かめる", ref GuiState.MapEnabled,
            "公式の開発者用クイックテストと同じ設定で作ります。比較のため、対象なしでも同じ種で作ります。");
        if (GuiState.MapEnabled)
        {
            GuiState.MapSeed = list.TextEntryLabeled("種（seed）", GuiState.MapSeed);
            string biome = GuiState.MapBiome.NullOrEmpty() ? "指定なし（種で決まる）" : BiomeLabel(GuiState.MapBiome!);
            if (list.ButtonTextLabeledPct("バイオーム", biome, 0.4f))
            {
                var options = new List<FloatMenuOption> { new("指定なし（種で決まる）", () => GuiState.MapBiome = null) };
                options.AddRange(DefDatabase<BiomeDef>.AllDefs.Where(b => b.canBuildBase && b.implemented)
                    .OrderBy(b => b.label)
                    .Select(b => new FloatMenuOption($"{b.LabelCap}（{b.defName}）", () => GuiState.MapBiome = b.defName)));
                Find.WindowStack.Add(new FloatMenu(options));
            }
        }
        list.End();
    }

    private void DrawRight(Rect rect)
    {
        var list = new Listing_Standard();
        list.Begin(rect);
        Text.Font = GameFont.Medium;
        list.Label("製造指示の材料（C・実験）");
        Text.Font = GameFont.Small;
        list.CheckboxLabeled("レシピの材料の候補に、ある物が出るか・許可されているかを調べる", ref GuiState.BillEnabled,
            "製造指示の「材料」画面と同じ処理で調べます。結果は常に実験扱いです。");
        if (GuiState.BillEnabled)
        {
            DefField(list, "レシピの defName", GuiState.BillRecipe, text => GuiState.BillRecipe = text, RecipeCandidates);
            DefField(list, "材料の defName", GuiState.BillThing, text => GuiState.BillThing = text, ThingCandidates);
            list.CheckboxLabeled("材料の候補に出るはず", ref GuiState.BillVisible);
            list.CheckboxLabeled("最初から許可されているはず", ref GuiState.BillAllowed);
            GUI.color = ColoredText.SubtleGrayColor;
            list.Label("候補は公式の Def からです。MOD が足すレシピ・材料は defName を直接入れてください。");
            GUI.color = Color.white;
        }
        list.GapLine();
        Text.Font = GameFont.Medium;
        list.Label("追加の期待値（JSON・上級者向け）");
        Text.Font = GameFont.Small;
        GUI.color = ColoredText.SubtleGrayColor;
        list.Label("{\"expectations\": {...}, \"allow\": {...}} の形で。書き方は docs/contracts/mod-validation-v1.md。");
        GUI.color = Color.white;
        Rect area = list.GetRect(Mathf.Max(80f, rect.height - list.CurHeight - 4f));
        Rect view = new(0f, 0f, area.width - 16f, Mathf.Max(area.height, Text.CalcHeight(GuiState.ExtraJson, area.width - 16f) + 20f));
        Widgets.BeginScrollView(area, ref _extraScroll, view);
        GuiState.ExtraJson = Widgets.TextArea(view, GuiState.ExtraJson);
        Widgets.EndScrollView();
        list.End();
    }

    private static void DrawStart(Rect rect)
    {
        RunSettings settings = GuiState.CurrentSettings();
        int targets = settings.Mods.Count(m => m.Target);
        string summary = $"MOD {settings.Mods.Count} 件（対象 {targets}）、公式：{string.Join("・", settings.Official)}、言語：{LanguageLabel(settings.Language)}";
        Text.Anchor = TextAnchor.MiddleLeft;
        Widgets.Label(new Rect(rect.x, rect.y, rect.width - 260f, 28f), summary);
        if (RunController.StartError != null)
        {
            GUI.color = ColorLibrary.RedReadable;
            Widgets.Label(new Rect(rect.x, rect.y + 28f, rect.width - 260f, 30f), RunController.StartError);
            GUI.color = Color.white;
        }
        Text.Anchor = TextAnchor.UpperLeft;
        if (Widgets.ButtonText(new Rect(rect.xMax - 240f, rect.y + 6f, 240f, 48f), "検証を始める", active: !RunController.Busy))
        {
            RunController.Start(settings);
        }
    }

    private static void DefField(Listing_Standard list, string label, string value, Action<string> set,
        Func<string, IEnumerable<(string Label, string DefName)>> candidates)
    {
        Rect row = list.GetRect(Text.LineHeight + 6f);
        Widgets.Label(row.LeftPart(0.35f), label);
        Rect field = new(row.x + row.width * 0.35f, row.y, row.width * 0.65f - 70f, row.height);
        value = Widgets.TextField(field, value);
        set(value);
        if (Widgets.ButtonText(new Rect(field.xMax + 6f, row.y, 64f, row.height), "候補"))
        {
            var options = candidates(value).Take(MaxCandidates).ToList();
            Find.WindowStack.Add(new FloatMenu(options.Count == 0
                ? [new FloatMenuOption("公式の Def に当てはまるものがありません", null)]
                : options.Select(o => new FloatMenuOption($"{o.Label}（{o.DefName}）", () => set(o.DefName))).ToList()));
        }
        list.Gap(4f);
    }

    private static IEnumerable<(string, string)> RecipeCandidates(string typed) =>
        DefDatabase<RecipeDef>.AllDefs.Where(r => Matches(r, typed)).OrderBy(r => r.defName).Select(r => ((string)r.LabelCap, r.defName));

    private static IEnumerable<(string, string)> ThingCandidates(string typed)
    {
        RecipeDef? recipe = DefDatabase<RecipeDef>.GetNamedSilentFail(GuiState.BillRecipe.Trim());
        IEnumerable<ThingDef> things = recipe != null
            ? recipe.ingredients.SelectMany(i => i.filter.AllowedThingDefs).Concat(recipe.fixedIngredientFilter?.AllowedThingDefs ?? [])
            : DefDatabase<ThingDef>.AllDefs.Where(t => t.category == ThingCategory.Item);
        return things.Distinct().Where(t => Matches(t, typed)).OrderBy(t => t.defName).Select(t => ((string)t.LabelCap, t.defName));
    }

    private static bool Matches(Def def, string typed) =>
        typed.NullOrEmpty() || def.defName.IndexOf(typed.Trim(), StringComparison.OrdinalIgnoreCase) >= 0
        || (def.label?.IndexOf(typed.Trim(), StringComparison.OrdinalIgnoreCase) ?? -1) >= 0;

    /// <summary>The request names a language by the English part of the game's folder name: "Japanese (日本語)" → "Japanese".</summary>
    private static string RequestName(LoadedLanguage language) => language.folderName.Split(" (")[0];

    private static string LanguageLabel(string requestName)
    {
        LoadedLanguage? language = LanguageDatabase.AllLoadedLanguages.FirstOrDefault(l => RequestName(l) == requestName);
        return language == null ? requestName : $"{language.FriendlyNameNative}（{requestName}）";
    }

    private static string BiomeLabel(string defName) =>
        DefDatabase<BiomeDef>.GetNamedSilentFail(defName) is BiomeDef biome ? $"{biome.LabelCap}（{defName}）" : defName;
}

using System.Collections;
using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>A fixed, non-rendered case. No caller-supplied type or method is invoked.</summary>
public static class BillIngredientOptions
{
    public const string CaseId = "bill-ingredient-options.v1";

    public static void Write(Utf8JsonWriter json, JsonElement expectations)
    {
        if (!expectations.TryGetProperty("billIngredients", out JsonElement items) || items.GetArrayLength() == 0)
        {
            json.WriteStartArray("billIngredients");
            json.WriteEndArray();
            return;
        }
        var rows = new List<Dictionary<string, object?>>();
        PropertyInfo? current = null;
        object? previous = null;
        try
        {
            current = Reflect.StaticProperty(GameType("Verse.Current"), "Game");
            previous = current.GetValue(null);
            // Bill's real constructor needs a real UniqueIDsManager. The fresh Game also
            // defines the initial undiscovered-item state. Never start/finalize/tick it.
            object game = Activator.CreateInstance(GameType("Verse.Game"))!;
            current.SetValue(null, game);
            foreach (JsonElement item in items.EnumerateArray())
            {
                try
                {
                    rows.Add(Observe(item, game));
                }
                catch (Exception e) when (e is not OutOfMemoryException)
                {
                    rows.Add(Error(item, e));
                }
            }
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            rows.Clear();
            foreach (JsonElement item in items.EnumerateArray())
            {
                rows.Add(Error(item, e));
            }
        }
        finally
        {
            if (current != null)
            {
                current.SetValue(null, previous);
            }
        }
        json.WritePropertyName("billIngredients");
        JsonSerializer.Serialize(json, rows);
    }

    private static Type GameType(string name) => Reflect.Type(name + ", Assembly-CSharp");
    private static IEnumerable<object> Objects(object value) => ((IEnumerable)value).Cast<object>();

    private static object Def(Type type, string name)
    {
        Type database = GameType("Verse.DefDatabase`1").MakeGenericType(type);
        return Reflect.StaticMethod(database, "GetNamedSilentFail", typeof(string)).Invoke(null, [name])
            ?? throw new CaseContextException("defMissing", $"{type.Name} {name} is not loaded");
    }

    private static Dictionary<string, object?> Observe(JsonElement item, object game)
    {
        Type recipeType = GameType("Verse.RecipeDef");
        Type thingType = GameType("Verse.ThingDef");
        Type filterType = GameType("Verse.ThingFilter");
        Type nodeType = GameType("Verse.TreeNode_ThingCategory");
        Type specialType = GameType("Verse.SpecialThingFilterDef");
        Type listingType = GameType("Verse.Listing_TreeThingFilter");
        object recipe = Def(recipeType, item.GetProperty("recipe").GetString()!);
        object thing = Def(thingType, item.GetProperty("thing").GetString()!);
        if ((bool)Reflect.Member(recipe, "IsSurgery")!)
        {
            throw new CaseContextException("paneNotEditable", "surgery is outside the production-bill case");
        }
        bool paneEligible = Objects(Reflect.Member(recipe, "ingredients")!)
            .Any(i => !(bool)Reflect.Member(i, "IsFixedIngredient")!);
        if (!paneEligible)
        {
            throw new CaseContextException("paneNotEditable", "the recipe has no editable ingredient pane");
        }
        object bill = Reflect.StaticMethod(GameType("RimWorld.BillUtility"), "MakeNewBill", recipeType,
            GameType("RimWorld.Precept_ThingStyle")).Invoke(null, [recipe, null])!;
        if (!GameType("RimWorld.Bill_Production").IsInstanceOfType(bill))
        {
            throw new CaseContextException("contextUnavailable", "recipe did not create a production bill");
        }
        object filter = Reflect.Member(bill, "ingredientFilter")!;
        object parent = Reflect.Member(recipe, "fixedIngredientFilter")!;
        object node = Reflect.Member(parent, "DisplayRootCategory")
            ?? throw new CaseContextException("categoryMissing", "ingredient display root is unavailable");
        // Use the actual bill dialog's special-filter exclusions, with this recipe's
        // additions, rather than reconstructing the game's DLC-dependent list.
        var hidden = Objects(Reflect.StaticProperty(GameType("RimWorld.Dialog_BillConfig"),
            "HiddenSpecialThingFilters").GetValue(null)!).ToList();
        if (Reflect.Member(recipe, "forceHiddenSpecialFilters") is object extra)
        {
            hidden.AddRange(Objects(extra));
        }
        Array typedHidden = Array.CreateInstance(specialType, hidden.Count);
        for (int i = 0; i < hidden.Count; i++)
        {
            typedHidden.SetValue(hidden[i], i);
        }
        Type searchType = Reflect.Type("RimWorld.QuickSearchFilter, Assembly-CSharp");
        ConstructorInfo ctor = listingType.GetConstructor([filterType, filterType,
            typeof(IEnumerable<>).MakeGenericType(thingType), typeof(IEnumerable<>).MakeGenericType(specialType),
            typeof(List<>).MakeGenericType(thingType), searchType])
            ?? throw new AdapterMismatchException("Listing_TreeThingFilter constructor");
        object listing = ctor.Invoke([filter, parent, null, typedHidden,
            Reflect.InstanceMethod(recipeType, "GetPremultipliedSmallIngredients").Invoke(recipe, null),
            Activator.CreateInstance(searchType)]);
        MethodInfo itemVisibleMethod = Reflect.InstanceMethod(listingType, "Visible", thingType);
        MethodInfo categoryVisibleMethod = Reflect.InstanceMethod(listingType, "Visible", nodeType);
        bool itemVisible = (bool)itemVisibleMethod.Invoke(listing, [thing])!;
        (bool reachable, bool categoryVisible) = Reachable(node, thing, listing, categoryVisibleMethod);
        if (!reachable)
        {
            throw new CaseContextException("categoryMissing", "the material has no path from the displayed category root");
        }
        object hiddenManager = Reflect.Member(game, "hiddenItemsManager")!;
        bool hiddenByDiscovery = (bool)Reflect.InstanceMethod(hiddenManager.GetType(), "Hidden", thingType)
            .Invoke(hiddenManager, [thing])!;
        bool allowed = (bool)Reflect.InstanceMethod(filterType, "Allows", thingType).Invoke(filter, [thing])!;
        bool parentAllows = (bool)Reflect.InstanceMethod(filterType, "Allows", thingType).Invoke(parent, [thing])!;
        bool specialDisallows = (bool)Reflect.InstanceMethod(filterType, "IsAlwaysDisallowedDueToSpecialFilters", thingType)
            .Invoke(parent, [thing])!;
        bool visible = categoryVisible && itemVisible && !hiddenByDiscovery;
        var reasons = new List<string>();
        if (!categoryVisible) reasons.Add("categoryNotVisible");
        if (!parentAllows) reasons.Add("parentFilterDisallows");
        if (specialDisallows) reasons.Add("specialFilterDisallows");
        if (!itemVisible) reasons.Add("itemNotVisible");
        if (hiddenByDiscovery) reasons.Add("undiscoveredItem");
        var actual = new Dictionary<string, object?>
        {
            ["paneEligible"] = true, ["categoryReachable"] = true, ["categoryVisible"] = categoryVisible,
            ["itemVisible"] = itemVisible, ["hiddenByDiscovery"] = hiddenByDiscovery,
            ["parentAllows"] = parentAllows, ["specialFilterDisallows"] = specialDisallows,
            ["visible"] = visible, ["allowed"] = allowed, ["reasons"] = reasons,
            ["context"] = "freshGameNewBill", ["rendered"] = false,
        };
        return new Dictionary<string, object?>
        {
            ["caseId"] = CaseId, ["expected"] = item.Clone(), ["actual"] = actual,
            ["outcome"] = visible == item.GetProperty("visible").GetBoolean()
                && allowed == item.GetProperty("allowed").GetBoolean() ? "match" : "mismatch",
        };
    }

    private static (bool Reachable, bool Visible) Reachable(object root, object thing, object listing, MethodInfo visible)
    {
        bool reachable = false, shown = false;
        int count = 0;
        var path = new HashSet<object>(ReferenceEqualityComparer.Instance);
        Walk(root, true, 0);
        return (reachable, shown);

        void Walk(object node, bool ancestorsVisible, int depth)
        {
            if (depth > 128 || ++count > 20000 || !path.Add(node))
            {
                throw new CaseContextException("categoryTraversalLimit", "cyclic or oversized ingredient category tree");
            }
            object category = Reflect.Member(node, "catDef")!;
            if (Objects(Reflect.Member(category, "SortedChildThingDefs")!).Any(t => ReferenceEquals(t, thing)))
            {
                reachable = true;
                shown |= ancestorsVisible;
            }
            foreach (object child in Objects(Reflect.Member(node, "ChildCategoryNodes")!))
            {
                bool childVisible = (bool)visible.Invoke(listing, [child])!;
                Walk(child, ancestorsVisible && childVisible, depth + 1);
            }
            path.Remove(node);
        }
    }

    private static Dictionary<string, object?> Error(JsonElement item, Exception error)
    {
        while (error is TargetInvocationException { InnerException: { } inner }) error = inner;
        string reason = error is CaseContextException context ? context.Reason
            : error is AdapterMismatchException or MissingMemberException ? "apiUnavailable" : "observationError";
        return new() { ["caseId"] = CaseId, ["expected"] = item.Clone(), ["outcome"] = "error",
            ["reason"] = reason, ["error"] = Diagnostics.TruncateUtf8(error.Message, 16 * 1024) };
    }

    private sealed class CaseContextException(string reason, string message) : Exception(message)
    {
        public string Reason { get; } = reason;
    }
}

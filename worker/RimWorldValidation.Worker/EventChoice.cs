using System.Collections;
using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// One controlled fixture incident. Reward evidence comes from actual item stacks on
/// the generated map before and after selecting the option, not from fixture counters.
/// </summary>
public sealed class EventChoice
{
    public Dictionary<string, object?>? Row { get; private set; }

    private static Dictionary<string, long> ItemStacks(MapApi api, object map)
    {
        object lister = api.MapListerThings.GetValue(map)
            ?? throw new InvalidOperationException("map item lister is unavailable");
        if (api.AllThings.GetValue(lister) is not IEnumerable things)
            throw new InvalidOperationException("map items are unavailable");

        var counts = new Dictionary<string, long>(StringComparer.Ordinal);
        foreach (object thing in things)
        {
            object def = Reflect.Member(thing, "def")!;
            if (Reflect.Member(def, "category")?.ToString() != "Item")
                continue;
            string name = MapStage.DefName(def)
                ?? throw new InvalidOperationException("item has no defName");
            long stackCount = Convert.ToInt64(Reflect.Member(thing, "stackCount"));
            if (stackCount < 0)
                throw new InvalidOperationException("negative item stack count");
            counts[name] = checked(counts.GetValueOrDefault(name) + stackCount);
        }
        return counts;
    }

    public void Observe(JsonElement expectations, MapApi api, object map)
    {
        if (!expectations.TryGetProperty("eventChoices", out JsonElement entries) || entries.GetArrayLength() != 1)
            return;
        JsonElement expected = entries[0].Clone();
        Row = new() { ["caseId"] = "event-choice.v1", ["expected"] = expected };
        try
        {
            Type defType = Reflect.Type("RimWorld.IncidentDef, Assembly-CSharp");
            Type parmsType = Reflect.Type("RimWorld.IncidentParms, Assembly-CSharp");
            object def = api.DefNamed(defType, "RWMT_ChoiceEvent")
                ?? throw new InvalidOperationException("fixture incident not found");
            object worker = Reflect.InstanceProperty(defType, "Worker").GetValue(def)!;
            object parms = Activator.CreateInstance(parmsType)!;
            Reflect.InstanceField(parmsType, "target").SetValue(parms, map);
            Reflect.InstanceField(parmsType, "forced").SetValue(parms, true);
            bool occurred = (bool)Reflect.InstanceMethod(worker.GetType(), "TryExecute", parmsType).Invoke(worker, [parms])!;
            Type fixture = worker.GetType();
            object? option = Reflect.StaticField(fixture, "PendingChoice").GetValue(null);
            bool presented = option != null;

            // The incident may change the map before the option is chosen. Only
            // the change caused by selecting the option counts as its reward.
            Dictionary<string, long> before = ItemStacks(api, map);
            if (option != null)
                Reflect.InstanceMethod(option.GetType(), "Activate").Invoke(option, null);
            Dictionary<string, long> after = ItemStacks(api, map);

            var added = new List<(string Name, long Quantity)>();
            bool removedItems = false;
            foreach ((string name, long count) in before)
                if (after.GetValueOrDefault(name) < count)
                    removedItems = true;
            foreach ((string name, long count) in after)
            {
                long difference = checked(count - before.GetValueOrDefault(name));
                if (difference > 0)
                    added.Add((name, difference));
            }
            bool unambiguous = !removedItems && added.Count <= 1;
            (string Name, long Quantity)? reward = unambiguous && added.Count == 1 ? added[0] : null;
            Row["actual"] = new Dictionary<string, object?>
            {
                ["eventOccurred"] = occurred && (bool)Reflect.StaticField(fixture, "EventOccurred").GetValue(null)!,
                ["choicePresented"] = presented,
                ["choiceExecuted"] = (bool)Reflect.StaticField(fixture, "ChoiceExecuted").GetValue(null)!,
                ["rewardThing"] = reward?.Name,
                ["rewardCount"] = checked((int)(reward?.Quantity ?? 0)),
                ["rewardSource"] = "mapItemStackDelta",
                ["mapDeltaUnambiguous"] = unambiguous,
                ["context"] = "freshGeneratedMap",
                ["rendered"] = false
            };
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            Row["error"] = (error is TargetInvocationException { InnerException: { } inner } ? inner : error).ToString();
        }
    }
}

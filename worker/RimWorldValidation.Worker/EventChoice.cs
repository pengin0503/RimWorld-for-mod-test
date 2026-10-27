using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>One controlled fixture incident; errors never constitute an observation.</summary>
public sealed class EventChoice
{
    public Dictionary<string, object?>? Row { get; private set; }

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
            object def = api.DefNamed(defType, "RWMT_ChoiceEvent") ?? throw new InvalidOperationException("fixture incident not found");
            object worker = Reflect.InstanceProperty(defType, "Worker").GetValue(def)!;
            object parms = Activator.CreateInstance(parmsType)!;
            Reflect.InstanceField(parmsType, "target").SetValue(parms, map);
            Reflect.InstanceField(parmsType, "forced").SetValue(parms, true);
            bool occurred = (bool)Reflect.InstanceMethod(worker.GetType(), "TryExecute", parmsType).Invoke(worker, [parms])!;
            Type fixture = worker.GetType();
            object? option = Reflect.StaticField(fixture, "PendingChoice").GetValue(null);
            bool presented = option != null;
            if (option != null)
                Reflect.InstanceMethod(option.GetType(), "Activate").Invoke(option, null);
            Row["actual"] = new Dictionary<string, object?>
            {
                ["eventOccurred"] = occurred && (bool)Reflect.StaticField(fixture, "EventOccurred").GetValue(null)!,
                ["choicePresented"] = presented,
                ["choiceExecuted"] = (bool)Reflect.StaticField(fixture, "ChoiceExecuted").GetValue(null)!,
                ["rewardThing"] = (string?)Reflect.StaticField(fixture, "RewardThing").GetValue(null),
                ["rewardCount"] = (int)Reflect.StaticField(fixture, "RewardCount").GetValue(null)!,
                ["context"] = "freshGeneratedMap", ["rendered"] = false
            };
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            Row["error"] = (error is TargetInvocationException { InnerException: { } inner } ? inner : error).ToString();
        }
    }
}

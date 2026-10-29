using System.Text.Json;

namespace RimWorldValidation.Worker;

public sealed record TickRequest(int Count, int[] ObserveAt)
{
    public static TickRequest? Load(JsonElement root)
    {
        if (!root.TryGetProperty("tick", out JsonElement value)) return null;
        if (value.ValueKind != JsonValueKind.Object || value.EnumerateObject().Count() != 2
            || !value.TryGetProperty("count", out JsonElement countValue) || !countValue.TryGetInt32(out int count)
            || count < 1 || count > 60000 || !value.TryGetProperty("observeAt", out JsonElement array)
            || array.ValueKind != JsonValueKind.Array || array.GetArrayLength() is < 1 or > 64)
            throw new InvalidDataException("invalid bounded tick request");
        var points = new List<int>();
        foreach (JsonElement item in array.EnumerateArray())
        {
            if (!item.TryGetInt32(out int point) || point < 0 || point > count
                || (points.Count > 0 && point <= points[^1]))
                throw new InvalidDataException("invalid tick observation point");
            points.Add(point);
        }
        if (points[^1] != count) throw new InvalidDataException("final tick observation required");
        return new TickRequest(count, points.ToArray());
    }
}

public sealed record TickObservation(int Tick, int GameTick, Dictionary<string, long> Values);

/// <summary>Bound actual game ticks; frame/loop counts are never arrival evidence.</summary>
public sealed class BoundedTickRunner(int count, int[] points)
{
    private readonly List<TickObservation> _observations = [];
    private readonly object _gate = new();
    public IReadOnlyList<TickObservation> Observations { get { lock (_gate) return _observations.ToArray(); } }
    public string Status { get; private set; } = "incomplete";
    public int StartTick { get; private set; }
    public int EndTick { get; private set; }
    public int Advanced => EndTick - StartTick;
    public string? Error { get; private set; }

    public void Run(Func<int> readTick, Action singleTick, Func<long> readProbe, Func<bool> shouldStop, Action? checkpoint = null)
    {
        try
        {
            StartTick = EndTick = readTick();
            if (StartTick < 0 || (long)StartTick + count > int.MaxValue)
                throw new InvalidOperationException("unsupported game tick range");
            int pointIndex = 0;
            void Observe(int relative)
            {
                long value = readProbe();
                lock (_gate) _observations.Add(new TickObservation(relative, EndTick,
                    new Dictionary<string, long> { ["fixture.counter"] = value }));
                checkpoint?.Invoke();
            }
            if (points[0] == 0) { Observe(0); pointIndex++; }
            while (Advanced < count)
            {
                if (shouldStop()) throw new OperationCanceledException("tick deadline or termination reached");
                int before = readTick();
                if (before != EndTick) throw new InvalidOperationException("game tick changed outside the bounded step");
                singleTick();
                EndTick = readTick();
                if ((long)EndTick - before != 1) throw new InvalidOperationException("single tick did not advance exactly one game tick");
                if (pointIndex < points.Length && Advanced == points[pointIndex])
                {
                    Observe(Advanced);
                    pointIndex++;
                }
            }
            if (pointIndex != points.Length || readTick() != EndTick)
                throw new InvalidOperationException("tick observation sequence incomplete");
            Status = "completed";
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            try { EndTick = readTick(); } catch (Exception readError) when (readError is not OutOfMemoryException) { /* previous confirmed tick retained */ }
            Error = error.GetType().Name + ": " + error.Message;
            Status = "incomplete";
        }
    }

    public Dictionary<string, object?> Evidence(string? initialization)
    {
        // Copy under the same lock used by the writer; the watchdog never reads game objects.
        lock (_gate) return new()
        {
            ["caseId"] = "bounded-tick.v1", ["observerVersion"] = 1, ["status"] = Status,
            ["initialization"] = initialization, ["startTick"] = StartTick, ["endTick"] = EndTick,
            ["advanced"] = Advanced, ["error"] = Error,
            ["observations"] = _observations.Select(o => new Dictionary<string, object>
            {
                ["tick"] = o.Tick, ["gameTick"] = o.GameTick, ["values"] = o.Values
            }).ToArray()
        };
    }
}

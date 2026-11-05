using System.Collections.Generic;

namespace RimWorldValidation.Worker;

/// <summary>Experimental D v2: selected, fixed-name runtime observers, never log warnings.</summary>
public sealed class BoundedTickRunnerV2
{
    private static readonly HashSet<string> Allowed = ["fixture.counter", "game.tick"];
    private readonly int _count;
    private readonly int[] _points;
    private readonly string[] _ids;
    private readonly List<TickObservation> _observations = [];
    private readonly object _gate = new();

    public BoundedTickRunnerV2(int count, int[] points, string[] observers)
    {
        if (count is < 1 or > 60000 || points is null || points.Length is < 1 or > 64
            || observers is null || observers.Length is < 1 or > 2
            || points[^1] != count || points[0] < 0)
            throw new ArgumentException("invalid bounded D v2 configuration");
        for (int i = 1; i < points.Length; i++)
            if (points[i] <= points[i-1] || points[i] > count)
                throw new ArgumentException("unsorted or invalid observation points");
        if (observers.Any(id => !Allowed.Contains(id))
            || !observers.SequenceEqual(observers.OrderBy(id => id, StringComparer.Ordinal).Distinct()))
            throw new ArgumentException("unregistered or duplicate observer ID");
        _count = count;
        _points = (int[])points.Clone();
        _ids = (string[])observers.Clone();
    }

    public IReadOnlyList<TickObservation> Observations
    {
        get { lock (_gate) return _observations.ToArray(); }
    }
    public string Status { get; private set; } = "incomplete";
    public int StartTick { get; private set; }
    public int EndTick { get; private set; }
    public int Advanced => EndTick - StartTick;
    public string? Error { get; private set; }

    public void Run(Func<int> readTick, Action singleTick,
        Func<IReadOnlyDictionary<string, long>> readObservers,
        Func<bool> shouldStop, Action? checkpoint = null)
    {
        try
        {
            StartTick = EndTick = readTick();
            if (StartTick < 0 || (long)StartTick + _count > int.MaxValue)
                throw new InvalidOperationException("unsupported game tick range");
            int index = 0;
            void Observe(int relative)
            {
                IReadOnlyDictionary<string, long> source = readObservers()
                    ?? throw new InvalidOperationException("observation source missing");
                if (source.Count != _ids.Length ||
                    _ids.Any(id => !source.ContainsKey(id)))
                    throw new InvalidOperationException("missing or unregistered observer value");
                var values = new Dictionary<string, long>(source.Count, StringComparer.Ordinal);
                foreach (string id in _ids)
                    values.Add(id, source[id]);
                lock (_gate)
                    _observations.Add(new TickObservation(relative, EndTick, values));
                checkpoint?.Invoke();
            }
            if (_points[0] == 0) { Observe(0); index++; }
            while (Advanced < _count)
            {
                if (shouldStop()) throw new OperationCanceledException("tick deadline reached");
                int before = readTick();
                if (before != EndTick)
                    throw new InvalidOperationException("game tick changed outside the bounded step");
                singleTick();
                EndTick = readTick();
                if ((long)EndTick - before != 1)
                    throw new InvalidOperationException("one step did not advance exactly one tick");
                if (index < _points.Length && Advanced == _points[index])
                {
                    Observe(Advanced);
                    index++;
                }
            }
            if (index != _points.Length || readTick() != EndTick)
                throw new InvalidOperationException("observation sequence incomplete");
            Status = "completed";
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            try { EndTick = readTick(); }
            catch (Exception readError) when (readError is not OutOfMemoryException) { /* last confirmed tick */ }
            Error = error.GetType().Name + ": " + error.Message;
            Status = "incomplete";
        }
    }

    public Dictionary<string, object?> Evidence(string? initialization)
    {
        lock (_gate)
            return new()
            {
                ["caseId"] = "bounded-tick.v2", ["observerVersion"] = 2,
                ["status"] = Status, ["initialization"] = initialization,
                ["startTick"] = StartTick, ["endTick"] = EndTick, ["advanced"] = Advanced,
                ["error"] = Error,
                ["observations"] = _observations.Select(o => new Dictionary<string, object>
                {
                    ["tick"] = o.Tick, ["gameTick"] = o.GameTick, ["values"] = o.Values
                }).ToArray()
            };
    }
}

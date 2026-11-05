using RimWorldValidation.Worker;

static void Check(bool value, string message) { if (!value) throw new Exception(message); }
foreach (int count in new[] { 60, 600 })
{
    int tick = 1234, calls = 0;
    long state = 0;
    var points = count == 60 ? new[] { 0, 60 } : new[] { 0, 60, 600 };
    var runner = new BoundedTickRunner(count, points);
    var snapshots = new List<int>();
    runner.Run(() => tick, () => { calls++; tick++; state++; }, () => state, () => false, () => snapshots.Add(runner.Advanced));
    Check(snapshots.SequenceEqual(points), "checkpoint each observation before further ticks");
    Check(runner.Status == "completed", "complete");
    Check(calls == count && tick == 1234 + count && runner.Advanced == count, "no extra tick");
    Check(runner.Observations.Select(x => x.Tick).SequenceEqual(points), "ordered points");
    Check(runner.Observations[0].Values["fixture.counter"] == 0, "tick zero precedes first step");
    Check(runner.Observations[^1].Values["fixture.counter"] == count, "independent state");
}
foreach (string mode in new[] { "frozen", "jump", "throw", "deadline", "probeMissing" })
{
    int tick = 100, calls = 0;
    var runner = new BoundedTickRunner(600, new[] { 0, 60, 600 });
    runner.Run(() => tick, () => {
        calls++;
        if (mode == "throw" && calls == 61) throw new InvalidOperationException("fixture failure");
        tick += mode == "frozen" ? 0 : mode == "jump" ? 2 : 1;
    }, () => mode == "probeMissing" ? throw new InvalidOperationException("missing probe") : calls,
       () => mode == "deadline" && calls >= 60);
    Check(runner.Status == "incomplete" && runner.Error != null, mode + " must not complete");
    Check(calls < 600, mode + " must stop");
    if (mode is "throw" or "deadline")
        Check(runner.Observations.Count == 2 && runner.Observations[^1].Tick == 60, "partial evidence retained");
}
{
    int tick = 1000;
    var runner = new BoundedTickRunnerV2(60, [0, 60], ["game.tick"]);
    runner.Run(() => tick, () => tick++,
        () => new Dictionary<string, long> { ["game.tick"] = tick },
        () => false);
    Check(runner.Status == "completed" && runner.Advanced == 60, "v2 trusted game tick");
    Check(runner.Observations.Count == 2, "v2 observation count");
    Check(runner.Observations[0].Values["game.tick"] == 1000, "v2 tick zero");
    Check(runner.Observations[1].Values["game.tick"] == 1060, "v2 current game tick");
    var evidence = runner.Evidence("gameFinalizeInitAndStartedNewGame");
    Check((string?)evidence["caseId"] == "bounded-tick.v2"
          && (int?)evidence["observerVersion"] == 2, "v2 identity");
}
{
    int tick = 1000;
    var runner = new BoundedTickRunnerV2(60, [0, 60], ["game.tick"]);
    runner.Run(() => tick, () => tick++,
        () => new Dictionary<string, long> { ["game.tick"] = tick, ["extra"] = 123 },
        () => false);
    Check(runner.Status == "incomplete" && runner.Error != null, "v2 extra evidence fails closed");
}
Console.WriteLine("bounded tick synthetic: 9 cases passed");

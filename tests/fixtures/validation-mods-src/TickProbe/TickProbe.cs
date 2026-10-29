using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Verse;

namespace RWMT.TickProbe
{
    // The game calls this component; the host never increments its state.
    public sealed class TickProbeConfigDef : Def { public string mode = "normal"; }

    public sealed class TickProbeComponent : GameComponent
    {
        public long Counter;
        public bool Started;
        public TickProbeComponent(Game game) { }
        public override void StartedNewGame() { Counter = 0; Started = true; }
        private readonly List<byte[]> memory = new List<byte[]>();
        public override void GameComponentTick()
        {
            if (LongEventHandler.AnyEventNowOrWaiting)
                throw new InvalidOperationException("RWMT tick executed before long events drained");
            if (Counter == 60)
            {
                string mode = DefDatabase<TickProbeConfigDef>.GetNamedSilentFail("RWMT_TickConfig")?.mode;
                if (mode == "hang" || mode == "memory" || mode == "log")
                {
                    Process child = Process.Start(new ProcessStartInfo("/bin/sleep", "600") { UseShellExecute = false });
                    File.WriteAllText(Path.Combine(Environment.GetEnvironmentVariable("HOME"), "tick-probe-child.pid"), child.Id.ToString());
                }
                if (mode == "throw") throw new InvalidOperationException("RWMT controlled tick exception");
                if (mode == "hang") while (true) Thread.Sleep(100);
                if (mode == "memory")
                {
                    for (int n = 0; n < 256; n++)
                    {
                        byte[] block = new byte[4 * 1024 * 1024];
                        for (int i = 0; i < block.Length; i += 4096) block[i] = 1;
                        memory.Add(block);
                        Thread.Sleep(10);
                    }
                }
                if (mode == "log")
                {
                    for (int n = 0; n < 4096; n++) Console.WriteLine(new string('X', 1024));
                    Thread.Sleep(5000); // allow the polled log bound to terminate the process
                }
            }
            Counter++;
        }
    }
}

using Prepatcher;
using Verse;

namespace RWMT.PrepatcherField
{
    // A field added to Verse.Def the way Prepatcher-based mods do it: an extern ref
    // accessor marked [PrepatcherField]. RimWorld 1.7.5014 gives such accessors a real
    // field when the mod's assembly loads (RimWorldWaylith.PrepatcherCompat); a host
    // that skips that boot step fails when the accessor is called.
    public static class InjectedFields
    {
        [PrepatcherField]
        [Prepatcher.DefaultValue(7)]
        public static extern ref int RwmtCounter(this Def def);
    }

    [StaticConstructorOnStartup]
    public static class PrepatcherFieldProbe
    {
        static PrepatcherFieldProbe()
        {
            ThingDef steel = DefDatabase<ThingDef>.GetNamed("Steel");
            ThingDef wood = DefDatabase<ThingDef>.GetNamed("WoodLog");
            int initial = steel.RwmtCounter();
            steel.RwmtCounter() = 42;
            Log.Message($"[RWMT-PROBE] prepatcher field initial={initial} steel={steel.RwmtCounter()} wood={wood.RwmtCounter()}");
        }
    }
}

using System;
using RimWorld;
using Verse;

namespace RWMT.EventChoice
{
    // Self-made fixture: the game's incident entry point creates one real dialog option.
    public class ChoiceIncident : IncidentWorker
    {
        public static DiaOption PendingChoice;
        public static int RewardCount;
        public static string RewardThing;

        public static bool EventOccurred;
        public static bool ChoiceExecuted;

        protected override bool TryExecuteWorker(IncidentParms parms)
        {
            EventOccurred = true;
            RewardCount = 0;
            ChoiceExecuted = false;
            Map map = parms.target as Map;
            if (map == null) return false;
            PendingChoice = new DiaOption("accept")
            {
                action = () =>
                {
                    Thing reward = ThingMaker.MakeThing(ThingDefOf.Steel);
                    reward.stackCount = 10;
                    Thing spawned = GenSpawn.Spawn(reward, CellFinder.RandomClosewalkCellNear(map.Center, map, 5), map);
                    RewardCount = spawned.stackCount;
                    RewardThing = spawned.def.defName;
                    ChoiceExecuted = true;
                }
            };
            return true;
        }
    }
}

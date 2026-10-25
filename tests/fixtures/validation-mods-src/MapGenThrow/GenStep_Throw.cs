using System;
using Verse;

namespace RWMT.MapGenThrow
{
    // A broken gen step: loading succeeds, generating the map logs the game's
    // "Error in GenStep" error for it.
    public class GenStep_Throw : GenStep
    {
        public override int SeedPart => 0x52574D54;

        public override void Generate(Map map, GenStepParams parms)
        {
            throw new InvalidOperationException("RWMT_ThrowingGenStep failed on purpose");
        }
    }
}

using System;
using Verse;

namespace RWMT.InitThrow
{
    public class InitThrowMod : Mod
    {
        public InitThrowMod(ModContentPack content) : base(content)
        {
            throw new InvalidOperationException("RWMT fixture: intentional failure in Mod constructor");
        }
    }
}

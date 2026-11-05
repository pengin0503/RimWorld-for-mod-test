# DPA CSV exporter Harmony argument binding regression (2026-11-05)

## Observed discrepancy

The user-authored addon source integrated into main by PR #64 patches `Analyzer.Window_Analyzer.DoWindowContents` with `DrawExportButton(Rect rect)`. The upstream Dubs Performance Analyzer 1.7 `Source/Window_Analyzer.cs` declares `DoWindowContents(Rect inRect)`. Harmony matches ordinary postfix parameters to the original *by name*; positional injection `Rect __0` avoids coupling to that name.

References:
- https://github.com/Dubwise56/Dubs-Performance-Analyzer/blob/develop/Source/Window_Analyzer.cs
- https://github.com/pardeike/Harmony/blob/master/Documentation/articles/patching-injections.md

This mismatch can prevent the patch from being installed, removing the exporter button. Previous public CI tested CSV formatting only; it could not catch the failure.

## Scope

1. Change only the postfix's injected Rect argument to `Rect __0` and use it for button placement. Preserve other gameplay and exporter behavior.
2. Add a synthetic, game-free .NET 10 integration runner that includes the actual `Source/ModEntry.cs`, `Source/Exporter.cs` and `Source/CsvFormat.cs` and exercises *real Harmony* patch injection against a fake `Analyzer.Window_Analyzer.DoWindowContents(Rect inRect)` method. The fake Verse/RimWorld/DPA types exist only in the test project, not in production.
3. In the synthetic runner, activate the addon as a normal Mod, verify the patch owner is installed, trigger the fake window draw, and inspect the CSV output from seeded synthetic DPA logs (BOM, header, rows, numeric counts and untrusted formula label escaping). Validate at least one exported success message.
4. Add the test to existing GUI-model OS matrix in `.github/workflows/offline-audit.yml`, retain existing public CI.
5. Do not fetch or distribute game DLLs, MOD binaries, actual R2 data or DPA third-party sources. Never claim full DPA GUI or RimWorld runtime qualification from this synthetic test.

## Acceptance

Before modifying `ModEntry.cs`, run new CI test and observe a failure specifically due to the wrongly named `rect` argument. After the fix, the exact new test and entire public CI matrix must pass. Keep existing branch heads, main and qualification adapters untouched; leave the PR unmerged pending explicit approval, per AGENTS.md.

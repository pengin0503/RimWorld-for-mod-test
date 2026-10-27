# DPA CSV Exporter (RimWorld 1.7)

Adds an **Export CSV** button to Dubs Performance Analyzer and a backup button in Options → Mod Settings → DPA CSV Exporter.

## Purpose

Export **every row in the currently selected profiler entry** (Tick/Update/GUI/etc), including the rows hidden by an on-screen search filter, without copying the Analyzer window's table manually. It does not start extra measurements or change the game rules.

A profile is the currently selected DPA measurement entry. DPA does not measure every entry/category simultaneously; export again after selecting another entry to compare them.

## Install the packaged version

1. Enable Harmony and Dubs Performance Analyzer compatible with RimWorld 1.7.
2. Unpack `DPA-CSV-Exporter-1.0.0-RW1.7.zip` into your local RimWorld `Mods` directory.
3. Load order: Harmony → Dubs Performance Analyzer → DPA CSV Exporter.
4. Open the Dubs window, select a profiling entry, and let results accumulate.
5. Click **Export CSV** at the top right of the analyzer window (or from this mod's settings).

CSV output: `GenFilePaths.SaveDataFolderPath/AnalyzerExports` (typically `%USERPROFILE%\\AppData\\LocalLow\\Ludeon Studios\\RimWorld by Ludeon Studios\\AnalyzerExports` on Windows).

## Fields

29 columns including category, entry, FPS/TPS, profiler root time, method/key/label, best-effort MOD name and assembly, avg/self/max/total milliseconds, calls, fraction of root, spike counts, and phase flags.

Files are UTF-8 with BOM for Excel, formula-injection mitigated for textual fields, decimal points use invariant culture. Every export receives a timestamp and random suffix.

## Building / verification

The source targets .NET 10 and uses Harmony 3 from NuGet for compilation. It requires **RimWorld 1.7** `Assembly-CSharp.dll`, `UnityStubs.dll`, and `Waylith.dll` as compile-time references (never committed or distributed).

```sh
dotnet run --project Tests/CsvSmokeTest.csproj -c Release
dotnet build Source/DPA.CsvExporter.csproj -c Release -p:RimWorldRefs=/path/to/private/references
```

In the `RimWorld-for-mod-test` repo, the separate lightweight build workflow fetches exactly those three DLLs from private Cloudflare R2 and publishes **only the independently authored compiled addon** as an Action artifact. The old full-game preflight is neither required for building nor a release gate.

A successful compilation or headless A loader check does **not** prove the on-screen button works. That requires a normal Windows game session. This addon does not use undocumented public distribution of the game's proprietary DLLs.

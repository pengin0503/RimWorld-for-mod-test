# DPA CSV Exporter — historical self-authored optional addon

**Status:** Source-only integration from `feat/dpa-csv-exporter-private-validation-20261027`. The author field identifies `pengin0503`. This is an independent user addon for the Dubs Performance Analyzer, **not a qualified test-host component**, and no compiled MOD, third-party source, game assembly, or Workshop payload is distributed here.

The experimental addon adds an Export CSV button to the DPA window and a fallback button to its own MOD settings. It attempts to export the entire selected DPA profiler log (including rows hidden by search), and does not perform additional measurements. The exported CSV uses UTF-8 with BOM, invariant numeric culture, and basic spreadsheet-formula injection mitigation.

## Isolated serializer regression tests (no game needed)

```bash
dotnet run --project addons/DPA-CSV-Exporter/Tests/CsvSmokeTest.csproj -c Release
```

These tests run in public GitHub Actions on Linux and Windows. They cover **CSV formatting only**. They do not validate exporter reflection, the DPA API at runtime, Harmony patch application, UI integration, full file output, or actual RimWorld behavior.

## Local build — private game reference assemblies required

```bash
dotnet build addons/DPA-CSV-Exporter/Source/DPA.CsvExporter.csproj -c Release -p:RimWorldRefs=/your/private/rimworld-1.7/references
```

This requires the owner's legitimately acquired RimWorld 1.7 `Assembly-CSharp.dll`, `UnityStubs.dll`, and `Waylith.dll`. It references Harmony 3 through NuGet, and has not been qualified against a specific DPA runtime version in this integration. Those DLLs must never be committed or uploaded to public CI.

**Do not install or distribute this from this repository as a working release without completing actual A/B runtime checks and in-game UI verification.** Earlier historical private-preflight workflow was blocked by unavailable secrets, and its old branch-specific workflow has not been carried into main.

The historical branch and exact reviewed SHA are recorded in [the residual branch disposition report](../../docs/research/2026-11-05-residual-branch-consolidation.md).

// Synthetic stand-ins for the public, game-independent Harmony/CSV contract test.
// These are NOT RimWorld/DPA runtime implementations and must never ship with the addon.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using UnityEngine;

namespace UnityEngine
{
    public readonly struct Rect
    {
        public readonly float x, y, width, height;
        public float xMax => x + width;
        public Rect(float x, float y, float width, float height)
        {
            this.x = x; this.y = y; this.width = width; this.height = height;
        }
        public Rect ContractedBy(float margin)
            => new(x + margin, y + margin, width - 2f * margin, height - 2f * margin);
    }
}

namespace Verse
{
    public class ModContentPack
    {
        public string Name => "synthetic";
        public AssemblyHolder assemblies { get; } = new();
    }
    public class AssemblyHolder
    {
        public List<Assembly> loadedAssemblies { get; } = new();
    }
    public class Mod
    {
        public Mod(ModContentPack content) { }
        public virtual string SettingsCategory() => string.Empty;
        public virtual void DoSettingsWindowContents(Rect rect) { }
    }
    public static class LoadedModManager
    {
        public static List<ModContentPack> RunningMods { get; } = new();
    }
    public static class GenFilePaths
    {
        public static string SaveDataFolderPath { get; set; } = "";
    }
    public static class LongEventHandler
    {
        public static void ExecuteWhenFinished(Action callback) => callback();
    }
    public static class Log
    {
        public static List<string> Errors { get; } = new();
        public static void Message(string value) { }
        public static void Warning(string value) => Errors.Add(value);
        public static void Error(string value) => Errors.Add(value);
        public static void ErrorOnce(string value, int key) => Errors.Add(value);
    }
    public static class Widgets
    {
        public static int ClickCount { get; private set; }
        public static void Label(Rect rect, string value) { }
        public static bool ButtonText(Rect rect, string label)
        {
            if (label != "Export CSV") return false;
            ClickCount++;
            return true;
        }
    }
}

namespace RimWorld
{
    public static class MessageTypeDefOf
    {
        public static object TaskCompletion { get; } = new();
        public static object RejectInput { get; } = new();
    }
    public static class Messages
    {
        public static List<string> Notifications { get; } = new();
        public static void Message(string text, object messageType, bool historical)
            => Notifications.Add(text);
    }
}

namespace Analyzer
{
    public static class ModInfoCache
    {
        public static Dictionary<string, string> AssemblyToModname { get; } = new();
    }
    public class Window_Analyzer
    {
        public int Calls { get; private set; }
        // The real DPA 1.7 method has the name inRect, NOT rect.
        [MethodImpl(MethodImplOptions.NoInlining)]
        public void DoWindowContents(Rect inRect) => Calls++;
    }
}

namespace Analyzer.Profiling
{
    public enum Category { Tick, Settings }
    public class Entry { public string name = "Synthetic Tick"; }
    public class ProfileLog
    {
        public int entries = 2, spikes = 0, spike = 0, seenIn = 3;
        public float percent = 0.5f, max = 2.5f, total = 4.0f, calls = 2f;
        public double average = 1.5, self = 0.5;
        public string key = "synthetic", label = "=2+2";
        public Type type = typeof(ProfileLog);
        public MethodBase? meth = typeof(object).GetMethod(nameof(ToString));
        public bool pinned;
    }
    public static class GUIController
    {
        public static Entry CurrentEntry { get; } = new();
        public static Category CurrentCategory => Category.Tick;
    }
    public static class Analyzer
    {
        public static object LogicLock { get; } = new();
        public static List<ProfileLog> Logs { get; } = new();
        public static int GetCurrentLogCount => 7;
    }
    public static class ProfileController
    {
        public static float updateAverage = 1.25f;
    }
    public static class Panel_TopRow
    {
        public static int fps = 85, tps = 180, tpsTarget = 360;
        public static string TimesFilter = "=unsafe";
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using HarmonyLib;
using RimWorld;
using Verse;

namespace RWMT.CRendered
{
    // Development-only observer for a *rendering* official process (never the product).
    // It opens the real bill dialog through the real WindowStack while the official process
    // sits at the Entry state, and records which ingredient rows the dialog's own code listed
    // during the real OnGUI passes that the engine delivers. It never synthesizes input
    // events, never calls the ingredient pane directly, never replaces a visibility predicate,
    // never changes tree open state and never starts or ticks a game.
    public class ConfigDef : Def
    {
        public bool official;
        public List<string> recipes = new List<string>();
        public List<string> things = new List<string>();
    }

    public class ProbeMod : Mod
    {
        public ProbeMod(ModContentPack content) : base(content)
        {
            var harmony = new Harmony("rwmodtest.crendered");
            // Drive from the start of each root GUI pass: window functions registered in the
            // previous pass have all run by then, so closing a dialog or restoring Current.Game
            // here can never strand a pending window of the same event.
            harmony.Patch(AccessTools.Method(typeof(UIRoot_Entry), nameof(UIRoot_Entry.UIRootOnGUI)),
                prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.BeforeRootOnGUI)));
            harmony.Patch(AccessTools.Method(typeof(Dialog_BillConfig), nameof(Dialog_BillConfig.DoWindowContents)),
                prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.ContentsPrefix)));
            harmony.Patch(AccessTools.Method(typeof(Dialog_BillConfig), "DoIngredientConfigPane",
                    new[] { typeof(float), typeof(float).MakeByRefType(), typeof(float), typeof(float) }),
                prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.PanePrefix)),
                finalizer: new HarmonyMethod(typeof(Observer), nameof(Observer.PaneFinalizer)));
            harmony.Patch(AccessTools.GetDeclaredMethods(typeof(ThingFilterUI)).Single(m => m.Name == "DoThingFilterConfigWindow"),
                prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.UiPrefix)));
            harmony.Patch(AccessTools.GetDeclaredConstructors(typeof(Listing_TreeThingFilter)).Single(c => c.GetParameters().Length == 6),
                prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.ListingPrefix)));
            var row = AccessTools.Method(typeof(Listing_TreeThingFilter), "DoThingDef", new[] { typeof(ThingDef), typeof(int), typeof(Map) });
            if (row == null) throw new MissingMethodException("Listing_TreeThingFilter.DoThingDef(ThingDef,int,Map)");
            harmony.Patch(row, prefix: new HarmonyMethod(typeof(Observer), nameof(Observer.RowPrefix)));
        }
    }

    internal sealed class CaseRecord
    {
        public string recipe;
        public string setup = "notStarted";
        public bool opened, openedOnMainThread, freshGameKept = true;
        public int openEventType = -1, windowsBeforeOpen, otherDialogsBeforeOpen, repaintsWhileOpen;
        public readonly SortedDictionary<int, int> contents = new SortedDictionary<int, int>();
        public readonly SortedDictionary<int, int> pane = new SortedDictionary<int, int>();
        public int ui, listing, paneRepaints;
        public readonly SortedDictionary<string, SortedSet<int>> listed = new SortedDictionary<string, SortedSet<int>>();
        public readonly HashSet<string> anyRow = new HashSet<string>();
        public readonly SortedDictionary<string, bool> allowed = new SortedDictionary<string, bool>();
        public bool exception, removed;
        public string exceptionKind = "none";
    }

    public static class Observer
    {
        private const int Repaint = 7;
        private const int IdleRepaintsBeforeOpen = 30, RepaintsPerCase = 3, MaxRepaintsPerCase = 600, MaxRepaints = 20000;
        // Keep each dialog on screen long enough for the private external screen capture.
        private const double MinOpenSeconds = 6, MaxOpenSeconds = 120;
        private static readonly System.Diagnostics.Stopwatch openClock = new System.Diagnostics.Stopwatch();
        private static readonly PropertyInfo CurrentEvent = AccessTools.Property(AccessTools.TypeByName("UnityEngine.Event"), "current");
        private static PropertyInfo eventType;
        // 0 waiting for an idle Entry state, 1 a dialog is open, 3 draining after the last close, 2 finished.
        private static int phase, idleRepaints, openRepaints, totalRepaints, recipeIndex, drainRepaints, lateContents;
        // A closed dialog's window function may still run for a pass that was registered before
        // it was removed. Keep the fresh Game current until such passes are over, and count them.
        private const int DrainRepaints = 5;
        private static readonly HashSet<Dialog_BillConfig> closed = new HashSet<Dialog_BillConfig>();
        private static Game previousGame, freshGame;
        private static Dialog_BillConfig dialog;
        private static Bill_Production bill;
        private static CaseRecord current;
        private static bool inPane;
        private static readonly List<CaseRecord> done = new List<CaseRecord>();

        private static ConfigDef Config => DefDatabase<ConfigDef>.GetNamedSilentFail("RWMT_CRendered");

        private static int EventType()
        {
            object e = CurrentEvent?.GetValue(null);
            if (e == null) return -1;
            eventType ??= AccessTools.Property(e.GetType(), "type");
            return Convert.ToInt32(eventType.GetValue(e));
        }

        private static void Count(SortedDictionary<int, int> counts, int type)
        {
            counts.TryGetValue(type, out int n);
            counts[type] = n + 1;
        }

        public static void BeforeRootOnGUI()
        {
            if (phase == 2) return;
            ConfigDef config = Config;
            if (config == null || !config.official) return;
            if (EventType() != Repaint) return;
            if (++totalRepaints > MaxRepaints) { Finish("frameLimit"); return; }
            if (phase == 0)
            {
                if (LongEventHandler.AnyEventNowOrWaiting || Current.ProgramState != ProgramState.Entry) { idleRepaints = 0; return; }
                if (++idleRepaints < IdleRepaintsBeforeOpen) return;
                previousGame = Current.Game;
                // Same context as the product case: a fresh Game that is never started or ticked.
                freshGame = new Game();
                Current.Game = freshGame;
                phase = 1;
                OpenNext(config);
                return;
            }
            if (phase == 3)
            {
                if (++drainRepaints >= DrainRepaints) Finish(null);
                return;
            }
            current.repaintsWhileOpen++;
            if (!ReferenceEquals(Current.Game, freshGame)) current.freshGameKept = false;
            bool enough = current.paneRepaints >= RepaintsPerCase && openClock.Elapsed.TotalSeconds >= MinOpenSeconds;
            if (enough || current.exception || ++openRepaints > MaxRepaintsPerCase || openClock.Elapsed.TotalSeconds > MaxOpenSeconds)
            {
                CloseCurrent(config);
                OpenNext(config);
            }
        }

        private static void OpenNext(ConfigDef config)
        {
            while (recipeIndex < config.recipes.Count)
            {
                current = new CaseRecord { recipe = config.recipes[recipeIndex] };
                RecipeDef recipe = DefDatabase<RecipeDef>.GetNamedSilentFail(current.recipe);
                if (recipe == null) { current.setup = "defMissing"; done.Add(current); recipeIndex++; continue; }
                try
                {
                    bill = BillUtility.MakeNewBill(recipe, null) as Bill_Production;
                    if (bill == null) { current.setup = "notProductionBill"; done.Add(current); recipeIndex++; continue; }
                    current.setup = "dialog";
                    dialog = new Dialog_BillConfig(bill, IntVec3.Invalid);
                    current.openEventType = EventType();
                    current.openedOnMainThread = UnityData.IsInMainThread;
                    current.windowsBeforeOpen = Find.WindowStack.Count;
                    current.otherDialogsBeforeOpen = Find.WindowStack.Windows.Count(w => w.layer == WindowLayer.Dialog);
                    Find.WindowStack.Add(dialog);
                    current.opened = Find.WindowStack.IsOpen(dialog);
                    current.setup = current.opened ? "open" : "notOpened";
                }
                catch (Exception error)
                {
                    current.setup = "openFailed";
                    current.exception = true;
                    current.exceptionKind = Classify(error);
                    Log.Message("[RWMT-RENDERED-PRIVATE] " + error);
                }
                if (!current.opened) { done.Add(current); dialog = null; bill = null; recipeIndex++; continue; }
                openRepaints = 0;
                openClock.Restart();
                return;
            }
            current = null;
            phase = 3;
        }

        private static void CloseCurrent(ConfigDef config)
        {
            foreach (string name in config.things)
            {
                ThingDef def = DefDatabase<ThingDef>.GetNamedSilentFail(name);
                if (def != null) current.allowed[name] = bill.ingredientFilter.Allows(def);
            }
            current.removed = Find.WindowStack.TryRemove(dialog, doCloseSound: false);
            closed.Add(dialog);
            done.Add(current);
            dialog = null; bill = null; current = null; inPane = false;
            recipeIndex++;
        }

        private static void Finish(string stop)
        {
            if (phase == 2) return;
            phase = 2;
            if (current != null && !done.Contains(current)) done.Add(current);
            if (dialog != null) Find.WindowStack.TryRemove(dialog, doCloseSound: false);
            if (freshGame != null) Current.Game = previousGame;
            ConfigDef config = Config;
            var cases = done.Select(c => new
            {
                c.recipe, c.setup, c.opened, c.openedOnMainThread, c.openEventType, c.windowsBeforeOpen,
                c.otherDialogsBeforeOpen, c.repaintsWhileOpen, c.freshGameKept, c.removed,
                contents = c.contents.ToDictionary(p => p.Key.ToString(), p => p.Value),
                pane = c.pane.ToDictionary(p => p.Key.ToString(), p => p.Value),
                c.ui, c.listing, c.paneRepaints, rowCount = c.anyRow.Count,
                listed = config.things.ToDictionary(t => t, t => c.listed.TryGetValue(t, out var types) ? types.ToArray() : new int[0]),
                allowed = c.allowed, c.exception, c.exceptionKind,
            }).ToList();
            Log.Message("[RWMT-RENDERED] " + JsonSerializer.Serialize(new { phase = "rendered", stop = stop ?? "none", totalRepaints,
                drainRepaints, lateContents, cases }));
            AccessTools.Method(AccessTools.TypeByName("UnityEngine.Application"), "Quit", Type.EmptyTypes).Invoke(null, null);
        }

        private static string Classify(Exception error)
        {
            Exception cause = error;
            for (int n = 0; n < 8 && cause is TargetInvocationException && cause.InnerException != null; n++) cause = cause.InnerException;
            return cause is MissingMemberException ? "missingApi" : cause is TypeInitializationException ? "typeInitialization"
                : cause is NullReferenceException ? "nullReference" : "runtimeOther";
        }

        public static void ContentsPrefix(Dialog_BillConfig __instance)
        {
            if (closed.Contains(__instance)) lateContents++;
            else if (current != null && ReferenceEquals(__instance, dialog)) Count(current.contents, EventType());
        }

        public static void PanePrefix(Dialog_BillConfig __instance)
        {
            if (current == null || !ReferenceEquals(__instance, dialog)) return;
            inPane = true;
            int type = EventType();
            Count(current.pane, type);
            if (type == Repaint) current.paneRepaints++;
        }

        public static Exception PaneFinalizer(Dialog_BillConfig __instance, Exception __exception)
        {
            if (current != null && ReferenceEquals(__instance, dialog))
            {
                inPane = false;
                if (__exception != null && !current.exception)
                {
                    current.exception = true;
                    current.exceptionKind = Classify(__exception);
                    Log.Message("[RWMT-RENDERED-PRIVATE] " + __exception);
                }
            }
            return __exception;
        }

        public static void UiPrefix() { if (inPane) current.ui++; }
        public static void ListingPrefix() { if (inPane) current.listing++; }

        public static void RowPrefix(object[] __args)
        {
            if (!inPane || __args.Length == 0 || !(__args[0] is ThingDef def)) return;
            if (current.anyRow.Count < 20000) current.anyRow.Add(def.defName);
            if (!current.listed.TryGetValue(def.defName, out SortedSet<int> types))
                current.listed[def.defName] = types = new SortedSet<int>();
            types.Add(EventType());
        }
    }
}

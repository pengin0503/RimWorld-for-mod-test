using System.Reflection;
using RimWorld;
using UnityEngine;
using Verse;
using Verse.Sound;

namespace RimWorldValidation.Gui;

/// <summary>
/// The validation scene's root, in place of the game's Root_Entry. It does the
/// game's global start-up (Root.Start/CheckGlobalInit) without Steam and
/// without a main menu, loads the official content, then shows the GUI.
/// </summary>
public sealed class ValidationRoot : Root
{
    private const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
    private ScriptRunner? _script;
    private bool _prefsLoaded;

    /// <summary>True once the official content is loaded and the GUI is drawn.</summary>
    public static bool Ready => Current.Root is ValidationRoot { uiRoot: not null } && !LongEventHandler.AnyEventNowOrWaiting;

    public override void Start()
    {
        try
        {
            typeof(Current).GetField("cameraInt", Any)!.SetValue(null, GameObject.Find("Camera").GetComponent<Camera>());
            typeof(Current).GetField("rootInt", Any)!.SetValue(null, this);
            CultureInfoUtility.EnsureEnglish();
            UnityDataInitializer.CopyUnityData();
            Prefs.Init();
            _prefsLoaded = true;
            // Prefs.xml in the run directory says so already; the GUI offers no developer tools whatever it says.
            Prefs.DevMode = false;
            Application.logMessageReceivedThreaded += Verse.Log.Notify_MessageReceivedThreadedInternal;
            Application.runInBackground = true;
            LongEventHandler.QueueLongEvent(StaticConstructorOnStartupUtility.CallAll, null, false, null);
            LongEventHandler.QueueLongEvent(() => PlayDataLoader.LoadAllPlayData(), null, true, null);
            LongEventHandler.QueueLongEvent(() =>
            {
                soundRoot = new SoundRoot();
                uiRoot = new ValidationUIRoot();
                uiRoot.Init();
            }, "InitializingInterface", false, null);
            if (Boot.Request.Script is { Count: > 0 } steps)
            {
                _script = new ScriptRunner(steps);
            }
        }
        catch (Exception e)
        {
            Verse.Log.Error("Critical error in the validation root's Start(): " + e);
        }
    }

    public override void Update()
    {
        base.Update();
        if (_prefsLoaded && Prefs.DevMode)
        {
            Prefs.DevMode = false;
        }
        if (Ready)
        {
            _script?.Update(UnityEngine.Time.frameCount);
        }
    }
}

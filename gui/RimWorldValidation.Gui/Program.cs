using System.Globalization;
using RimWorldValidation.Gui.Model;

namespace RimWorldValidation.Gui;

/// <summary>
/// Entry point of the validation GUI. It is started only by tools/gui_host.py
/// inside a prepared run directory, with <c>--gui-request &lt;path&gt;</c>. It
/// shows the validation screens and starts validations through the Controller;
/// it never offers a main menu, never creates a Game and never starts Steam.
/// Exit codes: 0 closed, 2 bad invocation or request, 3 something tried to
/// make the game playable (a Game or a scene change), 4 this game build lacks a
/// member the GUI needs, 5 a test script step failed.
/// </summary>
public static class Program
{
    public const int Closed = 0, BadRequest = 2, PlayableBlocked = 3, AdapterMismatch = 4, ScriptFailed = 5;

    public static int Main(string[] args)
    {
        if (args.Length != 2 || args[0] != "--gui-request")
        {
            Console.Error.WriteLine("usage: RimWorldValidationGui --gui-request <path>");
            Console.Error.WriteLine("This program is started by tools/gui_host.py; it is not a game launcher.");
            return BadRequest;
        }
        GuiRequest request;
        try
        {
            request = GuiRequest.Load(args[1]);
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException)
        {
            Console.Error.WriteLine($"invalid GUI request: {e.Message}");
            return BadRequest;
        }
        return Run(request);
    }

    // Separate method so that the usage/request checks above work without the game's assemblies.
    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
    private static int Run(GuiRequest request)
    {
        IReadOnlyList<string> missing = Boot.MissingMembers();
        if (missing.Count > 0)
        {
            Console.Error.WriteLine("adapter mismatch: this game build lacks " + string.Join(", ", missing));
            return AdapterMismatch;
        }
        CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.DefaultThreadCurrentUICulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        int code = Boot.Run(request);
        // Engine and game threads (audio, jobs, long events) must not keep the process alive.
        Environment.Exit(code);
        return code;
    }
}

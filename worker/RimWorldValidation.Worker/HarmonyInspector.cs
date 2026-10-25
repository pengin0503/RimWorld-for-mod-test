using System.Collections;
using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// Reads Harmony's own registry (HarmonyLib.Harmony.GetAllPatchedMethods /
/// GetPatchInfo) from whichever Harmony assembly the mods loaded, and compares
/// it with fully specified expected patches. Registration is evidence that a
/// patch was applied to that target; it does not prove the patch is correct.
/// </summary>
public sealed class HarmonyInspector
{
    // Request kind -> member of HarmonyLib.Patches holding that kind.
    private static readonly (string Kind, string Member)[] Kinds =
        [("prefix", "Prefixes"), ("postfix", "Postfixes"), ("transpiler", "Transpilers"), ("finalizer", "Finalizers")];
    private const int MaxListedPatches = 500;

    private sealed record Registered(MethodBase Target, string Kind, string Owner, MethodInfo PatchMethod);

    public void Write(Utf8JsonWriter json, List<JsonElement> expected)
    {
        json.WriteStartObject("harmony");
        Type[] harmonyTypes = AppDomain.CurrentDomain.GetAssemblies()
            .Select(a => a.GetType("HarmonyLib.Harmony", throwOnError: false))
            .OfType<Type>().ToArray();
        json.WriteStartArray("assemblies");
        foreach (Type type in harmonyTypes)
        {
            json.WriteStartObject();
            json.WriteString("name", type.Assembly.GetName().Name);
            json.WriteString("version", type.Assembly.GetName().Version?.ToString());
            json.WriteString("mvid", type.Assembly.ManifestModule.ModuleVersionId.ToString());
            json.WriteString("location", type.Assembly.Location);
            json.WriteEndObject();
        }
        json.WriteEndArray();
        if (harmonyTypes.Length == 0)
        {
            json.WriteBoolean("available", false);
            json.WriteStartArray("expected");
            foreach (JsonElement item in expected)
            {
                WriteOutcome(json, item, "missing", "no Harmony assembly was loaded");
            }
            json.WriteEndArray();
            json.WriteStartArray("unexpected");
            json.WriteEndArray();
            json.WriteEndObject();
            return;
        }
        json.WriteBoolean("available", true);
        List<Registered> registered;
        try
        {
            registered = ReadRegistry(harmonyTypes[0]);
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            json.WriteString("registryError", e.ToString());
            registered = [];
        }

        var matched = new HashSet<Registered>();
        json.WriteStartArray("expected");
        foreach (JsonElement item in expected)
        {
            try
            {
                MethodBase target = ResolveTarget(item);
                string kind = item.GetProperty("kind").GetString()!;
                string owner = item.GetProperty("owner").GetString()!;
                string patchType = item.GetProperty("patchType").GetString()!;
                string patchMethod = item.GetProperty("patchMethod").GetString()!;
                Registered? hit = registered.FirstOrDefault(r => r.Target == target && r.Kind == kind && r.Owner == owner
                    && r.PatchMethod.DeclaringType?.FullName == patchType && r.PatchMethod.Name == patchMethod);
                if (hit != null)
                {
                    matched.Add(hit);
                    WriteOutcome(json, item, "match", null);
                }
                else
                {
                    WriteOutcome(json, item, "missing", "no registered patch with this target, kind, owner and patch method");
                }
            }
            catch (Exception e) when (e is not OutOfMemoryException)
            {
                WriteOutcome(json, item, "error", e.Message);
            }
        }
        json.WriteEndArray();

        var owners = expected.Select(e => e.GetProperty("owner").GetString()).ToHashSet();
        json.WriteStartArray("unexpected");
        foreach (Registered r in registered.Where(r => owners.Contains(r.Owner) && !matched.Contains(r)))
        {
            WritePatch(json, r);
        }
        json.WriteEndArray();

        json.WriteNumber("registeredCount", registered.Count);
        json.WriteStartArray("registered");
        foreach (Registered r in registered.Take(MaxListedPatches))
        {
            WritePatch(json, r);
        }
        json.WriteEndArray();
        json.WriteEndObject();
    }

    private static List<Registered> ReadRegistry(Type harmony)
    {
        var result = new List<Registered>();
        MethodInfo all = harmony.GetMethod("GetAllPatchedMethods", BindingFlags.Public | BindingFlags.Static)
            ?? throw new MissingMethodException("HarmonyLib.Harmony", "GetAllPatchedMethods");
        MethodInfo info = harmony.GetMethod("GetPatchInfo", BindingFlags.Public | BindingFlags.Static)
            ?? throw new MissingMethodException("HarmonyLib.Harmony", "GetPatchInfo");
        foreach (MethodBase target in ((IEnumerable)all.Invoke(null, null)!).Cast<MethodBase>())
        {
            object? patches = info.Invoke(null, [target]);
            if (patches == null)
            {
                continue;
            }
            foreach ((string kind, string member) in Kinds)
            {
                foreach (object patch in (IEnumerable)Reflect.Member(patches, member)!)
                {
                    result.Add(new Registered(target, kind, (string)Reflect.Member(patch, "owner")!, (MethodInfo)Reflect.Member(patch, "PatchMethod")!));
                }
            }
        }
        return result;
    }

    private static MethodBase ResolveTarget(JsonElement item)
    {
        string assemblyName = item.GetProperty("targetAssembly").GetString()!;
        string typeName = item.GetProperty("targetType").GetString()!;
        string methodName = item.GetProperty("targetMethod").GetString()!;
        string[] parameters = item.GetProperty("targetParameters").EnumerateArray().Select(p => p.GetString()!).ToArray();
        int arity = item.TryGetProperty("genericArity", out JsonElement a) ? a.GetInt32() : 0;

        Assembly assembly = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(x => x.GetName().Name == assemblyName)
            ?? throw new InvalidOperationException($"target assembly {assemblyName} is not loaded");
        Type type = assembly.GetType(typeName, throwOnError: false)
            ?? throw new InvalidOperationException($"target type {typeName} not found in {assemblyName}");
        const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance | BindingFlags.DeclaredOnly;
        IEnumerable<MethodBase> candidates = methodName == ".ctor"
            ? type.GetConstructors(all)
            : methodName == ".cctor" ? type.GetConstructors(all).Where(c => c.IsStatic) : type.GetMethods(all).Where(m => m.Name == methodName);
        MethodBase[] found = candidates.Where(m =>
            (m.IsGenericMethodDefinition ? m.GetGenericArguments().Length : 0) == arity &&
            m.GetParameters().Select(p => p.ParameterType.ToString()).SequenceEqual(parameters)).ToArray();
        return found.Length switch
        {
            1 => found[0],
            0 => throw new InvalidOperationException($"no {typeName}.{methodName} with parameters ({string.Join(", ", parameters)})"),
            _ => throw new InvalidOperationException($"ambiguous {typeName}.{methodName}"),
        };
    }

    private static void WriteOutcome(Utf8JsonWriter json, JsonElement item, string outcome, string? detail)
    {
        json.WriteStartObject();
        json.WritePropertyName("expected");
        item.WriteTo(json);
        json.WriteString("outcome", outcome);
        if (detail != null)
        {
            json.WriteString("detail", detail);
        }
        json.WriteEndObject();
    }

    private static void WritePatch(Utf8JsonWriter json, Registered r)
    {
        json.WriteStartObject();
        json.WriteString("targetAssembly", r.Target.DeclaringType?.Assembly.GetName().Name);
        json.WriteString("targetType", r.Target.DeclaringType?.FullName);
        json.WriteString("targetMethod", r.Target.Name);
        json.WriteStartArray("targetParameters");
        foreach (ParameterInfo p in r.Target.GetParameters())
        {
            json.WriteStringValue(p.ParameterType.ToString());
        }
        json.WriteEndArray();
        json.WriteString("kind", r.Kind);
        json.WriteString("owner", r.Owner);
        json.WriteString("patchType", r.PatchMethod.DeclaringType?.FullName);
        json.WriteString("patchMethod", r.PatchMethod.Name);
        json.WriteEndObject();
    }
}

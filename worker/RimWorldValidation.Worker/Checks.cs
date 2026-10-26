using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// Post-load observations and expectation checks. They only read game state the
/// real loader produced; nothing here edits defs or invokes arbitrary game code.
/// Each outcome is "match", "mismatch" or "error" (could not evaluate).
/// </summary>
public sealed class Checks(GameApi api)
{
    public void WriteRunningMods(Utf8JsonWriter json)
    {
        json.WriteStartArray("runningMods");
        foreach (object mod in (IEnumerable)api.RunningMods.GetValue(null)!)
        {
            json.WriteStartObject();
            json.WriteString("packageId", (string?)Reflect.Member(mod, "PackageId"));
            json.WriteString("name", (string?)Reflect.Member(mod, "Name"));
            json.WriteString("folderName", (string?)Reflect.Member(mod, "FolderName"));
            json.WriteBoolean("official", (bool)Reflect.Member(mod, "IsOfficialMod")!);
            json.WriteNumber("defCount", ((IEnumerable)Reflect.Member(mod, "AllDefs")!).Cast<object>().Count());
            string root = (string)Reflect.Member(mod, "RootDir")!;
            json.WriteStartArray("loadFolders");
            foreach (string folder in (IEnumerable)Reflect.InstanceField(mod.GetType(), "foldersToLoadDescendingOrder").GetValue(mod)!)
            {
                string relative = Path.GetRelativePath(root, folder);
                json.WriteStringValue(relative == "." ? "" : relative.Replace(Path.DirectorySeparatorChar, '/'));
            }
            json.WriteEndArray();
            json.WriteEndObject();
        }
        json.WriteEndArray();
        json.WriteStartArray("modClasses");
        foreach (object handle in (IEnumerable)api.ModHandles.GetValue(null)!)
        {
            json.WriteStringValue(handle.GetType().FullName);
        }
        json.WriteEndArray();
    }

    /// <summary>
    /// The individual errors behind the game's "Translation data for language X has
    /// N errors" warning: the same lists LoadedLanguage.InjectIntoData_AfterImpliedDefs
    /// counts (the language's own load errors plus each def-injection package's).
    /// </summary>
    public static void WriteTranslationErrors(Utf8JsonWriter json, object? language, int maxItems, int maxBytes)
    {
        if (language == null)
        {
            json.WriteNull("translationErrors");
            return;
        }
        var errors = ((IEnumerable)Reflect.Member(language, "loadErrors")!).Cast<string>().ToList();
        foreach (object package in (IEnumerable)Reflect.Member(language, "defInjections")!)
        {
            errors.AddRange(((IEnumerable)Reflect.Member(package, "loadErrors")!).Cast<string>());
        }
        json.WriteStartObject("translationErrors");
        json.WriteNumber("count", errors.Count);
        json.WriteNumber("dropped", Math.Max(0, errors.Count - maxItems));
        json.WriteStartArray("items");
        foreach (string error in errors.Take(maxItems))
        {
            json.WriteStringValue(Diagnostics.TruncateUtf8(error, maxBytes));
        }
        json.WriteEndArray();
        json.WriteEndObject();
    }

    public List<string> RunningModIds()
    {
        return ((IEnumerable)api.RunningMods.GetValue(null)!).Cast<object>()
            .Select(m => ((string)Reflect.Member(m, "PackageId")!).ToLowerInvariant()).ToList();
    }

    public void WriteExpectations(Utf8JsonWriter json, JsonElement expectations)
    {
        json.WriteStartObject("checks");
        json.WriteStartArray("defs");
        foreach (JsonElement item in Items(expectations, "defs"))
        {
            CheckDef(json, item);
        }
        json.WriteEndArray();
        json.WriteStartArray("defValues");
        foreach (JsonElement item in Items(expectations, "defValues"))
        {
            CheckDefValue(json, item);
        }
        json.WriteEndArray();
        json.WriteStartArray("keyed");
        foreach (JsonElement item in Items(expectations, "keyed"))
        {
            CheckKeyed(json, item);
        }
        json.WriteEndArray();
        new HarmonyInspector().Write(json, Items(expectations, "harmonyPatches").ToList());
        json.WriteEndObject();
    }

    private static IEnumerable<JsonElement> Items(JsonElement expectations, string name)
    {
        return expectations.TryGetProperty(name, out JsonElement list) ? list.EnumerateArray() : [];
    }

    private void CheckDef(Utf8JsonWriter json, JsonElement item)
    {
        json.WriteStartObject();
        json.WritePropertyName("expected");
        item.WriteTo(json);
        try
        {
            object? def = FindDef(item.GetProperty("type").GetString()!, item.GetProperty("defName").GetString()!);
            bool expected = item.GetProperty("exists").GetBoolean();
            json.WriteBoolean("actualExists", def != null);
            json.WriteString("outcome", (def != null) == expected ? "match" : "mismatch");
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            json.WriteString("outcome", "error");
            json.WriteString("error", e.Message);
        }
        json.WriteEndObject();
    }

    private void CheckDefValue(Utf8JsonWriter json, JsonElement item)
    {
        json.WriteStartObject();
        json.WritePropertyName("expected");
        item.WriteTo(json);
        try
        {
            object? def = FindDef(item.GetProperty("type").GetString()!, item.GetProperty("defName").GetString()!);
            if (def == null)
            {
                json.WriteString("outcome", "mismatch");
                json.WriteNull("actual");
                json.WriteString("detail", "def not found");
            }
            else
            {
                object? value = MemberPath.Evaluate(def, item.GetProperty("path").GetString()!);
                string actual = MemberPath.Format(value);
                json.WriteString("actual", actual);
                json.WriteString("outcome", MemberPath.Equal(actual, item.GetProperty("equals").GetString()!) ? "match" : "mismatch");
            }
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            json.WriteString("outcome", "error");
            json.WriteString("error", e.Message);
        }
        json.WriteEndObject();
    }

    private void CheckKeyed(Utf8JsonWriter json, JsonElement item)
    {
        json.WriteStartObject();
        json.WritePropertyName("expected");
        item.WriteTo(json);
        try
        {
            object language = api.ActiveLanguage.GetValue(null) ?? throw new InvalidOperationException("no active language");
            MethodInfo lookup = Reflect.InstanceMethod(language.GetType(), "TryGetTextFromKey",
                typeof(string), Reflect.Type("Verse.TaggedString, Assembly-CSharp").MakeByRefType());
            object?[] args = [item.GetProperty("key").GetString(), null];
            bool found = (bool)lookup.Invoke(language, args)!;
            string? text = found ? (string?)Reflect.Member(args[1]!, "RawText") : null;
            json.WriteString("language", (string?)Reflect.Member(language, "folderName"));
            json.WriteBoolean("found", found);
            json.WriteString("actual", text);
            bool ok = item.TryGetProperty("equals", out JsonElement equals) ? found && text == equals.GetString() : found;
            json.WriteString("outcome", ok ? "match" : "mismatch");
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            json.WriteString("outcome", "error");
            json.WriteString("error", e.Message);
        }
        json.WriteEndObject();
    }

    private object? FindDef(string typeName, string defName)
    {
        Type[] matches = api.DefTypes().Where(t => t.Name == typeName || t.FullName == typeName).Distinct().ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidOperationException(matches.Length == 0 ? $"unknown def type {typeName}" : $"ambiguous def type {typeName}; use the full name");
        }
        Type database = Reflect.Type("Verse.DefDatabase`1, Assembly-CSharp").MakeGenericType(matches[0]);
        MethodInfo get = database.GetMethod("GetNamedSilentFail", BindingFlags.Public | BindingFlags.Static, [typeof(string)])
            ?? throw new AdapterMismatchException("Verse.DefDatabase`1.GetNamedSilentFail(String)");
        return get.Invoke(null, [defName]);
    }
}

/// <summary>
/// A deliberately small read-only path language for def values:
/// <c>member</c>, <c>member.member</c>, <c>list[3]</c> and <c>list[key=value]</c>
/// (first element whose member <c>key</c> formats to <c>value</c>; a Def formats as its defName).
/// </summary>
public static class MemberPath
{
    public static object? Evaluate(object root, string path)
    {
        object? current = root;
        foreach (string segment in path.Split('.'))
        {
            if (current == null)
            {
                throw new InvalidOperationException($"null before '{segment}'");
            }
            string name = segment;
            string? selector = null;
            int open = segment.IndexOf('[');
            if (open >= 0)
            {
                if (!segment.EndsWith(']'))
                {
                    throw new FormatException($"bad segment '{segment}'");
                }
                name = segment[..open];
                selector = segment[(open + 1)..^1];
            }
            current = Reflect.Member(current, name);
            if (selector != null)
            {
                current = Select(current, selector);
            }
        }
        return current;
    }

    private static object? Select(object? list, string selector)
    {
        if (list is not IEnumerable items || list is string)
        {
            throw new InvalidOperationException("selector applied to a non-list");
        }
        int equals = selector.IndexOf('=');
        if (equals < 0)
        {
            int index = int.Parse(selector, CultureInfo.InvariantCulture);
            return items.Cast<object?>().ElementAtOrDefault(index) ?? throw new InvalidOperationException($"no element {index}");
        }
        string key = selector[..equals];
        string wanted = selector[(equals + 1)..];
        foreach (object? item in items)
        {
            if (item != null && Format(Reflect.Member(item, key)) == wanted)
            {
                return item;
            }
        }
        throw new InvalidOperationException($"no element with {key}={wanted}");
    }

    public static string Format(object? value)
    {
        if (value == null)
        {
            return "null";
        }
        Type type = value.GetType();
        for (Type? t = type; t != null; t = t.BaseType)
        {
            if (t.FullName == "Verse.Def")
            {
                return (string)Reflect.Member(value, "defName")!;
            }
        }
        return value switch
        {
            float f => f.ToString("R", CultureInfo.InvariantCulture),
            double d => d.ToString("R", CultureInfo.InvariantCulture),
            IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
            _ => value.ToString() ?? "",
        };
    }

    public static bool Equal(string actual, string expected)
    {
        if (actual == expected)
        {
            return true;
        }
        return double.TryParse(actual, NumberStyles.Float, CultureInfo.InvariantCulture, out double a)
            && double.TryParse(expected, NumberStyles.Float, CultureInfo.InvariantCulture, out double b)
            && Math.Abs(a - b) <= 1e-6 * Math.Max(1.0, Math.Abs(b));
    }
}

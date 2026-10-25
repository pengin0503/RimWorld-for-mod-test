using System.Reflection;

namespace RimWorldValidation.Worker;

/// <summary>Thrown when the loaded game build lacks a member the adapter needs.</summary>
public sealed class AdapterMismatchException(string member) : Exception($"adapter member not found: {member}")
{
    public string Member { get; } = member;
}

/// <summary>Small reflection helpers that fail loudly with the missing member name.</summary>
public static class Reflect
{
    private const BindingFlags AnyStatic = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static;
    private const BindingFlags AnyInstance = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;

    public static Type Type(string assemblyQualifiedName)
    {
        return System.Type.GetType(assemblyQualifiedName, throwOnError: false)
            ?? throw new AdapterMismatchException(assemblyQualifiedName);
    }

    public static MethodInfo StaticMethod(Type type, string name, params Type[] parameters)
    {
        return type.GetMethod(name, AnyStatic, binder: null, parameters, modifiers: null)
            ?? throw new AdapterMismatchException($"{type.FullName}.{name}({string.Join(",", parameters.Select(p => p.Name))})");
    }

    public static MethodInfo InstanceMethod(Type type, string name, params Type[] parameters)
    {
        return type.GetMethod(name, AnyInstance, binder: null, parameters, modifiers: null)
            ?? throw new AdapterMismatchException($"{type.FullName}.{name}({string.Join(",", parameters.Select(p => p.Name))})");
    }

    public static PropertyInfo StaticProperty(Type type, string name)
    {
        return type.GetProperty(name, AnyStatic) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static PropertyInfo InstanceProperty(Type type, string name)
    {
        return type.GetProperty(name, AnyInstance) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static FieldInfo StaticField(Type type, string name)
    {
        return type.GetField(name, AnyStatic) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static FieldInfo InstanceField(Type type, string name)
    {
        return type.GetField(name, AnyInstance) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static EventInfo StaticEvent(Type type, string name)
    {
        return type.GetEvent(name, AnyStatic) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static EventInfo InstanceEvent(Type type, string name)
    {
        return type.GetEvent(name, AnyInstance) ?? throw new AdapterMismatchException($"{type.FullName}.{name}");
    }

    public static T Delegate<T>(MethodInfo method, object? target = null) where T : Delegate
    {
        return (T)System.Delegate.CreateDelegate(typeof(T), target, method);
    }

    /// <summary>Reads a public field or property by name, whichever the type exposes.</summary>
    public static object? Member(object target, string name)
    {
        Type type = target.GetType();
        FieldInfo? field = type.GetField(name, AnyInstance);
        if (field != null)
        {
            return field.GetValue(target);
        }
        PropertyInfo? property = type.GetProperty(name, AnyInstance);
        if (property != null && property.GetIndexParameters().Length == 0)
        {
            return property.GetValue(target);
        }
        throw new MissingMemberException(type.FullName, name);
    }
}

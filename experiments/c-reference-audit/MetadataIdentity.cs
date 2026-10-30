using System.Reflection.Metadata;
using System.Text.Json.Nodes;

namespace CReferenceAudit;

public sealed record MetadataIdentity(string Name, string Assembly, int Arity, int Depth, string Handle, string Scope)
{
    public JsonObject PublicShape() => new() { ["handle"] = Handle, ["scope"] = Scope, ["depth"] = Depth };

    static string Join(string ns, List<string> names)
    {
        names.Reverse();
        string name = (ns.Length == 0 ? "" : ns + ".") + string.Join("+", names);
        if (name.Length > 2048) throw new BudgetExceededException();
        return name;
    }

    public static MetadataIdentity Read(MetadataReader reader, TypeDefinitionHandle handle)
    {
        var names = new List<string>();
        var seen = new HashSet<TypeDefinitionHandle>();
        var original = reader.GetTypeDefinition(handle);
        string ns;
        while (true)
        {
            if (!seen.Add(handle)) throw new BadImageFormatException();
            if (names.Count >= 8) throw new BudgetExceededException();
            var type = reader.GetTypeDefinition(handle);
            names.Add(reader.GetString(type.Name));
            var parent = type.GetDeclaringType();
            ns = reader.GetString(type.Namespace);
            if (parent.IsNil) break;
            if (ns.Length != 0) throw new BadImageFormatException();
            handle = parent;
        }
        return new(Join(ns, names), reader.GetString(reader.GetAssemblyDefinition().Name),
                   original.GetGenericParameters().Count, names.Count - 1, "definition", "module");
    }

    public static MetadataIdentity Read(MetadataReader reader, TypeReferenceHandle handle)
    {
        var names = new List<string>();
        var seen = new HashSet<TypeReferenceHandle>();
        string leaf = reader.GetString(reader.GetTypeReference(handle).Name);
        int arity = 0;
        int tick = leaf.LastIndexOf('`');
        if (tick >= 0 && (!int.TryParse(leaf[(tick + 1)..], out arity) || arity < 0 || arity > 32))
            throw new BadImageFormatException();
        while (true)
        {
            if (!seen.Add(handle)) throw new BadImageFormatException();
            if (names.Count >= 8) throw new BudgetExceededException();
            var type = reader.GetTypeReference(handle);
            names.Add(reader.GetString(type.Name));
            string ns = reader.GetString(type.Namespace);
            var scope = type.ResolutionScope;
            if (scope.Kind == HandleKind.TypeReference)
            {
                if (ns.Length != 0) throw new BadImageFormatException();
                handle = (TypeReferenceHandle)scope;
                continue;
            }
            string assembly = scope.Kind switch
            {
                HandleKind.AssemblyReference => reader.GetString(reader.GetAssemblyReference((AssemblyReferenceHandle)scope).Name),
                HandleKind.ModuleDefinition => reader.GetString(reader.GetAssemblyDefinition().Name),
                _ => ""
            };
            return new(Join(ns, names), assembly, arity, names.Count - 1, "reference",
                scope.Kind == HandleKind.AssemblyReference ? "assembly" : scope.Kind == HandleKind.ModuleDefinition ? "module" : "other");
        }
    }
}

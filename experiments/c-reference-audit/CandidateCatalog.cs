using System.Reflection.Metadata;
using System.Text.Json.Nodes;
namespace CReferenceAudit;

public static class CandidateCatalog
{
    static readonly (string Id,string Name,string Assembly,int Arity)[] Entries =
    [
        ("action-1","System.Action`1","System.Private.CoreLib",1),
        ("exception","System.Exception","System.Private.CoreLib",0),
        ("nullable-1","System.Nullable`1","System.Private.CoreLib",1),
        ("bill","RimWorld.Bill","Assembly-CSharp",0),
        ("incident-parms","RimWorld.IncidentParms","Assembly-CSharp",0),
        ("thing-category","Verse.ThingCategoryDef","Assembly-CSharp",0)
    ];
    public static JsonObject? Match(MetadataReader reader, TypeDefinitionHandle handle)
    {
        var t=reader.GetTypeDefinition(handle);
        if (!t.GetDeclaringType().IsNil) return null;
        string name=reader.GetString(t.Namespace)+"."+reader.GetString(t.Name);
        string assembly=reader.GetString(reader.GetAssemblyDefinition().Name);
        foreach(var c in Entries)
            if(c.Name==name && c.Assembly==assembly && t.GetGenericParameters().Count==c.Arity)
                return new JsonObject { ["id"]=c.Id,["kind"]="definition",["arity"]=c.Arity };
        return null;
    }
    public static JsonObject? Match(MetadataReader reader, TypeReferenceHandle handle)
    {
        var t=reader.GetTypeReference(handle);
        if(t.ResolutionScope.Kind!=HandleKind.AssemblyReference) return null;
        string name=reader.GetString(t.Namespace)+"."+reader.GetString(t.Name);
        string assembly=reader.GetString(reader.GetAssemblyReference((AssemblyReferenceHandle)t.ResolutionScope).Name);
        foreach(var c in Entries)
            if(c.Name==name && c.Assembly==assembly)
                return new JsonObject { ["id"]=c.Id,["kind"]="reference",["arity"]=c.Arity };
        return null;
    }
    public static JsonArray Definitions(MetadataReader reader)
    {
        var rows=new JsonArray();
        foreach(var h in reader.TypeDefinitions)
            if(Match(reader,h) is JsonObject row) rows.Add(row);
        return rows;
    }
}

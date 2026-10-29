using System.Collections.Immutable;
using System.Reflection.Metadata;
using System.Text.Json.Nodes;

namespace CReferenceAudit;

sealed class SignatureProvider : ISignatureTypeProvider<JsonNode, object?>
{
    static JsonObject Node(string kind, JsonNode? element = null) => new() { ["kind"] = kind, ["element"] = element };
    public JsonNode GetArrayType(JsonNode elementType, ArrayShape shape) => new JsonObject { ["kind"] = "array", ["element"] = elementType, ["rank"] = shape.Rank };
    public JsonNode GetByReferenceType(JsonNode elementType) => Node("byref", elementType);
    public JsonNode GetFunctionPointerType(MethodSignature<JsonNode> signature) => Node("functionPointer");
    public JsonNode GetGenericInstantiation(JsonNode genericType, ImmutableArray<JsonNode> typeArguments)
    {
        if (typeArguments.Length > 32) throw new BadImageFormatException();
        var args = new JsonArray();
        foreach (var argument in typeArguments) args.Add(argument);
        return new JsonObject { ["kind"] = "generic", ["element"] = genericType, ["arguments"] = args };
    }
    public JsonNode GetGenericMethodParameter(object? genericContext, int index) => new JsonObject { ["kind"] = "methodParameter", ["index"] = index };
    public JsonNode GetGenericTypeParameter(object? genericContext, int index) => new JsonObject { ["kind"] = "typeParameter", ["index"] = index };
    public JsonNode GetModifiedType(JsonNode modifier, JsonNode unmodifiedType, bool isRequired) => new JsonObject { ["kind"] = "modified", ["modifier"] = modifier, ["element"] = unmodifiedType, ["required"] = isRequired };
    public JsonNode GetPinnedType(JsonNode elementType) => Node("pinned", elementType);
    public JsonNode GetPointerType(JsonNode elementType) => Node("pointer", elementType);
    public JsonNode GetPrimitiveType(PrimitiveTypeCode typeCode) => new JsonObject { ["kind"] = "primitive", ["name"] = typeCode.ToString() };
    public JsonNode GetSZArrayType(JsonNode elementType) => new JsonObject { ["kind"] = "array", ["element"] = elementType, ["rank"] = 1 };
    public JsonNode GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind)
    {
        var t = reader.GetTypeDefinition(handle);
        return new JsonObject { ["kind"] = "named", ["name"] = reader.GetString(t.Namespace) + "." + reader.GetString(t.Name) };
    }
    public JsonNode GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
    {
        var t = reader.GetTypeReference(handle);
        return new JsonObject { ["kind"] = "named", ["name"] = reader.GetString(t.Namespace) + "." + reader.GetString(t.Name) };
    }
    public JsonNode GetTypeFromSpecification(MetadataReader reader, object? genericContext, TypeSpecificationHandle handle, byte rawTypeKind) => reader.GetTypeSpecification(handle).DecodeSignature(this, genericContext);
}

using System.Collections.Immutable;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json.Nodes;

namespace CReferenceAudit;

public sealed class BudgetExceededException : Exception { }

public static class Scanner
{
    static readonly (string Id, string Type, string[] Methods)[] Targets =
    [
        ("game", "Verse.Game", ["InitNewGame", "FinalizeInit"]),
        ("map-generator", "Verse.MapGenerator", ["GenerateMap"]),
        ("long-events", "Verse.LongEventHandler", ["ExecuteWhenFinished", "QueueLongEvent"]),
        ("bill-dialog", "RimWorld.Dialog_BillConfig", ["DoIngredientConfigPane", "get_HiddenSpecialThingFilters"]),
        ("filter-ui", "Verse.ThingFilterUI", ["DoThingFilterConfigWindow"]),
        ("filter-listing", "Verse.Listing_TreeThingFilter", [".ctor", "Visible", "DoThingDef"]),
        ("bill-factory", "RimWorld.BillUtility", ["MakeNewBill"]),
        ("incident", "RimWorld.IncidentWorker", ["TryExecute"]),
        ("dialog-choice", "Verse.DiaOption", ["Activate"])
    ];
    static readonly Dictionary<ushort, OpCode> Opcodes = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static)
        .Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!)
        .ToDictionary(o => unchecked((ushort)o.Value));

    public static JsonObject Scan(byte[] image, string expectedHash)
    {
        if (image.Length == 0 || image.Length > 64 * 1024 * 1024) throw new BadImageFormatException();
        string digest = Convert.ToHexStringLower(SHA256.HashData(image));
        if (digest != expectedHash) throw new BadImageFormatException();
        using var stream = new MemoryStream(image, writable: false);
        using var pe = new PEReader(stream);
        MetadataReader reader = pe.GetMetadataReader();
        var provider = new SignatureProvider();
        int methods = 0, totalIl = 0, instructions = 0, calls = 0;
        var output = new JsonArray();
        foreach (var target in Targets)
        {
            var definitions = reader.TypeDefinitions.Where(h => TypeName(reader, h) == target.Type).ToArray();
            if (definitions.Length > 1) throw new BadImageFormatException();
            var entries = new JsonArray();
            foreach (string methodName in target.Methods)
            {
                var overloads = new JsonArray();
                if (definitions.Length == 1)
                {
                    var type = reader.GetTypeDefinition(definitions[0]);
                    foreach (var handle in type.GetMethods())
                    {
                        var method = reader.GetMethodDefinition(handle);
                        if (reader.GetString(method.Name) != methodName) continue;
                        if (++methods > 128 || overloads.Count >= 16) throw new BudgetExceededException();
                        provider.Candidates = new JsonArray();
                        var signature = method.DecodeSignature(provider, null);
                        CheckDepth(signature.ReturnType, 0);
                        foreach (var parameter in signature.ParameterTypes) CheckDepth(parameter, 0);
                        if (signature.ParameterTypes.Length > 64 || signature.GenericParameterCount > 32) throw new BudgetExceededException();
                        var parameters = new JsonArray();
                        foreach (var parameter in signature.ParameterTypes) parameters.Add(parameter);
                        var sites = new JsonArray();
                        var regions = new JsonArray();
                        var branches = new JsonArray();
                        if (method.RelativeVirtualAddress != 0)
                        {
                            var body = pe.GetMethodBody(method.RelativeVirtualAddress);
                            byte[] il = body.GetILBytes() ?? throw new BadImageFormatException();
                            totalIl += il.Length;
                            if (il.Length > 65536 || totalIl > 1024 * 1024) throw new BudgetExceededException();
                            DecodeIl(reader, il, sites, branches, ref instructions, ref calls);
                            foreach (var region in body.ExceptionRegions)
                                regions.Add(new JsonObject { ["kind"] = region.Kind.ToString(), ["tryOffset"] = region.TryOffset, ["tryLength"] = region.TryLength, ["handlerOffset"] = region.HandlerOffset, ["handlerLength"] = region.HandlerLength });
                        }
                        overloads.Add(new JsonObject { ["token"] = MetadataTokens.GetToken(handle), ["return"] = signature.ReturnType,
                            ["parameters"] = parameters, ["genericCount"] = signature.GenericParameterCount,
                            ["static"] = (method.Attributes & MethodAttributes.Static) != 0,
                            ["visibility"] = (method.Attributes & MethodAttributes.MemberAccessMask).ToString(),
                            ["calls"] = sites, ["branches"] = branches, ["exceptions"] = regions, ["candidateReferences"] = provider.Candidates });
                    }
                }
                entries.Add(new JsonObject { ["name"] = methodName, ["overloads"] = overloads });
            }
            output.Add(new JsonObject { ["id"] = target.Id, ["found"] = definitions.Length == 1, ["methods"] = entries });
        }
        return new JsonObject { ["sha256"] = digest, ["types"] = output, ["candidateDefinitions"] = CandidateCatalog.Definitions(reader), ["metrics"] = new JsonObject { ["methods"] = methods, ["ilBytes"] = totalIl, ["instructions"] = instructions, ["calls"] = calls } };
    }

    static void CheckDepth(JsonNode node, int depth)
    {
        if (depth >= 8) throw new BudgetExceededException();
        if (node is not JsonObject obj) throw new BadImageFormatException();
        if (obj["element"] is JsonNode element) CheckDepth(element, depth + 1);
        if (obj["modifier"] is JsonNode modifier) CheckDepth(modifier, depth + 1);
        if (obj["arguments"] is JsonArray args)
        {
            if (args.Count > 32) throw new BudgetExceededException();
            foreach (var argument in args) CheckDepth(argument ?? throw new BadImageFormatException(), depth + 1);
        }
    }

    static string TypeName(MetadataReader reader, TypeDefinitionHandle handle)
    {
        var type = reader.GetTypeDefinition(handle);
        return reader.GetString(type.Namespace) + "." + reader.GetString(type.Name);
    }

    static string MemberName(MetadataReader reader, int token)
    {
        EntityHandle entity = MetadataTokens.EntityHandle(token);
        if (entity.Kind == HandleKind.MethodSpecification)
            return MemberName(reader, MetadataTokens.GetToken(reader.GetMethodSpecification((MethodSpecificationHandle)entity).Method));
        if (entity.Kind == HandleKind.MethodDefinition)
        {
            var method = reader.GetMethodDefinition((MethodDefinitionHandle)entity);
            return TypeName(reader, method.GetDeclaringType()) + "." + reader.GetString(method.Name);
        }
        if (entity.Kind == HandleKind.MemberReference)
        {
            var member = reader.GetMemberReference((MemberReferenceHandle)entity);
            string parent = member.Parent.Kind switch
            {
                HandleKind.TypeDefinition => TypeName(reader, (TypeDefinitionHandle)member.Parent),
                HandleKind.TypeReference => RefName(reader, (TypeReferenceHandle)member.Parent),
                _ => "unresolved"
            };
            return parent + "." + reader.GetString(member.Name);
        }
        return "unresolved";
    }

    static string RefName(MetadataReader reader, TypeReferenceHandle handle)
    {
        var type = reader.GetTypeReference(handle);
        return reader.GetString(type.Namespace) + "." + reader.GetString(type.Name);
    }

    static void DecodeIl(MetadataReader reader, byte[] il, JsonArray sites, JsonArray branches, ref int instructions, ref int calls)
    {
        int pos = 0;
        var starts = new HashSet<int>();
        var branchTargets = new List<int>();
        while (pos < il.Length)
        {
            if (++instructions > 100000) throw new BudgetExceededException();
            int offset = pos;
            starts.Add(offset);
            ushort code = il[pos++];
            if (code is >= 0xf8 and <= 0xfd or 0xff) throw new BadImageFormatException();
            if (code == 0xfe)
            {
                if (pos >= il.Length) throw new BadImageFormatException();
                code = (ushort)(0xfe00 | il[pos++]);
            }
            if (!Opcodes.TryGetValue(code, out var op)) throw new BadImageFormatException();
            int size = op.OperandType switch
            {
                OperandType.InlineNone => 0,
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2,
                OperandType.InlineI or OperandType.InlineBrTarget or OperandType.InlineField or OperandType.InlineMethod or OperandType.InlineSig or OperandType.InlineString or OperandType.InlineTok or OperandType.InlineType or OperandType.ShortInlineR => 4,
                OperandType.InlineI8 or OperandType.InlineR => 8,
                OperandType.InlineSwitch => SwitchSize(il, pos),
                _ => throw new BadImageFormatException()
            };
            if (size < 0 || size > il.Length - pos) throw new BadImageFormatException();
            if (op.OperandType == OperandType.ShortInlineBrTarget || op.OperandType == OperandType.InlineBrTarget)
            {
                int delta = size == 1 ? unchecked((sbyte)il[pos]) : BitConverter.ToInt32(il, pos);
                long target = (long)pos + size + delta;
                if (target < 0 || target >= il.Length) throw new BadImageFormatException();
                branchTargets.Add((int)target);
                branches.Add(new JsonObject { ["offset"] = offset, ["target"] = (int)target });
            }
            else if (op.OperandType == OperandType.InlineSwitch)
            {
                int count = BitConverter.ToInt32(il, pos);
                for (int i = 0; i < count; i++)
                {
                    long target = (long)pos + size + BitConverter.ToInt32(il, pos + 4 + i * 4);
                    if (target < 0 || target >= il.Length) throw new BadImageFormatException();
                    branchTargets.Add((int)target);
                    branches.Add(new JsonObject { ["offset"] = offset, ["target"] = (int)target });
                }
            }
            if (op == OpCodes.Call || op == OpCodes.Callvirt || op == OpCodes.Newobj)
            {
                if (++calls > 4096) throw new BudgetExceededException();
                int token = BitConverter.ToInt32(il, pos);
                sites.Add(new JsonObject { ["offset"] = offset, ["kind"] = op.Name, ["target"] = MemberName(reader, token) });
            }
            pos += size;
        }
        if (branchTargets.Any(target => !starts.Contains(target))) throw new BadImageFormatException();
    }

    static int SwitchSize(byte[] il, int pos)
    {
        if (il.Length - pos < 4) throw new BadImageFormatException();
        int count = BitConverter.ToInt32(il, pos);
        if (count < 0 || count > (il.Length - pos - 4) / 4) throw new BadImageFormatException();
        return 4 + count * 4;
    }
}

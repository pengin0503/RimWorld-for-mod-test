using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using CReferenceAudit;

static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
using (var core = new PEReader(File.OpenRead(typeof(Exception).Assembly.Location)))
{
    var metadata = core.GetMetadataReader();
    var handle = metadata.TypeDefinitions.Single(h => metadata.GetString(metadata.GetTypeDefinition(h).Namespace) == "System" && metadata.GetString(metadata.GetTypeDefinition(h).Name) == "Exception");
    Require((string?)CandidateCatalog.Match(metadata, handle)?["id"] == "exception", "core candidate missing");
}
string path = typeof(Verse.Game).Assembly.Location;
byte[] image = File.ReadAllBytes(path);
string marker = Path.Combine(Path.GetTempPath(), "rwmt-static-audit-" + Guid.NewGuid().ToString("N"));
Environment.SetEnvironmentVariable("RWMT_AUDIT_MARKER", marker);
using (var own = new PEReader(new MemoryStream(image)))
{
    var metadata = own.GetMetadataReader();
    var handle = metadata.TypeDefinitions.Single(h => metadata.GetString(metadata.GetTypeDefinition(h).Namespace) == "RimWorld" && metadata.GetString(metadata.GetTypeDefinition(h).Name) == "IncidentParms");
    Require(CandidateCatalog.Match(metadata, handle) is null, "same name from wrong assembly accepted");
}
JsonObject result = Scanner.Scan(image, Hash(image));
Require(!File.Exists(marker), "static constructor was executed");
var game = result["types"]!.AsArray().Single(t => (string?)t!["id"] == "game")!;
var init = game["methods"]!.AsArray().Single(t => (string?)t!["name"] == "InitNewGame")!;
var overloads = init["overloads"]!.AsArray();
Require(overloads.Count == 5, "overload loss");
Require(init.ToJsonString().Contains("byref") && init.ToJsonString().Contains("array"), "signature loss");
Require(overloads.Any(o => (int?)o!["genericCount"] == 1), "generic signature loss");
Require(overloads.Any(o => o!["branches"]!.AsArray().Count > 0), "branch metadata missing");
var caller = overloads.Single(o => o!["parameters"]!.AsArray().Count == 0)!;
var site = caller["calls"]!.AsArray().Single(c => ((string?)c!["target"])?.EndsWith(".FinalizeInit") == true)!;
Require((int?)site["offset"] == 1 && (string?)site["kind"] == "call", "call offset or opcode incorrect");
Require(overloads.Any(o => !ReferenceEquals(o, caller) && o!["calls"]!.AsArray().Any(c => ((string?)c!["target"])?.EndsWith(".FinalizeInit") == true)), "generic method specification unresolved");
Require(overloads.Single(o => o!["parameters"]!.ToJsonString().Contains("byref"))!["calls"]!.AsArray().All(c => ((string?)c!["target"])?.EndsWith(".FinalizeInit") != true), "literal mistaken for call");
byte[] truncated = image[..32];
try { Scanner.Scan(truncated, Hash(truncated)); throw new Exception("truncated PE accepted"); }
catch (BadImageFormatException) { }
byte[] invalid = (byte[])image.Clone();
using (var pe = new PEReader(new MemoryStream(invalid)))
{
    var md = pe.GetMetadataReader();
    var type = md.TypeDefinitions.Select(md.GetTypeDefinition).Single(t => md.GetString(t.Namespace) == "Verse" && md.GetString(t.Name) == "Game");
    var method = type.GetMethods().Select(md.GetMethodDefinition).First(m => md.GetString(m.Name) == "InitNewGame" && m.RelativeVirtualAddress != 0);
    int rva = method.RelativeVirtualAddress;
    var section = pe.PEHeaders.SectionHeaders[pe.PEHeaders.GetContainingSectionIndex(rva)];
    int header = section.PointerToRawData + rva - section.VirtualAddress;
    int headerSize = (invalid[header] & 3) == 2 ? 1 : (invalid[header + 1] >> 4) * 4;
    invalid[header + headerSize] = 0xff;
}
try { Scanner.Scan(invalid, Hash(invalid)); throw new Exception("reserved opcode accepted"); }
catch (BadImageFormatException) { }
Console.WriteLine("synthetic PE checks passed");

namespace Verse
{
    public class Game
    {
        static Game() { File.WriteAllText(Environment.GetEnvironmentVariable("RWMT_AUDIT_MARKER")!, "executed"); }
        public void InitNewGame() { FinalizeInit(); }
        public void InitNewGame(ref int[] values) { Console.WriteLine("FinalizeInit literal is not a call"); }
        public void InitNewGame<T>(T value) { Console.WriteLine(value); }
        public void InitNewGame(bool value) { if (value) Console.WriteLine(value); }
        public void InitNewGame(long value) { FinalizeInit<long>(); }
        public void FinalizeInit() { }
        public void FinalizeInit<T>() { }
    }
}

namespace RimWorld { public class IncidentParms { } }

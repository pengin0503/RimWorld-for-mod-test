using System.Security.Cryptography;
using System.Text.Json.Nodes;
using CReferenceAudit;

string path = typeof(Verse.Game).Assembly.Location;
byte[] image = File.ReadAllBytes(path);
string hash = Convert.ToHexStringLower(SHA256.HashData(image));
string marker = Path.Combine(Path.GetTempPath(), "rwmt-static-audit-" + Guid.NewGuid().ToString("N"));
Environment.SetEnvironmentVariable("RWMT_AUDIT_MARKER", marker);
JsonObject result = Scanner.Scan(image, hash);
if (File.Exists(marker)) throw new Exception("static constructor was executed");
var game = result["types"]!.AsArray().Single(t => (string?)t!["id"] == "game")!;
var init = game["methods"]!.AsArray().Single(t => (string?)t!["name"] == "InitNewGame")!;
if (init["overloads"]!.AsArray().Count != 2) throw new Exception("overload loss");
if (!init.ToJsonString().Contains("byref") || !init.ToJsonString().Contains("array")) throw new Exception("signature loss");
if (!init.ToJsonString().Contains("FinalizeInit")) throw new Exception("direct call missing");
try { Scanner.Scan(image[..32], hash); throw new Exception("truncated PE accepted"); }
catch (BadImageFormatException) { }
Console.WriteLine("synthetic PE checks passed");

namespace Verse
{
    public class Game
    {
        static Game() { File.WriteAllText(Environment.GetEnvironmentVariable("RWMT_AUDIT_MARKER")!, "executed"); }
        public void InitNewGame() { FinalizeInit(); }
        public void InitNewGame(ref int[] values) { Console.WriteLine("FinalizeInit literal is not a call"); }
        public void FinalizeInit() { }
    }
}

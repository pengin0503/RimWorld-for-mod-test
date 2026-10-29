using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using CReferenceAudit;

if (args.Length != 3) return 2;
try
{
    byte[] data = File.ReadAllBytes(args[0]);
    JsonObject result = Scanner.Scan(data, args[1]);
    string json = result.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
    if (json.Length > 4 * 1024 * 1024) return 3;
    File.WriteAllText(args[2], json);
    return 0;
}
catch { return 1; }

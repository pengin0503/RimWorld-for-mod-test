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
    if (System.Text.Encoding.UTF8.GetByteCount(json) > 4 * 1024 * 1024) return 4;
    File.WriteAllText(args[2], json);
    return 0;
}
catch (BudgetExceededException) { return 4; }
catch { return 1; }

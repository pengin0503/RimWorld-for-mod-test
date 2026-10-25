using System.Text.Json;

namespace RimWorldValidation.Worker;

/// <summary>
/// The Controller-to-Worker request (recordType rwmtWorkerRequest, schemaVersion 1).
/// The Controller validates the user's modValidationRequest and writes this
/// narrower, fully resolved file; the Worker trusts only these fields.
/// </summary>
public sealed class WorkerRequest
{
    public const string RecordType = "rwmtWorkerRequest";

    public required string RunId { get; init; }
    public required string Nonce { get; init; }
    public required string HostDir { get; init; }
    public required string UserDataDir { get; init; }
    public required string EventsPath { get; init; }
    public required string ResultPath { get; init; }
    public required string Language { get; init; }
    public required double DeadlineSeconds { get; init; }
    public required int MaxDiagnostics { get; init; }
    public required int MaxMessageBytes { get; init; }
    public required long MaxEventBytes { get; init; }
    public required IReadOnlyList<string> ExpectedModOrder { get; init; }
    public required JsonElement Expectations { get; init; }
    public MapRequest? Map { get; init; }

    public static WorkerRequest Load(string path)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllBytes(path));
        JsonElement root = doc.RootElement;
        if (Str(root, "recordType") != RecordType || root.GetProperty("schemaVersion").GetInt32() != 1)
        {
            throw new InvalidDataException("unsupported worker request");
        }
        JsonElement limits = root.GetProperty("limits");
        return new WorkerRequest
        {
            RunId = Str(root, "runId"),
            Nonce = Str(root, "nonce"),
            HostDir = Str(root, "hostDir"),
            UserDataDir = Str(root, "userDataDir"),
            EventsPath = Str(root, "eventsPath"),
            ResultPath = Str(root, "resultPath"),
            Language = Str(root, "language"),
            DeadlineSeconds = limits.GetProperty("deadlineSeconds").GetDouble(),
            MaxDiagnostics = limits.GetProperty("diagnostics").GetInt32(),
            MaxMessageBytes = limits.GetProperty("messageBytes").GetInt32(),
            MaxEventBytes = limits.GetProperty("eventBytes").GetInt64(),
            ExpectedModOrder = root.GetProperty("expectedModOrder").EnumerateArray().Select(e => e.GetString()!).ToArray(),
            Expectations = root.GetProperty("expectations").Clone(),
            Map = MapRequest.Load(root),
        };
    }

    private static string Str(JsonElement element, string name)
    {
        return element.GetProperty(name).GetString() ?? throw new InvalidDataException($"{name} must be a string");
    }
}

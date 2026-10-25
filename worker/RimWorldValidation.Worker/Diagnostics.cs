using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace RimWorldValidation.Worker;

/// <summary>
/// Captures engine and game log events (Verse.Log goes through the same logging
/// system as category "Verse") into an append-only JSON Lines file. Every line is
/// flushed so a crash or kill still leaves the events written so far. Limits are
/// enforced here and the number of dropped events is reported, never hidden.
/// </summary>
public sealed class Diagnostics : ILoggerProvider
{
    private readonly object _lock = new();
    private readonly FileStream _stream;
    private readonly Stopwatch _clock;
    private readonly int _maxEvents;
    private readonly int _maxMessageBytes;
    private readonly long _maxBytes;
    private long _bytes;
    private int _sequence;

    public Diagnostics(string path, Stopwatch clock, int maxEvents, int maxMessageBytes, long maxBytes)
    {
        _stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        _clock = clock;
        _maxEvents = maxEvents;
        _maxMessageBytes = maxMessageBytes;
        _maxBytes = maxBytes;
    }

    /// <summary>Best-effort label of the phase the main thread is in; events from other threads may lag.</summary>
    public static volatile string Stage = "workerStart";

    public int Written { get; private set; }
    public int Dropped { get; private set; }
    public int Truncated { get; private set; }
    public Dictionary<string, int> CountsByLevel { get; } = new();

    public ILogger CreateLogger(string categoryName) => new Logger(this, categoryName);

    public void Record(string level, string category, string message, Exception? exception)
    {
        string body = exception == null ? message : $"{message}\n{exception}";
        bool truncated = false;
        if (Encoding.UTF8.GetByteCount(body) > _maxMessageBytes)
        {
            body = TruncateUtf8(body, _maxMessageBytes);
            truncated = true;
        }
        lock (_lock)
        {
            CountsByLevel[level] = CountsByLevel.GetValueOrDefault(level) + 1;
            if (Written >= _maxEvents || _bytes >= _maxBytes)
            {
                Dropped++;
                return;
            }
            var buffer = new MemoryStream();
            using (var json = new Utf8JsonWriter(buffer))
            {
                json.WriteStartObject();
                json.WriteNumber("seq", ++_sequence);
                json.WriteNumber("t", Math.Round(_clock.Elapsed.TotalSeconds, 3));
                json.WriteString("level", level);
                json.WriteString("category", category);
                json.WriteString("stage", Stage);
                json.WriteString("thread", Environment.CurrentManagedThreadId == MainThreadId ? "main" : "other");
                json.WriteString("message", body);
                if (exception != null)
                {
                    json.WriteString("exceptionType", exception.GetType().FullName);
                }
                json.WriteBoolean("truncated", truncated);
                json.WriteEndObject();
            }
            buffer.WriteByte((byte)'\n');
            _stream.Write(buffer.GetBuffer(), 0, (int)buffer.Length);
            _stream.Flush();
            _bytes += buffer.Length;
            Written++;
            if (truncated)
            {
                Truncated++;
            }
        }
    }

    public static int MainThreadId { get; set; }

    public void Dispose()
    {
        lock (_lock)
        {
            _stream.Dispose();
        }
    }

    internal static string TruncateUtf8(string text, int maxBytes)
    {
        int length = Math.Min(text.Length, maxBytes);
        while (length > 0 && Encoding.UTF8.GetByteCount(text.AsSpan(0, length)) > maxBytes)
        {
            length = (int)(length * 0.9);
        }
        return text[..length];
    }

    private sealed class Logger(Diagnostics owner, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        // Debug/Trace engine chatter stays in the raw file log; Information is kept
        // for game messages (Verse.Log.Message) because mods report problems there too.
        public bool IsEnabled(LogLevel logLevel) =>
            logLevel >= LogLevel.Warning || (logLevel == LogLevel.Information && category == "Verse");

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel))
            {
                return;
            }
            string level = logLevel switch
            {
                LogLevel.Critical => "error",
                LogLevel.Error => "error",
                LogLevel.Warning => "warning",
                _ => "info",
            };
            owner.Record(level, category, formatter(state, exception), exception);
        }
    }
}

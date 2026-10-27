using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace DpaCsvExporter;

public static class CsvFormat
{
    public static string Escape(string? value, bool treatAsText = true)
    {
        string result = value ?? "";
        // Prevent spreadsheet formula injection for labels supplied by third-party mods.
        if (treatAsText && result.Length > 0)
        {
            string trimmed = result.TrimStart(' ', '\t', '\r', '\n');
            if (trimmed.Length > 0 && "=+-@".IndexOf(trimmed[0]) >= 0)
                result = "'" + result;
            else if (result[0] == '\t' || result[0] == '\r' || result[0] == '\n')
                result = "'" + result;
        }
        return result.IndexOfAny(new[] { ',', '"', '\r', '\n' }) >= 0
            ? '"' + result.Replace("\"", "\"\"") + '"' : result;
    }

    public static string Line(IEnumerable<string?> columns, ISet<int>? numericColumns = null)
        => string.Join(",", columns.Select((value, i) => Escape(value, numericColumns?.Contains(i) != true)));

    public static string Number(double value)
        => double.IsNaN(value) || double.IsInfinity(value)
            ? "" : value.ToString("0.#########", CultureInfo.InvariantCulture);
    public static string Number(int value) => value.ToString(CultureInfo.InvariantCulture);
}

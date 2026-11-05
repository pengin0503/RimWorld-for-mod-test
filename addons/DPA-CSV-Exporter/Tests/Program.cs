using DpaCsvExporter;
static void Equal(string want, string got) { if (want != got) throw new Exception($"Expected <{want}> got <{got}>"); }
Equal("plain", CsvFormat.Escape("plain"));
Equal("\"a,b\"", CsvFormat.Escape("a,b"));
Equal("\"a\"\"b\"", CsvFormat.Escape("a\"b"));
Equal("\"a\r\nb\"", CsvFormat.Escape("a\r\nb"));
Equal("'=SUM(A1)", CsvFormat.Escape("=SUM(A1)"));
Equal("'+cmd", CsvFormat.Escape("+cmd"));
Equal("'@formula", CsvFormat.Escape("@formula"));
Equal("'  =SUM(A1)", CsvFormat.Escape("  =SUM(A1)"));
Equal("0.25", CsvFormat.Number(0.25));
Equal("", CsvFormat.Number(double.NaN));
Equal("\"値, 値\",3.5", CsvFormat.Line(new string?[] { "値, 値", "3.5" }, new HashSet<int> { 1 }));
Console.WriteLine("11 CSV serialization tests passed");

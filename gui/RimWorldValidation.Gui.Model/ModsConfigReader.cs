using System.Xml;
using System.Xml.Linq;

namespace RimWorldValidation.Gui.Model;

/// <summary>Reads the active mod order from the game's own ModsConfig.xml. Read only: the GUI never writes it.</summary>
public static class ModsConfigReader
{
    public static IReadOnlyList<string> ReadActive(string path)
    {
        XDocument document;
        try
        {
            document = XDocument.Load(path);
        }
        catch (XmlException e)
        {
            throw new InvalidDataException($"{path} is not readable XML: {e.Message}", e);
        }
        return document.Root?.Element("activeMods")?.Elements("li")
            .Select(li => li.Value.Trim().ToLowerInvariant())
            .Where(id => id.Length > 0)
            .ToList() ?? [];
    }
}

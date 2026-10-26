namespace RimWorldValidation.Worker;

internal sealed class CategoryTreeLimitException() : Exception("cyclic or oversized ingredient category tree");

/// <summary>Validate the whole raw category graph before calling recursive game predicates.</summary>
internal static class BoundedCategoryTree
{
    internal sealed record Entry(object Node, int ParentIndex, bool Visible);

    internal static List<Entry> Observe(object root, Func<object, IEnumerable<object>> children,
        Func<object, bool> visible)
    {
        var entries = new List<Entry>();
        var path = new HashSet<object>(ReferenceEqualityComparer.Instance);
        Preflight(root, -1, 0);
        // Only after every subtree is bounded may a game predicate enumerate descendants.
        for (int i = 1; i < entries.Count; i++)
        {
            Entry entry = entries[i];
            entries[i] = entry with { Visible = entries[entry.ParentIndex].Visible && visible(entry.Node) };
        }
        return entries;

        void Preflight(object node, int parentIndex, int depth)
        {
            if (depth > 128 || entries.Count >= 20000 || !path.Add(node))
            {
                throw new CategoryTreeLimitException();
            }
            int index = entries.Count;
            entries.Add(new Entry(node, parentIndex, true));
            foreach (object child in children(node))
            {
                Preflight(child, index, depth + 1);
            }
            path.Remove(node);
        }
    }
}

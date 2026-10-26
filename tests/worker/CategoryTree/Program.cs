using RimWorldValidation.Worker;

int checks = 0;
void Require(bool ok, string message)
{
    if (!ok) throw new Exception(message);
    checks++;
}

List<BoundedCategoryTree.Entry> Observe(Node root) => BoundedCategoryTree.Observe(root,
    node => ((Node)node).Children, node => ((Node)node).Shown);
Node Chain(int depth)
{
    var root = new Node();
    var node = root;
    for (int i = 0; i < depth; i++)
    {
        var child = new Node();
        node.Children.Add(child);
        node = child;
    }
    return root;
}
void RejectBeforePredicate(Node root, string name)
{
    bool predicateCalled = false, rejected = false;
    try
    {
        BoundedCategoryTree.Observe(root, node => ((Node)node).Children,
            _ => { predicateCalled = true; return true; });
    }
    catch (CategoryTreeLimitException) { rejected = true; }
    Require(rejected, name + " must be rejected");
    Require(!predicateCalled, name + " must be rejected before the game predicate is called");
}

var ordinary = new Node();
var hidden = new Node { Shown = false };
hidden.Children.Add(new Node());
ordinary.Children.Add(hidden);
ordinary.Children.Add(new Node());
var rows = Observe(ordinary);
Require(rows.Count == 4 && rows[0].Visible && !rows[1].Visible && !rows[2].Visible && rows[3].Visible,
    "category ancestry must propagate actual visibility");
Require(Observe(Chain(128)).Count == 129, "depth 128 must be accepted");
RejectBeforePredicate(Chain(129), "depth 129");
var wide = new Node();
for (int i = 0; i < 19999; i++) wide.Children.Add(new Node());
Require(Observe(wide).Count == 20000, "20000 total nodes must be accepted");
wide.Children.Add(new Node());
RejectBeforePredicate(wide, "20001 nodes");
var cycle = new Node();
var next = new Node();
cycle.Children.Add(next);
next.Children.Add(cycle);
RejectBeforePredicate(cycle, "cycle");
Console.WriteLine($"PASS: {checks} category traversal assertions (no game files)");

sealed class Node
{
    public List<object> Children { get; } = [];
    public bool Shown { get; init; } = true;
}

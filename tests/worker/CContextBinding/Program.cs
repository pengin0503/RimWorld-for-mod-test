using RWMT.CContext;
var bill = new Bill();
var position = new Position(-1);
var actual = (Dialog)DialogConstructor.Create(typeof(Dialog), typeof(Bill), typeof(Position), bill, position);
if (!ReferenceEquals(actual.Bill, bill) || actual.Position != position) throw new Exception("verified constructor arguments changed");
try { DialogConstructor.Create(typeof(OldDialog), typeof(Bill), typeof(Position), bill, position); throw new Exception("old one-argument API accepted"); }
catch (MissingMethodException) { }
Console.WriteLine("verified two-argument dialog constructor checks passed");
public sealed class Bill { }
public readonly record struct Position(int Value);
public sealed class Dialog(Bill bill, Position position)
{
    public Bill Bill { get; } = bill;
    public Position Position { get; } = position;
}
public sealed class OldDialog { public OldDialog(Bill bill) { } }

from zk.formats.csharp_project import DISCLAIMER, report, summarize, summarize_source

GAME = '''using System;
[assembly: AssemblyVersion("1.0")]
namespace ZodiacKnights.Game
{
    // a comment with { braces
    [Serializable]
    public class Hero : Unit
    {
        [Token(Token = "0x4000001")]
        private int hp = Compute(1);
        private string s = "}{";
        public static event Action Died;
        public int Hp { get; private set; }
        public int Max => 10;
        public string Name { get { return name; } set => name = value; }
        public int this[int i] { get { throw null; } }
        public Hero() : base(1) { }
        public void Attack(int x = 1) { hp -= x; if (x > 1) { Log($"{x}"); } }
        public int Stub() { throw null; }
        public T Get<T>() where T : class { return default(T); }
        public void Nope() => throw new NotImplementedException("x");
        public extern void Native();
        public static bool operator ==(Hero a, Hero b) { return true; }
        public Data D = new Data { A = 1 };
        public class Inner<T> where T : struct
        {
            private void Local() { void F() { } F(); }
        }
        public delegate void OnHit(int dmg);
        public enum Kind { A = 1, B }
    }
    public interface IUnit { void Act(); int Speed { get; } }
    public abstract class Unit { protected abstract void Tick(); }
    public struct Point { public int X; }
}
'''


def test_counts_types_methods_and_bodies():
    s = summarize_source(GAME)
    # Hero, Inner, OnHit, Kind, IUnit, Unit, Point
    assert s["types"] == 7
    # Hp get/set, Max, Name get/set, indexer get, ctor, Attack, Stub, Get, Nope, Native, ==, Local, Act, Speed get, Tick
    assert s["methods"] == 17
    # none: Hp get/set, Native, Act, Speed get, Tick; stub: indexer get, ctor, Stub, Get, Nope
    assert s["bodies"] == {"none": 6, "reconstructed": 6, "stub": 5}


def test_file_scoped_namespace_and_records():
    s = summarize_source("namespace A;\npublic record Pos(int X, int Y);\npublic record struct P { public void M() { } }\n")
    assert s == {"types": 2, "methods": 1, "bodies": {"none": 0, "reconstructed": 0, "stub": 1}}


def test_summarize_groups_by_assembly_and_sorts():
    files = {"B/X.cs": "class X { void M() { Go(); } }", "A/Properties/AssemblyInfo.cs": "[assembly: A]\n",
             "A/N/Y.cs": "class Y { }", "A/A.csproj": "<Project/>", "loose.cs": "class Z { }"}
    out = summarize(files)
    assert list(out) == ["A", "B"]
    assert out["A"] == {"types": 1, "methods": 0, "bodies": {"none": 0, "reconstructed": 0, "stub": 0}}
    assert out["B"]["bodies"]["reconstructed"] == 1


def test_crlf_and_report_shape():
    s = summarize_source("class X\r\n{\r\n    void M()\r\n    {\r\n    }\r\n}\r\n")
    assert s["bodies"]["stub"] == 1
    r = report({"A": s}, {"name": "ilspycmd", "version": "11.2"}, "cpp2il")
    assert r["input"] == "cpp2il" and r["disclaimer"] == DISCLAIMER and r["assemblies"]["A"] == s


CPP2IL_STUBS = """namespace G;
public class S : IEnumerator
{
    public int P { get { return field; } set { field = value; } }
    public float F => 0f;
    public string A() { return null; }
    public bool B(out string s, out int n) { s = null; n = default; return false; }
    public long C() { return 0L; }
    public double D() { return 0.0; }
    void IEnumerator.Reset() { this.Reset(); }
    public bool Real(int x) { return x > 10; }
    public int Ten() { return 10; }
}
"""


def test_cpp2il_stub_markers():
    r = summarize_source(CPP2IL_STUBS)
    assert r["types"] == 1
    assert r["methods"] == 10
    assert r["bodies"] == {"none": 2, "reconstructed": 2, "stub": 6}

import pytest

from zk.formats import csharp_dump

DUMP = """\
// Image 0: mscorlib.dll - 0
// Image 1: ZodiacKnights.Game.dll - 2

// Namespace: System
public class Object // TypeDefIndex: 0
{
\t// Methods

\t// RVA: 0x1 Offset: 0x1 VA: 0x1
\tpublic void .ctor() { }

\t// RVA: 0x2 Offset: 0x2 VA: 0x2
\tpublic virtual string ToString() { }
}

// Namespace: 
internal class <Module> // TypeDefIndex: 1
{
}

// Namespace: 
private sealed class Hero.<>c // TypeDefIndex: 5
{
\t// Methods
\tpublic void .ctor() { }
\tinternal void <Use>b__0_0() { }
}

// Namespace: ZK.Game
[Serializable]
public class Hero<T> : Object // TypeDefIndex: 2
{
\t// Fields
\tprivate int hp; // 0x10
\tprivate string tag = "a{b(c"; // 0x18

\t// Properties
\tpublic int Hp { get; }

\t// Events
\tpublic event Action Died;

\t// Methods

\t// RVA: 0x8 Offset: 0x8 VA: 0x8
\tpublic int get_Hp() { }

\t// RVA: 0x9 Offset: 0x9 VA: 0x9
\tpublic void add_Died(Action value) { }

\t// RVA: 0xA Offset: 0xA VA: 0xA
\tpublic void remove_Died(Action value) { }

\t// RVA: 0x3 Offset: 0x3 VA: 0x3
\tpublic void Attack(int x) { }

\t// RVA: 0x4 Offset: 0x4 VA: 0x4
\tpublic void Use<U>(U u) where U : class { }
\t/* GenericInstMethod :
\t|
\t|-RVA: 0x5 Offset: 0x5 VA: 0x5
\t|-Hero<int>.Attack(int x)
\t*/
}

// Namespace: 
private class Hero.Inner<A, B> // TypeDefIndex: 3
{
\t// Methods
\tpublic void .ctor() { }
}

// Namespace: ZK.Game
public enum Element // TypeDefIndex: 4
{
\tpublic int value__; // 0x10
\tpublic const Element Fire = 0;
}
"""

INSPECTOR = {
    "cs/mscorlib.cs": """\
namespace System
{
\tpublic class Object // TypeDefIndex: 0
\t{
\t\tpublic Object() {} // 0x1
\t\tpublic virtual string ToString() => default; // 0x2
\t}
}
internal class <Module> // TypeDefIndex: 1
{
}
""",
    "cs/ZodiacKnights.Game.cs": """\
namespace ZK.Game
{
\t[Serializable]
\tpublic class Hero<T> : Object // TypeDefIndex: 2
\t{
\t\tprivate int hp; // 0x10
\t\tprivate string tag = "}";
\t\tpublic int Hp { [CompilerGenerated] get; } // 0x08-0x09
\t\tpublic event Action Died {
\t\t\tadd; // 0x09-0x0A
\t\t\tremove; // 0x0A-0x0B
\t\t}
\t\t[CompilerGenerated]
\t\tprivate sealed class __c // TypeDefIndex: 5
\t\t{
\t\t\tpublic __c(); // 0x06-0x07
\t\t\tinternal void _Use_b__0_0(); // 0x07-0x08
\t\t}
\t\tpublic void Attack(int x) {} // 0x3
\t\tpublic void Use<U>(U u) where U : class {} // 0x4
\t\tprivate class Inner<A, B> // TypeDefIndex: 3
\t\t{
\t\t\tpublic Inner() {} // 0x5
\t\t}
\t}
\tpublic enum Element // TypeDefIndex: 4
\t{
\t\tFire = 0
\t}
}
""",
}

EXPECTED = {
    "assemblies": {
        "ZodiacKnights.Game": {
            "types": 4,
            "methods": 8,
            "classes": {"ZK.Game.Element": 0, "ZK.Game.Hero`1": 5, "ZK.Game.Hero`1.Inner`2": 1,
                        "ZK.Game.Hero`1.__c": 2},
        },
        "mscorlib": {"types": 1, "methods": 2, "classes": {"System.Object": 2}},
    }
}


def test_dumper_summary():
    assert csharp_dump.summarize_dumper(DUMP) == EXPECTED


def test_inspector_summary_matches_dumper():
    assert csharp_dump.summarize_inspector(INSPECTOR) == EXPECTED


def test_summary_keys_are_sorted():
    s = csharp_dump.summarize_dumper(DUMP)
    assert list(s["assemblies"]) == sorted(s["assemblies"])


def test_dumper_needs_image_headers():
    with pytest.raises(ValueError, match="Image"):
        csharp_dump.summarize_dumper("public class A // TypeDefIndex: 0\n{\n}\n")


@pytest.mark.parametrize(
    ("raw", "norm"),
    [("Hero<T>", "Hero`1"), ("Outer<A, B>.Inner<C>", "Outer`2.Inner`1"), ("<Module>", "_Module_"),
     ("<>c__DisplayClass0_0", "__c__DisplayClass0_0"),
     ("<PrivateImplementationDetails>.__StaticArrayInitTypeSize=12",
      "_PrivateImplementationDetails_.__StaticArrayInitTypeSize_12"),
     ("Dict<K, List<V>>", "Dict`2"), ("Plain`1", "Plain`1")],
)
def test_normalize(raw, norm):
    assert csharp_dump.normalize(raw) == norm


def test_assembly_name():
    assert csharp_dump.assembly_name("ZodiacKnights.Game.dll") == "ZodiacKnights.Game"
    assert csharp_dump.assembly_name("mscorlib.cs") == "mscorlib"


def test_inspector_field_named_like_accessor_is_not_a_method():
    text = """\
namespace ZK
{
\tpublic class Box // TypeDefIndex: 0
\t{
\t\tpublic int add; // 0x10
\t\tprivate bool set;
\t\tpublic int Hp { get; set; } // 0x1-0x2
\t\tpublic event Action Died {
\t\t\tadd; // 0x3
\t\t\tremove; // 0x4
\t\t}
\t}
}
"""
    s = csharp_dump.summarize_inspector({"Game.cs": text})
    assert s["assemblies"]["Game"]["classes"] == {"ZK.Box": 4}


def test_inspector_indexer_accessors_with_bodies_count_as_methods():
    text = """\
namespace ZK
{
\tpublic class Bits // TypeDefIndex: 0
\t{
\t\tpublic bool this[int index] { get => default; set {} } // 0x1-0x2
\t\tpublic int this[string key] { get => default; } // 0x3-0x4
\t\tpublic int Size { get; } // 0x5-0x6
\t}
}
"""
    s = csharp_dump.summarize_inspector({"Game.cs": text})
    assert s["assemblies"]["Game"]["classes"] == {"ZK.Bits": 4}

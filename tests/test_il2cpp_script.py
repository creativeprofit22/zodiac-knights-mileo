import pytest

from zk.formats import il2cpp_script


def _script():
    return {
        "ScriptMethod": [{"Address": 4096, "Name": "Hero$$Attack", "Signature": "void f();", "TypeSignature": "vi"}],
        "ScriptString": [{"Address": 8192, "Value": "hi"}],
        "ScriptMetadata": [{"Address": 12288, "Name": "Hero_TypeInfo", "Signature": "Hero_c*"},
                           {"Address": 12296, "Name": "x", "Signature": None}],
        "ScriptMetadataMethod": [{"Address": 16384, "Name": "Method$Hero.Attack()", "MethodAddress": 4096}],
        "Addresses": [4096, 4100],
    }


def test_valid_script_counts():
    s = il2cpp_script.validate(_script())
    assert s.as_dict() == {"methods": 1, "strings": 1, "metadata": 2, "metadata_methods": 1, "addresses": 2}


def test_missing_section():
    data = _script()
    del data["ScriptString"]
    with pytest.raises(ValueError, match=r"^\$\.ScriptString: missing"):
        il2cpp_script.validate(data)


def test_wrong_type():
    data = _script()
    data["Addresses"] = {"a": 1}
    with pytest.raises(ValueError, match=r"^\$\.Addresses: expected a list"):
        il2cpp_script.validate(data)


def test_bad_nested_entry():
    data = _script()
    data["ScriptMethod"].append({"Address": "0x10", "Name": "n", "Signature": "s", "TypeSignature": "v"})
    with pytest.raises(ValueError, match=r"^\$\.ScriptMethod\[1\]\.Address: expected int, got str"):
        il2cpp_script.validate(data)


def test_bool_is_not_an_address():
    data = _script()
    data["Addresses"].append(True)
    with pytest.raises(ValueError, match=r"\$\.Addresses\[2\]"):
        il2cpp_script.validate(data)


def test_top_level_not_object():
    with pytest.raises(ValueError, match=r"^\$: expected an object"):
        il2cpp_script.validate([])


def _owners_script():
    return {
        "ScriptMethod": [
            {"Name": "ZodiacKnights.Game.AdminLiveOps$$Start"},
            {"Name": "ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext"},
            {"Name": "ChatModal$$Awake"},
            {"Name": "ChatModal.ChatEntry$$.ctor"},
            {"Name": "System.Collections.Generic.List<ZodiacKnights.Logic.Hero>$$Add"},
            {"Name": "ZodiacKnights.Logic.Pool<T>.<>c$$<Get>b__1_0"},
            {"Name": "no_owner"},
        ],
        "ScriptMetadata": [
            {"Name": "ZodiacKnights.Logic.Hero_TypeInfo"},
            {"Name": "ZodiacKnights.Logic.Hero[]_TypeInfo"},
            {"Name": "ZodiacKnights.Logic.Pool<int>_TypeInfo"},
            {"Name": "StringLiteral_1"},
        ],
    }


def test_strip_generics_keeps_compiler_generated_names():
    assert il2cpp_script.strip_generics("List<Dictionary<int, A.B>>") == "List"
    assert il2cpp_script.strip_generics("A.<Run>d__5") == "A.<Run>d__5"
    assert il2cpp_script.strip_generics("A<T>.<>c") == "A.<>c"


def test_type_owners():
    owners = il2cpp_script.type_owners(_owners_script())
    assert owners == {
        "ZodiacKnights.Game.AdminLiveOps", "ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54",
        "ChatModal", "ChatModal.ChatEntry", "System.Collections.Generic.List", "ZodiacKnights.Logic.Pool.<>c",
        "ZodiacKnights.Logic.Hero", "ZodiacKnights.Logic.Pool",
    }


@pytest.mark.parametrize(("name", "expected"), [
    ("ZodiacKnights.Game.AdminLiveOps.<AuthenticateCo>d__54$$MoveNext", ("ZodiacKnights.Game", "AdminLiveOps")),
    ("ZodiacKnights.Game.AdminLiveOps$$Start", ("ZodiacKnights.Game", "AdminLiveOps")),
    ("ChatModal.ChatEntry$$.ctor", ("", "ChatModal")),
    ("System.Collections.Generic.List<ZodiacKnights.Logic.Hero>$$Add", ("System.Collections.Generic", "List")),
    ("ZodiacKnights.Logic.Pool<T>.<>c$$<Get>b__1_0", ("ZodiacKnights.Logic", "Pool")),
    ("ZodiacKnights.Logic.Hero$$get_Hp", ("ZodiacKnights.Logic", "Hero")),
    ("Unknown.Type$$Run", None),
    ("no_owner", None),
])
def test_resolve_class(name, expected):
    assert il2cpp_script.resolve_class(name, il2cpp_script.type_owners(_owners_script())) == expected

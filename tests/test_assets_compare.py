from zk.formats.csharp_dump_diff import compare, tag_used


def _summary(classes):
    return {"assemblies": {a: {"types": len(c), "methods": sum(c.values()), "classes": c}
                           for a, c in classes.items()}}


def test_used_differences_are_unexplained_unless_a_rule_matches():
    a = _summary({"UI": {"UI.Image": 10, "UI.Helper": 2, "UI.Gone": 1}})
    b = _summary({"UI": {"UI.Image": 11, "UI.Helper": 3, "UI.New": 0}})
    r = tag_used(compare(a, b, ["UI"]), {"UI": ["UI.Image"]})
    ui = r["assemblies"]["UI"]
    assert ui["differences"]["UI.Image"] == {"counts": [10, 11], "used": True, "rule": None}
    assert ui["differences"]["UI.Helper"]["used"] is False
    assert ui["unexplained"] == ["UI.Image"] and r["unexplained"] == 1
    ruled = tag_used(compare(a, b, ["UI"]), {"UI": ["UI.Image"]}, {r"UI\.Im.*": "accessor counting"})
    assert ruled["assemblies"]["UI"]["differences"]["UI.Image"]["rule"] == "accessor counting"
    assert ruled["unexplained"] == 0


def test_type_gaps_from_one_sided_classes_are_accounted_for():
    a = _summary({"UI": {"A": 1, "B": 1}})
    b = _summary({"UI": {"A": 1, "B": 1, "C": 0, "D": 0}})
    r = tag_used(compare(a, b, ["UI"]), {})
    assert r["assemblies"]["UI"]["type_count_residual"] == 0 and r["unexplained"] == 0


def test_unattributed_type_count_gap_is_unexplained():
    a = _summary({"UI": {"A": 1}})
    b = {"assemblies": {"UI": {"types": 3, "methods": 1, "classes": {"A": 1}}}}
    r = tag_used(compare(a, b, ["UI"]), {})
    assert r["assemblies"]["UI"]["type_count_residual"] == -2
    assert r["assemblies"]["UI"]["unexplained"] == ["<type count residual -2>"] and r["unexplained"] == 1

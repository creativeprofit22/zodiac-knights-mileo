import json
import struct

import pytest

from zk.formats import il2cpp_metadata, scripting_assemblies, unity_serialized


def _meta(magic, version):
    return struct.pack("<Ii", magic, version) + b"\0" * 8


def test_metadata_known_version():
    h = il2cpp_metadata.parse_header(_meta(0xFAB11BAF, 39))
    assert (h.magic_hex, h.version, h.encrypted, h.warnings) == ("0xFAB11BAF", 39, False, ())


def test_metadata_unknown_version_is_a_warning():
    h = il2cpp_metadata.parse_header(_meta(0xFAB11BAF, 41))
    assert h.version == 41 and not h.encrypted
    assert len(h.warnings) == 1 and "41" in h.warnings[0]


def test_metadata_bad_magic_means_encrypted():
    h = il2cpp_metadata.parse_header(_meta(0x12345678, 39))
    assert h.encrypted and h.version is None and "0x12345678" in h.warnings[0]


def test_metadata_short():
    h = il2cpp_metadata.parse_header(b"\xaf\x1b")
    assert h.encrypted and h.version is None and h.warnings


def _serialized(fmt, version, at):
    head = bytearray(at + 32)
    struct.pack_into(">I", head, 0x08, fmt)
    head[at:at + len(version) + 1] = version.encode() + b"\0"
    return bytes(head)


def test_serialized_format_22_reads_version_at_0x30():
    h = unity_serialized.parse_header(_serialized(22, "6000.3.2f1", 0x30))
    assert h == unity_serialized.SerializedHeader(22, "6000.3.2f1")


def test_serialized_format_17_reads_version_at_0x14():
    h = unity_serialized.parse_header(_serialized(17, "2019.4.40f1", 0x14))
    assert h == unity_serialized.SerializedHeader(17, "2019.4.40f1")


def test_serialized_version_at_wrong_offset_is_rejected():
    assert unity_serialized.parse_header(_serialized(22, "6000.3.2f1", 0x14)) is None


@pytest.mark.parametrize("head", [b"", b"\0" * 8, b"UnityFS\0" + b"\xff" * 80, b"\0" * 0x50])
def test_serialized_garbage(head):
    assert not unity_serialized.is_serialized_file(head)


def test_scripting_assemblies_game_filter():
    sa = scripting_assemblies.parse(json.dumps({
        "names": ["UnityEngine.dll", "ZodiacKnights.Logic.dll", "Unity.Burst.dll", "System.Core.dll",
                  "mscorlib.dll", "ZodiacKnights.Game.dll", "Mono.Security.dll", "Engine.Thing.dll"],
        "types": [2, 16, 16, 16, 16, 16, 16, 2]}))
    assert scripting_assemblies.game_assemblies(sa) == ["ZodiacKnights.Game", "ZodiacKnights.Logic"]


@pytest.mark.parametrize("doc", [
    {"names": ["a.dll"], "types": []},
    {"names": "a.dll", "types": [16]},
    {"names": ["a.dll"], "types": ["16"]},
    [],
])
def test_scripting_assemblies_rejects_bad_shape(doc):
    with pytest.raises(ValueError):
        scripting_assemblies.parse(json.dumps(doc))

"""Fake il2cpp_dump adapter B: same port, different output, to prove config-only swapping."""
from tests.fakes.fake_dump_a import FakeDump

PORT = "il2cpp_dump"


class FakeDumpB(FakeDump):
    tag = "b"


def create(cfg):
    return FakeDumpB()

"""Fake il2cpp_dump adapter B: same port, different output, to prove config-only swapping."""
from tests.fakes.fake_dump_a import GAME, FakeDump

PORT = "il2cpp_dump"


class FakeDumpB(FakeDump):
    tag = "b"
    game = {**GAME, "ZodiacKnights.Logic": {"ZK.Rules": 5}}  # same types, one more method


def create(cfg):
    return FakeDumpB()

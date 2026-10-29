"""Fake il2cpp_dump adapter that never emits ZodiacKnights.Logic.dll."""
from tests.fakes.fake_dump_a import GAME, FakeDump

PORT = "il2cpp_dump"


class FakeDumpMissing(FakeDump):
    tag = "missing"
    game = {k: v for k, v in GAME.items() if k != "ZodiacKnights.Logic"}


def create(cfg):
    return FakeDumpMissing()

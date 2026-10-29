"""Fake il2cpp_crosscheck adapter: GAME's summary; option `extra_type` adds a type to ZodiacKnights.Game."""
import json

from tests.fakes.fake_dump_a import GAME, summary

PORT = "il2cpp_crosscheck"


class FakeCrosscheck:
    def __init__(self, extra_type):
        self.extra_type = extra_type

    def crosscheck(self, binary, metadata, out):
        game = {**GAME}
        if self.extra_type:
            game["ZodiacKnights.Game"] = {**game["ZodiacKnights.Game"], self.extra_type: 0}
        (out / "summary.json").write_text(json.dumps(summary(game)), encoding="utf-8")
        return {"by": "crosscheck"}


def create(cfg):
    return FakeCrosscheck(cfg.options.get(PORT, {}).get("extra_type", ""))

"""Claims il2cpp_dump but lacks dump(): must fail the Protocol check."""
PORT = "il2cpp_dump"


class NotADumper:
    def decompile(self, apk, out):
        return {}


def create(cfg):
    return NotADumper()

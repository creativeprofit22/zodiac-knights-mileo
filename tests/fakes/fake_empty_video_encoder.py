"""Fake video_encoder adapter that breaks the contract: it writes an empty encoded.mp4."""
PORT = "video_encoder"


class EmptyVideoEncoder:
    def encode(self, frames_dir, fps, out):
        out.write_bytes(b"")
        return {"tool": "empty"}


def create(cfg):
    return EmptyVideoEncoder()

"""Fake video_encoder adapter: writes a tiny encoded.mp4 naming how many frames it was given."""
PORT = "video_encoder"


class FakeVideoEncoder:
    def encode(self, frames_dir, fps, out):
        n = len(list(frames_dir.glob("frame_*.jpg")))
        out.write_bytes(f"fake {n} frames @ {fps}".encode())
        return {"tool": "fake", "frames": n, "fps": fps}


def create(cfg):
    return FakeVideoEncoder()

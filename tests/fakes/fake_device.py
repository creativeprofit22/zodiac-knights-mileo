"""Fake device_source adapter: 'pulls' a synthetic Unity 6 IL2CPP APK (no game data).

The version label comes from [options.device_source] version, so tests can feed bad labels.
`abi` is the reported primary ABI; `split_abi` moves that ABI's lib/ folder into split_config.<abi>.apk, as Play splits do.
"""
import json
import shutil
import struct
import zipfile

PORT = "device_source"
ABIS = ("arm64-v8a", "armeabi-v7a", "x86_64")
UNITY = "6000.3.2f1"


def serialized(fmt=22, version=UNITY):
    head = bytearray(0x30 if fmt >= 22 else 0x14)
    struct.pack_into(">I", head, 0x08, fmt)
    return bytes(head) + version.encode() + b"\0" + bytes(32)


def metadata(version=39, magic=0xFAB11BAF):
    return struct.pack("<Ii", magic, version) + bytes(56)


def scripting_assemblies():
    names = ["UnityEngine.CoreModule.dll", "Assembly-CSharp.dll", "Unity.Burst.dll", "System.Core.dll",
             "ZodiacKnights.Logic.dll", "ZodiacKnights.Game.dll", "mscorlib.dll"]
    types = [2, 16, 16, 16, 16, 16, 16]
    return json.dumps({"names": names, "types": types})


def apk_files(metadata_version=39, unity=UNITY):
    data = "assets/bin/Data/"
    files = {f"lib/{abi}/libil2cpp.so": b"\x7fELF" for abi in ABIS}
    files.update({
        "lib/arm64-v8a/libunity.so": b"\x7fELF",
        data + "Managed/Metadata/global-metadata.dat": metadata(metadata_version),
        data + "globalgamemanagers": serialized(version=unity),
        data + "globalgamemanagers.assets.split0": serialized(),
        data + "globalgamemanagers.assets.split1": b"\x00" * 64,
        data + "globalgamemanagers.assets.split2": b"\x00" * 64,
        data + "level0": serialized(),
        data + "sharedassets0.assets": serialized(),
        data + "00135d9dada8eb8408d9b020f7597684": serialized(),
        data + "00135d9dada8eb8408d9b020f7597684.resource": b"\x00" * 16,
        data + "002c60d528087a04480d2f2375fdbfba": serialized(),
        data + "002c60d528087a04480d2f2375fdbfba.resource": b"\x00" * 16,
        data + "ScriptingAssemblies.json": scripting_assemblies().encode(),
        data + "boot.config": b"gfx-enable-gfx-jobs=1\n",
        "assets/Video/intro.mp4": b"\x00" * 10,
        "assets/Video/intro.rgbv": b"\x00" * 5,
        "assets/Video/manifest.json": b"{}",
    })
    return files


def split_name(abi):
    return f"split_config.{abi.replace('-', '_')}.apk"


def write_apk(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in sorted(files.items()):
            # fixed timestamp: a re-pull must give identical bytes
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)


class FakeDevice:
    def __init__(self, version, metadata_version, unity=UNITY, split_abi="", abi="arm64-v8a"):
        self.version = version
        self.metadata_version = metadata_version
        self.unity = unity
        self.split_abi = split_abi
        self.abi = abi
        self.pulls = 0

    def identify(self, package):
        return {"package": package, "version": self.version, "abi": self.abi}

    def pull(self, package, dest):
        self.pulls += 1
        if (dest / "apk").exists():  # like the real adapters: a pull replaces apk/
            shutil.rmtree(dest / "apk")
        (dest / "apk").mkdir(parents=True)
        apks: dict[str, dict] = {"base.apk": {}}
        prefix = f"lib/{self.split_abi}/"
        split = split_name(self.split_abi) if self.split_abi else None
        for name, data in apk_files(self.metadata_version, self.unity).items():
            apks.setdefault(split if split and name.startswith(prefix) else "base.apk", {})[name] = data
        for apk, files in sorted(apks.items()):
            write_apk(dest / "apk" / apk, files)
        return {"pulled": {"apk": sorted(apks), "obb": False, "data": False}}


def create(cfg):
    opts = cfg.options.get(PORT, {})
    return FakeDevice(opts.get("version", "0.4.6-17"), int(opts.get("metadata_version", "39")),
                      opts.get("unity_version", UNITY), opts.get("split_abi", ""), opts.get("abi", "arm64-v8a"))

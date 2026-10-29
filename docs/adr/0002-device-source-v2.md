# ADR 0002: `device_source` contract v2

Status: accepted (amends the `device_source` part of ADR 0001)

## Context

Contract v1 had a single method, `pull(package, dest)`, and promised `base.apk` at the top of `dest`. Two problems showed up when the acquire stage was built:

- The stage writes to `raw/<version>/`, so it must know the version label (`versionName-versionCode`) **before** it picks `dest`. With v1 only the adapter could find it out, and only while pulling.
- The existing pulled build uses `raw/<v>/apk/base.apk`, with sibling `obb/` and `data/` folders. v1's flat `base.apk` does not match it.

## Decision

- The Protocol gains `identify(package) -> dict`, which returns at least `{"package", "version"}` and optionally `"abi"`. It raises `RuntimeError` if the package is not installed or no source is reachable.
- `pull(package, dest)` writes `dest/apk/*.apk` (always `base.apk`, plus any splits), and optionally `dest/obb/` and `dest/data/`.
- The contract becomes `files=("apk/base.apk",)`.
- Adapter settings that a stage must not know about, like the folder adapter's source path, go in a new `zk.toml` table `[options.<port>]`. `create(cfg)` reads it.

## Consequences

- The stage stays adapter-agnostic: adb asks the phone for the version, and the folder adapter reads it from its options.
- Every `device_source` adapter must implement `identify`. None existed before this ADR, so nothing else changes.

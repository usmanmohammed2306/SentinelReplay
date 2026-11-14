# Replay compatibility and evidence versions

Finite-pack recordings now declare schema2 and the `finite-pack/1` replay contract. New recordings bind the interpreter, its runtime dependencies and Python major/minor. A current exact source profile is admitted directly. A historical profile is admitted only when its full adapter/runtime/Python material appears in the installed, reviewed registry in `replay_profiles.py`. Unknown source profiles fail before creating the replay destination.

Two November13 historical profiles are retained: the original published demo and the Linux OPA UID/GID portability fix. The registry stores their literal source identities. Tests replay a small historical clock/RNG/file capsule with live clock/RNG calls forbidden, and the complete published3,186-boundary capsule through workspace, Git and SQLite checkpoints. Golden canonical-wire vectors preserve the existing typed encoding, including enum subclasses, large integers, Unicode, bytes and timestamps.

This mechanism never imports Python from a capsule or runs an archived interpreter supplied by a caller. The installed trusted interpreter executes the fixed finite grammar. Definition digests, checkpoint identities, recorded requests, responses, evidence, journal chain and final covered effects remain checked. A self-consistent definition with an unknown runtime is rejected; recomputing its definition digest grants no compatibility.

Compatibility is an explicit supported ABI decision, not proof that every historical program is semantically identical. Adding a profile requires retained sources, an explanation of the change, golden capsules and conformance tests. A change to the meaning or coverage of an operation requires a new replay contract rather than adding an old profile to bypass a failure. Unsupported native-agent effects still earn boundary matching or unknown status, never strict effect replay by compatibility alone.

The profile is not a signer identity, external witness, release acceptance or freshness proof. Signed import and operator-held witnesses enforce their own boundaries. Python minor changes remain fail-closed until separately validated.

"""Trusted finite-pack source bundles admitted by regression conformance.

These profiles select the installed interpreter only. Archived capsule code is
never imported or executed. Unknown bundles remain fail-closed.
"""

from typing import Any

VALIDATED_PROFILES: dict[str, dict[str, Any]] = {
    "sha256:4120bd65128f2ce8b9b5a0d7594b1acf37678c16017304a9656ecd8c2c9e5343": {
        "name": "finite-pack-v1-2026-11-13-1",
        "contract": "finite-pack/1",
        "material": {
            "adapter_digest": (
                "sha256:e4daeec70477a0342a5ff9b88f876659f8dd62115aefea2778c6eeaaa20a4d96"
            ),
            "runtime_digests": {
                "canonical.py": (
                    "sha256:c3be227ce5bc3dc92189904246e6b417dbbb5cfa43934f107074a62ce7d91005"
                ),
                "environment_pack.py": (
                    "sha256:e4daeec70477a0342a5ff9b88f876659f8dd62115aefea2778c6eeaaa20a4d96"
                ),
                "evidence_store.py": (
                    "sha256:ec3fe3b83b808a0ffa93570eb469cd894a4685805d9b062a57ffcf449d203f9b"
                ),
                "journal.py": (
                    "sha256:7db379d869689761de2c4d99d69a1fdcc80308f7266c4d4d67edb0d57c7e08ff"
                ),
                "policy_language.py": (
                    "sha256:cc090dbe470a37d5d448b406a421a21223fdd4022ea11cb7f24986a73464f1e0"
                ),
                "progress_anchor.py": (
                    "sha256:7d53a1fee496ee538be5983da0843234701e5b4bc4f56944201b8a1ae32e6eab"
                ),
                "telemetry.py": (
                    "sha256:6d97994818598a0e877d8a96dcae329f792c4c8131dbf3bc0169f68a5142735d"
                ),
                "workspace_snapshot.py": (
                    "sha256:d681c01dcde5af8bc94b41bfd484b2aeaee3fd8d7082d148f6a415b91f2e5c81"
                ),
            },
            "python_major_minor": [3, 12],
        },
    },
    "sha256:f89b9cd03ed97370d0bd118aa1cc20ee31aaf6f206cfe98441934c67bbc0c230": {
        "name": "finite-pack-v1-2026-11-13-2",
        "contract": "finite-pack/1",
        "material": {
            "adapter_digest": (
                "sha256:e4daeec70477a0342a5ff9b88f876659f8dd62115aefea2778c6eeaaa20a4d96"
            ),
            "runtime_digests": {
                "canonical.py": (
                    "sha256:c3be227ce5bc3dc92189904246e6b417dbbb5cfa43934f107074a62ce7d91005"
                ),
                "environment_pack.py": (
                    "sha256:e4daeec70477a0342a5ff9b88f876659f8dd62115aefea2778c6eeaaa20a4d96"
                ),
                "evidence_store.py": (
                    "sha256:ec3fe3b83b808a0ffa93570eb469cd894a4685805d9b062a57ffcf449d203f9b"
                ),
                "journal.py": (
                    "sha256:7db379d869689761de2c4d99d69a1fdcc80308f7266c4d4d67edb0d57c7e08ff"
                ),
                "policy_language.py": (
                    "sha256:dd19545e116e8fb56c01aedd7a779829fbe9e77c393bf3405f79baae6c4a903b"
                ),
                "progress_anchor.py": (
                    "sha256:7d53a1fee496ee538be5983da0843234701e5b4bc4f56944201b8a1ae32e6eab"
                ),
                "telemetry.py": (
                    "sha256:6d97994818598a0e877d8a96dcae329f792c4c8131dbf3bc0169f68a5142735d"
                ),
                "workspace_snapshot.py": (
                    "sha256:d681c01dcde5af8bc94b41bfd484b2aeaee3fd8d7082d148f6a415b91f2e5c81"
                ),
            },
            "python_major_minor": [3, 12],
        },
    },
    "sha256:ab29a43e8d175112c84dc24329a9dce935d76c877cff3d13fbd6c3ae02785eaa": {
        "name": "finite-pack-v1-2026-11-14-1",
        "contract": "finite-pack/1",
        "material": {
            "adapter_digest": (
                "sha256:cf59b3dfc9559a6a8d9127780f74c9324b544cdd1be490d3b0cf6c1fdc5c3f46"
            ),
            "runtime_digests": {
                "environment_pack.py": (
                    "sha256:cf59b3dfc9559a6a8d9127780f74c9324b544cdd1be490d3b0cf6c1fdc5c3f46"
                ),
                "policy_language.py": (
                    "sha256:dd19545e116e8fb56c01aedd7a779829fbe9e77c393bf3405f79baae6c4a903b"
                ),
                "canonical.py": (
                    "sha256:022a3ee9b91de7e735526af75352303f9206e7a3f6c4e781052315b99202d101"
                ),
                "journal.py": (
                    "sha256:7db379d869689761de2c4d99d69a1fdcc80308f7266c4d4d67edb0d57c7e08ff"
                ),
                "workspace_snapshot.py": (
                    "sha256:d681c01dcde5af8bc94b41bfd484b2aeaee3fd8d7082d148f6a415b91f2e5c81"
                ),
                "evidence_store.py": (
                    "sha256:ec3fe3b83b808a0ffa93570eb469cd894a4685805d9b062a57ffcf449d203f9b"
                ),
                "telemetry.py": (
                    "sha256:6d97994818598a0e877d8a96dcae329f792c4c8131dbf3bc0169f68a5142735d"
                ),
                "progress_anchor.py": (
                    "sha256:7d53a1fee496ee538be5983da0843234701e5b4bc4f56944201b8a1ae32e6eab"
                ),
                "replay_profiles.py": (
                    "sha256:509e82235894e69b95997f0ba898879fe2f91dbc6095b6817ba7178b8b69b2d9"
                ),
            },
            "python_major_minor": [3, 12],
        },
    },
}


def validate_replay_profile(definition: dict[str, Any], current: dict[str, Any]) -> dict[str, str]:
    from sentinel_replay.boundary import ReplayMiss
    from sentinel_replay.canonical import event_digest

    material = {
        key: definition.get(key)
        for key in ("adapter_digest", "runtime_digests", "python_major_minor")
    }
    if material["python_major_minor"] != current["python_major_minor"]:
        raise ReplayMiss("pack Python compatibility mismatch")
    version = definition.get("schema_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise ReplayMiss("unsupported pack definition version")
    if version == 2 and definition.get("replay_contract") != "finite-pack/1":
        raise ReplayMiss("unsupported pack replay contract")
    identity = event_digest(material)
    if version == 2 and material == current:
        mode = "exact_source"
    elif identity in VALIDATED_PROFILES and material == VALIDATED_PROFILES[identity]["material"]:
        mode = "validated_finite_pack_v1_profile"
    else:
        raise ReplayMiss("pack runtime source bundle has no validated replay profile")
    return {
        "recording_profile": identity,
        "installed_profile": event_digest(current),
        "contract": "finite-pack/1",
        "mode": mode,
    }

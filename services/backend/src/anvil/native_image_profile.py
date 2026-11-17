"""Exact scanned AMD64 software-fixture successor; no runtime image override.

DevOps build87687277-b5d7-4a37-8cf3-38c2edc55bbb, scan receipt SHA256
77966a74203ecc897c13f463bf4167e2fbc5c6c2933bc41803a247be86aaf389.
This image identity grants neither source review nor execution/spending authority.
"""

IMAGE = "us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/native-fixture-security@sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
IMAGE_ID = "sha256:72b8eaacefaa82ffdec3ee632375df24057962d8c14cc327f1990113f7c2b951"
ARCHITECTURE = "amd64"


def require_cached_image(info):
    if (
        not isinstance(info, dict)
        or info.get("Os") != "linux"
        or info.get("Architecture") != ARCHITECTURE
        or info.get("Id") != IMAGE_ID
        or IMAGE not in info.get("RepoDigests", [])
    ):
        raise ValueError("Exact cached security-profile Linux image required")

"""Additive fixed AppArmor actor confinement. Never native admission.

Stacking retains the existing operator policy, including under no_new_privs.
No environment, caller profile name, fallback or reverse transition is accepted.
Actual policy bytes/features, closed FD inventory and role filesystem projection
remain independent runtime prerequisites; a matching label alone proves none.
"""

import os
import sys

OPERATOR = "anvil-marketing-operator-v1"
ACTORS = {"sdk": "anvil-marketing-sdk-v1", "graph": "anvil-marketing-graph-v1"}
ATTRIBUTE = "/proc/thread-self/attr/apparmor/current"
LABEL_LIMIT = 512


def _current_label():
    descriptor = os.open(ATTRIBUTE, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = os.read(descriptor, LABEL_LIMIT + 1)
    finally:
        os.close(descriptor)
    if not raw or len(raw) > LABEL_LIMIT:
        raise ValueError("marketing_bounded_actual_mac_label_required")
    return raw.decode("ascii", errors="strict").rstrip("\n")


def _labels(value):
    if not value.endswith(" (enforce)"):
        raise ValueError("marketing_enforced_mac_policy_required")
    labels = value.removesuffix(" (enforce)").split("//&")
    if len(set(labels)) != len(labels) or any(not label for label in labels):
        raise ValueError("marketing_exact_mac_stack_required")
    return frozenset(labels)


def verify_actor_profile(role):
    if role not in ACTORS:
        raise ValueError("marketing_fixed_actor_mac_role_required")
    if _labels(_current_label()) != frozenset((OPERATOR, ACTORS[role])):
        raise ValueError("marketing_original_enforced_actor_mac_stack_required")


def stack_actor_profile(role):
    if role not in ACTORS:
        raise ValueError("marketing_fixed_actor_mac_role_required")
    if sys.platform != "linux" or os.uname().machine != "x86_64" or os.geteuid() != 0:
        raise ValueError("marketing_root_linux_amd64_mac_required")
    if _labels(_current_label()) != frozenset((OPERATOR,)):
        raise ValueError("marketing_original_operator_mac_profile_required")
    # Only add restrictions. Never replace the operator label or relax NNP.
    request = ("stack " + ACTORS[role]).encode("ascii")
    descriptor = os.open(ATTRIBUTE, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        if os.write(descriptor, request) != len(request):
            raise RuntimeError("marketing_mac_transition_unknown_no_retry")
    finally:
        os.close(descriptor)
    verify_actor_profile(role)

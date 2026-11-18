# Actual Linux mount/MAC predicate verification

No model calls, Authoring, private data, host mounts/network/PID sharing, production
policy changes or native qualification. New uniquely named probe profiles only;
all existing profiles and serving QA roles preserved. Probe policies are NOT a
production role filesystem policy and must never be attached to a business run.

QA has AppArmor3.0.8, ptrace/signal mediation and parser. Compile with warnings as
errors; no complain mode, fallback, default-profile replacement or NNP relaxation.
The original unenforced fake-socket case reproduced proc-root access by UID0 with
zero caps after a helper exec reset dumpability to1. The first profile draft lacked
the required relative-stack permission. Correct rule is change_profile -> &target;
the proc request remains stack target. Corrected additive confinement preserved NNP
and denied foreign proc access, but direct admin-socket access remained available.

Combined probe then created a private mount namespace, made propagation private,
masked only the fake admin path, dropped setup capabilities and all bounding bits,
and stacked the actor policy. NNP stayed1. Actual final result PASS:

- Foreign helper proc-root and fd access denied.
- Direct masked admin socket inaccessible.
- Foreign helper signal and reverse profile transition denied.
- Original helper start-tick reads and own FD inspection preserved.
- Intended control socket works; confinement remains after ordinary exec.
- Parent/operator socket namespace unchanged.

Two setup capabilities SYS_ADMIN/SETPCAP were present only before actor execution
inside the isolated, network-disabled, no-host-mount probe container. Actor execution
verified zero effective caps. No --privileged or seccomp-unconfined option used.
The v3 loaded probe policy SHA is57c75ccef9097b3a1284c48f71a1aa12fc025075806cb7b59ff93a3df79a8fa4;
v1/v2 failures and original loaded profiles are retained rather than relabelled.
Harness corrections retained: bounded child-error reporting, an indentation error,
and removal of a site-package import from the intentionally stdlib-only -S child.

Source harness: scripts/verify_marketing_mac_probe.py. Policy source in
infra/apparmor/marketing-proc-probe.apparmor includes explanatory comments, so its
file hash differs from the loaded comment-free diagnostic artifact. Native input
claims cannot reuse either as an independently approved production profile.

Unwired marketing_native_mac.py prototype has9 local manufactured-label tests.
Its fixed shared labels are deliberately not wired into SDK/graph launch: a real
deployment needs per-attempt profiles, original job binding, exact closed FD and
role filesystem projections, full owner/capture lifecycle and genuine six-part
independent qualification. A positive predicate test is not full RL Gym stability.

Primary references: https://raw.githubusercontent.com/torvalds/linux/v6.1/security/apparmor/domain.c
and https://gitlab.com/apparmor/apparmor/-/wikis/AppArmorStacking .

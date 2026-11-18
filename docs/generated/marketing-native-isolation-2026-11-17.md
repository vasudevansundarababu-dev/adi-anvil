# Marketing native isolation — confirmed deployment blocker

Read-only review of fc23fb8 found that trusted Docker/Compose helpers call
`harden_graph()` and then ordinary `execve()`. The SDK, graph and helpers share
kernel UID0 and are designed for host PID visibility. Ordinary exec resets
dumpability; a locally masked admin socket alone does not prove that the actor
cannot traverse an exec helper's `/proc/<pid>/root` view.

Actual QA Linux probe used only a disposable network-disabled, readonly container,
zero capabilities, no host mounts, fake `/tmp` Unix socket and bounded child
processes. No production socket, credentials, database, model or Authoring data.
Observed ordinary-exec dumpable1; same-UID zero-capability actor successfully
connected to the fake socket through the helper's proc-root path. This reproduces
the relevant kernel access predicate. It is a security failure for the proposed
shared-UID/PID recipe, not a successful native qualification or a demonstrated
exploit against a deployed Marketing worker (none is admitted).

Probe: `scripts/verify_marketing_proc_boundary.py`, run on existing QA with
kyc-runtime@sha256:4f27972ad13fa56d73dc4f0512189f4993ae9b8401cb4863391511e257cf7077,
`--network none --read-only --user0:0 --cap-drop ALL --security-opt no-new-privileges`
and only a private16MiB/tmp tmpfs. No host PID/network namespace sharing or mount.
Primary Linux references: https://www.man7.org/linux/man-pages/man2/execve.2.html
and https://www.man7.org/linux/man-pages/man5/proc_pid_root.5.html.

Required before native activation: explicit per-role filesystem/FD projection,
an enforced proc/admin-socket boundary that survives helper exec, concrete outer
container/attach custody and bounded prepare adapters, compatible minimal actor/
verifier image, actual Linux deadline/death/cleanup tests, and authentic current
independent evidence/admission. SDK needs its exact control socket; graph needs
its exact attester socket. Blindly hiding all/run or all/proc would break required
original handles and is not a safe fix. Trusted helpers need distinct authority.

Native gate remains closed. Serving software scheduler/grader continue to poll
without models; that working deployment is separate from native qualification.

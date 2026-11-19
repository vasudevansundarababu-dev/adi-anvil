"""Classifier security controls only; not physical network qualification."""

import unittest
from pathlib import Path

from network_observer import classify, complete_trace


class TraceControls(unittest.TestCase):
    bridge = Path("/var/lib/anvil-qa-v1/runtime-functional/native-control-bridge")

    def test_actual_control_unix_peer_is_positive_evidence(self):
        raw = ('1.0 connect(3, {sa_family=AF_UNIX, sun_path="' + str(self.bridge)
               + '/.sg-abc12345/.bm-gw-def12345/gateway.sock"}, 100) = 0\n').encode()
        self.assertEqual(classify(raw, self.bridge)["unix_connect_events"], 1)

    def test_both_internet_families_and_connect_are_denied(self):
        for raw in (b"socket(AF_INET, SOCK_STREAM, IPPROTO_TCP) = 3\n", b"socket(AF_INET6, SOCK_DGRAM, 0) = -1\n",
                    b"connect(3, {sa_family=AF_INET, sin_port=htons(443)}, 16) = 0\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                classify(raw, self.bridge)

    def test_arbitrary_unix_broker_is_denied(self):
        with self.assertRaises(ValueError):
            classify(b'connect(3, {sa_family=AF_UNIX, sun_path="/tmp/provider.sock"}, 30) = 0\n', self.bridge)

    def test_no_positive_syscall_observations_is_not_a_pass(self):
        with self.assertRaises(ValueError):
            classify(b"", self.bridge)

    def test_abstract_malformed_and_truncated_connections_are_denied(self):
        for address in ('@"hidden"', '"/run/docker.sock"...', '""', 'NULL'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                classify(('connect(3, {sa_family=AF_UNIX, sun_path=' + address + '}, 100) = 0\n').encode(), self.bridge)

    def test_process_terminal_coverage_is_required(self):
        complete_trace(b'123.123 +++ exited with 0 +++\n')
        complete_trace(b'123.123 +++ killed by SIGTERM +++\n')
        for raw in (b'', b'connect(3, {sa_family=AF_UNIX, sun_path="/run/docker.sock"}, 30) = 0\n'):
            with self.assertRaises(ValueError):
                complete_trace(raw)


if __name__ == "__main__":
    unittest.main()

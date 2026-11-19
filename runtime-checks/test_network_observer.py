"""Classifier security controls only; not physical network qualification."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from network_observer import FilteredSDKObserver, classify, complete_trace


class TraceControls(unittest.TestCase):
    bridge = Path("/var/lib/anvil-qa-v1/runtime-functional/native-control-bridge")

    def test_actual_control_unix_peer_is_positive_evidence(self):
        raw = ('1.0 connect(3, {sa_family=AF_UNIX, sun_path="' + str(self.bridge)
               + '/.sg-abc12345/.bm-gw-def12345/gateway.sock"}, 100) = 0\n').encode()
        self.assertEqual(classify(raw, self.bridge)["unix_connect_events"], 1)

    def test_internet_connect_and_unknown_socket_families_are_denied(self):
        for raw in (b"socket(AF_PACKET, SOCK_RAW, 0) = 3\n",
                    b"connect(3, {sa_family=AF_INET, sin_port=htons(443)}, 16) = 0\n",
                    b"connect(3, {sa_family=AF_INET6, sin6_port=htons(443)}, 28) = -1 ENETUNREACH\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                classify(raw, self.bridge)

    def test_capability_probe_is_counted_and_failed_nscd_is_not_control_evidence(self):
        prefix = b'socket(AF_INET6, SOCK_STREAM|SOCK_CLOEXEC, IPPROTO_IP) = 3\nconnect(3, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT (No such file or directory)\n'
        with self.assertRaises(ValueError):
            classify(prefix, self.bridge)
        result = classify(prefix + b'connect(4, {sa_family=AF_UNIX, sun_path="/run/docker.sock"}, 30) = 0\n', self.bridge)
        self.assertEqual(result["internet_socket_events"], 1)
        self.assertEqual(result["internet_connect_events"], 0)
        self.assertEqual(result["unix_connect_events"], 1)

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

    def test_tracer_exit_race_preserves_partial_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            observer = object.__new__(FilteredSDKObserver)
            observer.evidence = Path(folder)
            observer.tracer_descriptor, write_fd = os.pipe()
            observer.tracer_owned = True
            observer.process = unittest.mock.Mock()
            observer.process.communicate.return_value = (b"original stdout", b"original stderr")
            poller = unittest.mock.Mock()
            poller.poll.side_effect = [[], [(observer.tracer_descriptor, 1)]]
            try:
                with patch("network_observer.NetworkObserver.abort"), patch("network_observer.select.poll", return_value=poller), patch("network_observer.signal.pidfd_send_signal", side_effect=ProcessLookupError, create=True):
                    observer.abort()
                self.assertEqual((Path(folder) / "sdk.partial.stdout").read_bytes(), b"original stdout")
                self.assertEqual(json.loads((Path(folder) / "sdk.filtered-abort.json").read_bytes())["failures"], [])
            finally:
                os.close(write_fd)

    def test_detached_tracer_pipe_timeout_retains_original_partial_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            observer = object.__new__(FilteredSDKObserver)
            observer.evidence = Path(folder)
            observer.tracer_descriptor, write_fd = os.pipe()
            observer.tracer_owned = True
            observer.process = unittest.mock.Mock()
            deadline = subprocess.TimeoutExpired("fixed synthetic process", 3, output=b"partial original", stderr=b"partial error")
            observer.process.communicate.side_effect = deadline
            poller = unittest.mock.Mock()
            poller.poll.return_value = [(observer.tracer_descriptor, 1)]
            try:
                with patch("network_observer.NetworkObserver.abort", side_effect=deadline), patch("network_observer.select.poll", return_value=poller):
                    observer.abort()
                self.assertEqual((Path(folder) / "sdk.partial.stdout").read_bytes(), b"partial original")
                self.assertIn("partial_pipe_drain_unknown", json.loads((Path(folder) / "sdk.filtered-abort.json").read_bytes())["failures"])
            finally:
                os.close(write_fd)


if __name__ == "__main__":
    unittest.main()

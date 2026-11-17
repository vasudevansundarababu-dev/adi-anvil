"""Anvil-owned configuration custody, never runtime/dispatch qualification.

No connection, DNS, file creation, credential issuance or deployment occurs.
Only a safe status/reason/hash may leave this module; never return its private
effective libpq parameters or descriptor through an API or diagnostic repr.
"""

import hmac
import ipaddress
import os
import re
import stat
from pathlib import Path

from psycopg import capabilities, pq
from psycopg.conninfo import conninfo_to_dict

from anvil.praxis_generic_contract import digest

PIN = "ANVIL_CAPTURE_DATABASE_TARGET_SHA256"
DSN_SETTINGS = frozenset({"DATABASE_URL", "ANVIL_GOLDEN_SCHEDULER_DATABASE_URL",
                          "ANVIL_CAPTURE_PEER_DATABASE_URL", "ANVIL_CAPTURE_REGISTRAR_DATABASE_URL"})
TLS_FIELDS = ("sslmode", "sslnegotiation", "sslrootcert", "sslcert", "sslkey", "sslcrl", "sslcrldir",
              "ssl_min_protocol_version", "ssl_max_protocol_version", "sslsni", "sslcertmode",
              "channel_binding", "gssencmode", "requirepeer", "require_auth")


class TargetUnavailable(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def setting(name):
    """Read only an explicitly injected fixed DSN; never load API config/.env."""
    if name not in DSN_SETTINGS:
        raise TargetUnavailable("capture_database_fixed_identity_required")
    value = os.environ.get(name)
    if not value:
        raise TargetUnavailable("capture_database_target_unavailable")
    return value


def inspect_target(*, setting_name="DATABASE_URL"):
    """Normalize effective parameters using libpq's own metadata, not DNS.

    parse(empty) supplies option metadata and compiled defaults without opening
    a connection or loading service files. DSN overrides environment, which
    overrides compiled defaults, matching libpq precedence. Secrets remain
    private and are deliberately absent from the allowlisted hash descriptor.
    """
    try:
        if setting_name not in DSN_SETTINGS:
            raise TargetUnavailable("capture_database_fixed_identity_required")
        supplied = conninfo_to_dict(setting(setting_name))
        parameters = {}
        for option in pq.Conninfo.parse(b""):
            name = option.keyword.decode("ascii")
            variable = option.envvar.decode("ascii") if option.envvar else None
            value = supplied.get(name)
            if value is None:
                value = os.environ.get(variable) if variable else None
                if not value:
                    value = option.compiled.decode("utf-8") if option.compiled else None
            if value is not None:
                parameters[name] = value
        if parameters.get("service"):
            raise TargetUnavailable("capture_database_service_expansion_denied")
        host, address = parameters.get("host", ""), parameters.get("hostaddr", "")
        port = parameters.get("port", "5432")
        if (not host or any("," in value for value in (host, address, port))
                or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535):
            raise TargetUnavailable("capture_database_single_target_required")
        if parameters.get("target_session_attrs", "any") == "prefer-standby":
            raise TargetUnavailable("capture_database_failover_denied")
        if parameters.get("load_balance_hosts", "disable") != "disable":
            raise TargetUnavailable("capture_database_failover_denied")
        for key in ("dbname", "user"):
            if not parameters.get(key) or len(parameters[key].encode()) > 200:
                raise TargetUnavailable("capture_database_explicit_identity_required")
        if "=" in parameters["dbname"] or parameters["dbname"].startswith(("postgresql://", "postgres://")):
            raise TargetUnavailable("capture_database_nested_configuration_denied")
        if parameters.get("options") or parameters.get("replication") not in (None, "false", "0"):
            raise TargetUnavailable("capture_database_opaque_session_configuration_denied")
        if (parameters.get("sslmode", "prefer") not in {"disable", "require", "verify-ca", "verify-full"}
                or parameters.get("gssencmode", "disable") != "disable"
                or any(key.startswith("oauth_") and value for key, value in parameters.items())
                or "oauth" in parameters.get("require_auth", "")):
            raise TargetUnavailable("capture_database_nonfallback_security_profile_required")
        descriptor = {"schema_version": "anvil.capture-database-target-configuration.v1", "host": host,
                      "port": str(int(port)), "database": parameters["dbname"], "user": parameters["user"],
                      "target_session_attrs": parameters.get("target_session_attrs", "any"),
                      "tls": {key: parameters.get(key) for key in TLS_FIELDS}}
        if host.startswith("/"):
            if address:
                raise TargetUnavailable("capture_database_single_target_required")
            parent = Path(host).resolve(strict=True)
            endpoint = parent / (".s.PGSQL." + str(int(port)))
            info = endpoint.stat(follow_symlinks=False)
            if not stat.S_ISSOCK(info.st_mode):
                raise TargetUnavailable("capture_database_socket_binding_required")
            descriptor.update(kind="unix_socket", resolved_parent=str(parent),
                              socket_identity={"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid,
                                               "gid": info.st_gid, "mode": info.st_mode})
        else:
            candidate = address or host
            if "%" in candidate:
                raise TargetUnavailable("capture_database_numeric_binding_required")
            try:
                numeric = str(ipaddress.ip_address(candidate))
            except ValueError:
                raise TargetUnavailable("capture_database_numeric_binding_required") from None
            parameters["hostaddr"] = numeric
            descriptor.update(kind="tcp", hostaddr=numeric)
        parameters["port"] = str(int(port))
        return parameters, digest(descriptor)
    except TargetUnavailable:
        raise
    except Exception:
        # Parser/filesystem errors can embed private configuration. Never expose
        # their message, arguments, DSN or exception chain through Admin/API.
        raise TargetUnavailable("capture_database_target_unavailable") from None


def configuration():
    parameters, fingerprint = inspect_target()
    _check_pin(fingerprint)
    return parameters, fingerprint


def _check_pin(fingerprint):
    pin = os.environ.get(PIN, "")
    if not re.fullmatch(r"[a-f0-9]{64}", pin):
        raise TargetUnavailable("capture_database_binding_pin_required")
    if not hmac.compare_digest(pin, fingerprint):
        raise TargetUnavailable("capture_database_binding_pin_stale")


def readiness():
    """Read-only safe Admin requirement, not a probe or execution admission."""
    value = {"owner": "anvil_provisioning", "ready": False, "configuration_ready": False,
             "runtime_qualified": False, "connection_probe_performed": False,
             "reason": "capture_database_target_unavailable", "target_sha256": None}
    try:
        _, fingerprint = inspect_target()
        value["target_sha256"] = fingerprint
        _check_pin(fingerprint)
        value["configuration_ready"] = True
        value["reason"] = ("capture_database_runtime_qualification_required" if capabilities.has_cancel_safe()
                           else "capture_database_driver_qualification_required")
    except TargetUnavailable as error:
        value["reason"] = error.code
    return value

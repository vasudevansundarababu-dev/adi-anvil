const messages: Record<string, string> = {
  capture_database_runtime_qualified: 'The capture API database target and cancellation controls are qualified. Project and operator bindings remain separate.',
  capture_database_trust_file_required: 'Forge must restore and qualify the database trust certificate.',
  capture_database_runtime_qualification_required: 'Forge still needs to verify this database binding in the actual runtime.',
  capture_database_driver_qualification_required: 'Forge needs a qualified database client before capture can run.',
  capture_database_binding_pin_required: 'Forge provisioning needs to record the database binding.',
  capture_database_binding_pin_stale: 'The database binding changed. Forge must qualify it again.',
  capture_database_numeric_binding_required: 'Forge provisioning needs to bind one database address.',
  capture_database_single_target_required: 'Forge provisioning needs one explicit database target.',
  capture_database_failover_denied: 'Forge must remove automatic database fallback from this capture profile.',
  capture_database_service_expansion_denied: 'Forge must supply an explicit database binding.',
  capture_database_explicit_identity_required: 'Forge must complete the database identity binding.',
  capture_database_nested_configuration_denied: 'Forge must qualify an explicit database configuration.',
  capture_database_opaque_session_configuration_denied: 'Forge must qualify the database session configuration.',
  capture_database_nonfallback_security_profile_required: 'Forge must qualify the database security profile.',
  capture_database_socket_binding_required: 'Forge must restore and qualify the database connection.',
  capture_database_target_unavailable: 'Forge database configuration has not been verified.',
};

export function captureDatabaseStatus(value: unknown) {
  const record = value && typeof value === 'object' ? value as Record<string, unknown> : null;
  const reason = typeof record?.reason === 'string' ? record.reason : '';
  const configurationReady = record?.owner === 'anvil_provisioning'
    && record.configuration_ready === true
    && (reason === 'capture_database_runtime_qualification_required'
      || reason === 'capture_database_driver_qualification_required'
      || reason === 'capture_database_runtime_qualified');
  const proof = record?.qualification && typeof record.qualification === 'object'
    ? record.qualification as Record<string, unknown> : null;
  const isHash = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const ready = configurationReady && reason === 'capture_database_runtime_qualified'
    && record?.ready === true && record.runtime_qualified === true
    && record.connection_probe_performed === false
    && proof?.schema_version === 'anvil.capture-database-runtime-qualification.v1'
    && proof.scope === 'capture_api_database_target_only' && proof.spending_authority === false
    && isHash(proof.receipt_sha256) && isHash(record.target_sha256)
    && proof.target_sha256 === record.target_sha256
    && typeof proof.expires_at === 'string' && Date.parse(proof.expires_at) > Date.now();
  return {
    ready,
    configurationReady,
    message: reason === 'capture_database_runtime_qualified' && !ready
      ? 'Current capture database qualification evidence is incomplete or expired.'
      : messages[reason] || 'Forge database readiness has not been reported.',
  };
}

const messages: Record<string, string> = {
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
      || reason === 'capture_database_driver_qualification_required');
  return {
    // No applicable database runtime-qualification receipt contract exists yet.
    // A pin, generic role flag or server "ready" boolean cannot invent one.
    ready: false,
    configurationReady,
    message: messages[reason] || 'Forge database readiness has not been reported.',
  };
}

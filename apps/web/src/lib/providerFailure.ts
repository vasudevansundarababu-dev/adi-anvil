export function providerFailure(usage: unknown): string | null {
  if (!usage || typeof usage !== 'object' || Array.isArray(usage)) return null;
  const evidence = (usage as Record<string, unknown>).provider_evidence;
  if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) return null;
  const status = (evidence as Record<string, unknown>).provider_http_status;
  const message =
    status === 503
      ? 'Provider unavailable (HTTP 503).'
      : status === 504
        ? 'Provider request deadline exceeded (HTTP 504).'
        : typeof status === 'number' && Number.isInteger(status) && status >= 500 && status <= 599
          ? `Provider server error (HTTP ${status}).`
          : null;
  return message
    ? message +
        ' Outcome and cost are unconfirmed; the reservation remains held. No automatic retry.'
    : null;
}

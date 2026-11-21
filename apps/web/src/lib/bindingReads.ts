// Only read requests use this deadline. Mutation outcomes are never inferred or retried.
export async function bindingReads<T>(
  paths: string[],
  read: (path: string, signal: AbortSignal) => Promise<T>,
  controller: AbortController,
  timeoutMs = 60_000,
): Promise<T[]> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancelled: (() => void) | undefined;
  try {
    const stop = new Promise<never>((_, reject) => {
      cancelled = () => reject(new Error('Binding read cancelled.'));
      controller.signal.addEventListener('abort', cancelled, { once: true });
      if (controller.signal.aborted) cancelled();
      timer = setTimeout(() => {
        reject(new Error('Loading bindings timed out. Reload to check again; no changes were submitted.'));
        controller.abort();
      }, timeoutMs);
    });
    return await Promise.race([
      Promise.all(paths.map((path) => read(path, controller.signal))),
      stop,
    ]);
  } finally {
    clearTimeout(timer);
    if (cancelled) controller.signal.removeEventListener('abort', cancelled);
    controller.abort();
  }
}

export function structuredInputPanel(
  inputOptions: unknown,
  hasLegacyActor: boolean,
  hasSelection: boolean,
): boolean {
  return (!!inputOptions && !hasLegacyActor) || hasSelection;
}

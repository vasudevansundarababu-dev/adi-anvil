export function policyReviewMatches(
  tasks: { task_id: string; task_version: string }[],
  subject: unknown,
): boolean {
  if (!subject || typeof subject !== 'object') return false;
  const value = subject as { task_id?: unknown; revision_id?: unknown };
  return typeof value.task_id === 'string' && typeof value.revision_id === 'string' &&
    tasks.some(task => task.task_id === value.task_id && task.task_version === value.revision_id);
}

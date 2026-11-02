import { redirect } from 'next/navigation';
export default async function Page({
  params,
}: {
  params: Promise<{ project: string; section?: string[] }>;
}) {
  const { project, section = [] } = await params;
  const destinations: Record<string, string> = {
    harbor: 'tasks',
    providers: 'models',
    people: 'people',
    runs: 'runs',
  };
  redirect(
    '/workspace/' + encodeURIComponent(project) + '/' + (destinations[section[0]] || 'overview'),
  );
}

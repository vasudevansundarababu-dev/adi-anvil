import { redirect } from 'next/navigation';
import { connection } from 'next/server';

// RLGYM_V2=1 makes the new RL Gym the entry; the existing workspace stays at /workspace.
export default async function Page() {
  await connection();
  redirect(process.env.RLGYM_V2 === '1' ? '/gym' : '/workspace');
}

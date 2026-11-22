import { Suspense } from 'react';
import { connection } from 'next/server';
import RLGym from '../../../components/rlgym/RLGym';

export default async function Page() {
  await connection();
  const enabled = process.env.RLGYM_V2 === '1';
  return (
    <Suspense fallback={<p>Loading RL Gym…</p>}>
      <RLGym enabled={enabled} />
    </Suspense>
  );
}

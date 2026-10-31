import { Suspense } from 'react';
import ModernWorkspace from '../../../../components/ModernWorkspace';
export default function Page() {
  return (
    <Suspense fallback={<p>Loading workspace…</p>}>
      <ModernWorkspace />
    </Suspense>
  );
}

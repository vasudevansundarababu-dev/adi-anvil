'use client';
import { useState } from 'react';
import FrameworkProfiles from './FrameworkProfiles';
import ModelProfiles from './ModelProfiles';
import WorkspacePeople from './WorkspacePeople';
import EvaluatorSettings from './EvaluatorSettings';
import RuntimeInventory from './RuntimeInventory';
import s from './ModernWorkspace.module.css';

export default function WorkspaceAdmin({ base, route }: { base: string; route: string }) {
  const [tab, setTab] = useState('Frameworks');
  return (
    <>
      <nav className={s.actions} aria-label="Admin tabs">
        {['Frameworks', 'Models & Keys', 'Users'].map((name) => (
          <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>
      {tab === 'Frameworks' && (
        <>
          <RuntimeInventory base={base} />
          <FrameworkProfiles base={base} />
          <details>
            <summary>Evaluator integrations</summary>
            <EvaluatorSettings base={base} />
          </details>
          <p>
            <a href={route + '/limits'}>Limits &amp; usage</a>
          </p>
        </>
      )}
      {tab === 'Models & Keys' && <ModelProfiles base={base} />}
      {tab === 'Users' && <WorkspacePeople base={base} />}
    </>
  );
}

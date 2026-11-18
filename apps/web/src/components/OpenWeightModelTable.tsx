'use client';
import styles from './ModernWorkspace.module.css';

export type OpenWeightCatalogItem = {
  id: string;
  label: string;
  repositories: { repository: string; revision: string; repository_url: string }[];
};

export default function OpenWeightModelTable({
  catalog,
  selected,
  onChange,
  disabled = false,
}: {
  catalog: OpenWeightCatalogItem[];
  selected: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
}) {
  const rows = catalog.flatMap((item) =>
    item.repositories.map((repo) => ({
      ...repo,
      label: item.label,
      key: item.id + ':' + repo.repository,
    })),
  );
  return (
    <div>
      <p>
        {selected.length} of {rows.length} model versions selected
      </p>
      <button
        type="button"
        disabled={disabled || !rows.length}
        onClick={() => onChange(rows.map((row) => row.key))}
      >
        Select all listed versions
      </button>
      <button type="button" disabled={disabled || !selected.length} onClick={() => onChange([])}>
        Clear selection
      </button>
      <div className={styles.tableScroll}>
        <table aria-label="Open Weight model versions">
          <thead>
            <tr>
              <th scope="col">Select</th>
              <th scope="col">Name</th>
              <th scope="col">Version</th>
              <th scope="col">Repository</th>
              <th scope="col">Terms</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={'Select ' + row.repository + ' at ' + row.revision}
                    disabled={disabled}
                    checked={selected.includes(row.key)}
                    onChange={(event) =>
                      onChange(
                        event.target.checked
                          ? [...selected, row.key]
                          : selected.filter((key) => key !== row.key),
                      )
                    }
                  />
                </td>
                <td>{row.label}</td>
                <td>
                  <code title={row.revision} style={{ overflowWrap: 'anywhere' }}>
                    {row.revision}
                  </code>
                </td>
                <td>
                  <a href={row.repository_url} target="_blank" rel="noreferrer">
                    {row.repository}
                  </a>
                </td>
                <td>
                  <a
                    href={row.repository_url + '/blob/' + row.revision + '/README.md'}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={'Terms and model card for ' + row.repository}
                  >
                    Terms &amp; model card
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

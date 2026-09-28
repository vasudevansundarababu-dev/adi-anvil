import { useId } from 'react';

type Node = { id: string; label: string; kind: string; status: string; hash: string };
type Edge = { source: string; target: string; relation: string };

export default function GraphMap({
  nodes,
  edges,
  selected,
  onSelect,
}: {
  nodes: Node[];
  edges: Edge[];
  selected?: string;
  onSelect: (node: Node) => void;
}) {
  const marker = useId();
  const kinds = [
    'objective',
    'case_family',
    'case',
    'task',
    'capability',
    'suite',
    'protocol',
    'episode',
    'finding',
    'report',
  ].filter((kind) => nodes.some((node) => node.kind === kind));
  const grouped = kinds.map((kind) => nodes.filter((node) => node.kind === kind));
  const width = Math.max(600, kinds.length * 190);
  const height = Math.max(200, ...grouped.map((group) => group.length * 72 + 60));
  const positions = new Map<string, { x: number; y: number }>();
  grouped.forEach((group, column) =>
    group.forEach((node, row) =>
      positions.set(node.id, { x: column * 190 + 10, y: row * 72 + 45 }),
    ),
  );
  if (!nodes.length) return <p>No visible nodes match this view.</p>;
  return (
    <div
      className="tablewrap"
      style={{ maxHeight: 520, overflow: 'auto' }}
      tabIndex={0}
      aria-label="Scrollable evidence graph"
    >
      <svg
        width={width}
        height={height}
        role="group"
        aria-label="Version-bound evidence graph"
        style={{ display: 'block' }}
      >
        <defs>
          <marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#71879b" />
          </marker>
        </defs>
        {kinds.map((kind, column) => (
          <text
            key={kind}
            x={column * 190 + 12}
            y={22}
            fill="currentColor"
            fontSize={13}
            fontWeight={600}
          >
            {kind.replaceAll('_', ' ').toUpperCase()}
          </text>
        ))}
        {edges.map((edge, i) => {
          const from = positions.get(edge.source),
            to = positions.get(edge.target);
          if (!from || !to) return null;
          const forward = to.x > from.x;
          const start = from.x + (forward ? 160 : 0),
            end = to.x + (forward ? 0 : 160);
          const active = edge.source === selected || edge.target === selected;
          return (
            <path
              key={i}
              d={`M${start},${from.y + 24} C${start + (forward ? 40 : -40)},${from.y + 24} ${end + (forward ? -40 : 40)},${to.y + 24} ${end},${to.y + 24}`}
              fill="none"
              stroke={active ? '#15a6a0' : '#71879b'}
              opacity={selected && !active ? 0.2 : 0.7}
              strokeWidth={active ? 2.5 : 1.3}
              markerEnd={`url(#${marker})`}
            >
              <title>{edge.relation}</title>
            </path>
          );
        })}
        {nodes.map((node) => {
          const position = positions.get(node.id);
          if (!position) return null;
          const active = selected === node.id;
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-label={`${node.kind}: ${node.label}, ${node.status}`}
              aria-pressed={active}
              onClick={() => onSelect(node)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(node);
                }
              }}
              style={{ cursor: 'pointer' }}
            >
              <title>
                {node.label} · {node.status}
              </title>
              <rect
                x={position.x}
                y={position.y}
                width={160}
                height={48}
                rx={7}
                fill={active ? '#0a2170' : '#e9f3f8'}
                stroke={active ? '#15a6a0' : '#71879b'}
                strokeWidth={active ? 3 : 1}
              />
              <text
                x={position.x + 8}
                y={position.y + 19}
                fill={active ? '#ffffff' : '#172a45'}
                fontSize={11}
              >
                {node.label.length > 23 ? node.label.slice(0, 22) + '…' : node.label}
              </text>
              <text
                x={position.x + 8}
                y={position.y + 36}
                fill={active ? '#bcecea' : '#526477'}
                fontSize={10}
              >
                {node.status}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

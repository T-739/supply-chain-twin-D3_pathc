import { LINEAGE_NODES } from '@/lib/constants';

/**
 * Lineage strip: `supply-chain-twin` → `supply-chain-twin-D3` →
 * `supply-chain-twin-D3_pathc`. Static copy — does not load
 * runtime data. Answers "how V2 / D3 Path B / D3_pathc relate".
 */
export function LineageStrip() {
  return (
    <section
      className="lineage-strip"
      data-testid="lineage-strip"
      aria-label="Repository lineage"
    >
      <h2 className="lineage-strip__title">Repository lineage</h2>
      <ol className="lineage-strip__nodes">
        {LINEAGE_NODES.map((node, idx) => (
          <li
            key={node.id}
            className="lineage-strip__node"
            data-testid={`lineage-node-${node.id}`}
          >
            <div className="lineage-strip__node-heading">
              <span className="lineage-strip__node-title">{node.title}</span>
              <span className="lineage-strip__node-subtitle">
                {node.subtitle}
              </span>
            </div>
            <p className="lineage-strip__node-role">{node.role}</p>
            {idx < LINEAGE_NODES.length - 1 && (
              <span aria-hidden="true" className="lineage-strip__arrow">
                →
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

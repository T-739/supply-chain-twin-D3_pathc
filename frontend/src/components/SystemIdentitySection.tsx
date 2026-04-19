import { TWO_PATH_SUMMARY } from '@/lib/constants';

/**
 * System identity: what the system IS. Two-path architecture
 * explained in the vocabulary already used by
 * PATH_C_BOUNDARY.md / PATH_C_SCHEMA_REGISTRY.md. No runtime
 * logic, no reinterpretation.
 */
export function SystemIdentitySection() {
  return (
    <section
      className="system-identity"
      data-testid="system-identity"
      aria-label="System identity"
    >
      <h2 className="system-identity__title">System identity</h2>
      <p className="system-identity__lede">
        A supply-chain digital-twin with a frozen deterministic core
        (<strong>Path B</strong>) and an additive adaptive overlay
        (<strong>Path C</strong>). The B5 surface you are looking at
        consumes already-produced session bundles — it does not run the
        twin.
      </p>
      <div className="system-identity__cards">
        {(['pathB', 'pathC', 'contract'] as const).map((key) => {
          const block = TWO_PATH_SUMMARY[key];
          return (
            <article
              key={key}
              className="system-identity__card"
              data-testid={`identity-card-${key}`}
            >
              <h3>{block.title}</h3>
              <p>{block.body}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

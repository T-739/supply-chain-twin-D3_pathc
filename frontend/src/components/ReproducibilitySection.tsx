import { REPRODUCIBILITY_POINTS } from '@/lib/constants';

/**
 * Reproducibility / read-only / bundle-contract section.
 *
 * Points the reader at the three invariants that make B5 output
 * trustworthy: deterministic construction, frozen schemas, and
 * the read-only surface contract.
 */
export function ReproducibilitySection() {
  return (
    <section
      className="reproducibility"
      data-testid="reproducibility"
      aria-label="Reproducibility and bundle contract"
    >
      <h2 className="reproducibility__title">
        Why the outputs are trustworthy
      </h2>
      <ul className="reproducibility__list">
        {REPRODUCIBILITY_POINTS.map((point) => (
          <li key={point.title} className="reproducibility__item">
            <h3>{point.title}</h3>
            <p>{point.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

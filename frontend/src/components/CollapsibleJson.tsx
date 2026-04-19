'use client';

export interface CollapsibleJsonProps {
  value: unknown;
  label?: string;
  defaultOpen?: boolean;
  testid?: string;
}

/**
 * Native <details>/<summary> wrapper around a JSON blob.
 *
 * Kept as a single primitive so the structured inspector
 * panels can offer a raw-JSON fallback without pulling in a
 * full JSON-viewer dependency. The <details> element makes the
 * collapse fully keyboard-accessible with zero custom state.
 */
export function CollapsibleJson({
  value,
  label = 'raw JSON',
  defaultOpen = false,
  testid,
}: CollapsibleJsonProps) {
  return (
    <details
      className="collapsible-json"
      data-testid={testid}
      {...(defaultOpen ? { open: true } : {})}
    >
      <summary className="collapsible-json__summary">{label}</summary>
      <pre
        className="collapsible-json__body"
        data-testid={testid ? `${testid}-body` : undefined}
        aria-label="JSON payload"
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

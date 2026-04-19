import { redirect } from 'next/navigation';

// Root route -> Overview. The Overview is the only real page in
// Phase 2, so the index should land there.
export default function RootRedirect(): never {
  redirect('/overview');
}

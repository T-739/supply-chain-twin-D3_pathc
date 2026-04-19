import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AppShell } from '@/components/AppShell';

import './globals.css';

export const metadata: Metadata = {
  title: 'supply-chain-twin · B5 Overview',
  description:
    'B5 Phase 2 — read-only overview and bundle catalog over the D3 Path C-min + B1–B4 surface.',
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

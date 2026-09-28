import type { Metadata } from 'next';
import './style.css';
export const metadata: Metadata = {title: 'ADI Anvil', description: 'Frontier Evaluation & Diagnostics Platform'};
export default function Layout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}

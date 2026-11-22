import type { Metadata } from 'next';
import './gym.css';

// Browser tab before the page sets its own `<Page> · RL Gym Evaluation · ADI Labs Forge` (shared/BRANDING.md).
export const metadata: Metadata = {
  title: 'RL Gym Evaluation · ADI Labs Forge',
  description: 'RL Gym Evaluation · ADI Labs Forge',
};

export default function GymLayout({ children }: { children: React.ReactNode }) {
  return children;
}

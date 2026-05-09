interface BentoGridProps {
  children: React.ReactNode;
}

export function BentoGrid({ children }: BentoGridProps) {
  return <div className="dashboard-grid content-bento-grid">{children}</div>;
}

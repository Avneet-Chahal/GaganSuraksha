import React from 'react';
import type { RiskLevel } from '../../api/types';

interface RiskBadgeProps {
  level: RiskLevel;
  className?: string;
  size?: 'sm' | 'md';
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({ level, className = '', size = 'md' }) => {
  const isSm = size === 'sm';

  switch (level) {
    case 'CRITICAL':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded border border-rose-500/30 bg-rose-500/10 ${
            isSm ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-0.5 text-xs'
          } font-medium text-rose-400 font-mono tracking-tight ${className}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
          Critical Risk
        </span>
      );
    case 'WARNING':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded border border-amber-500/30 bg-amber-500/10 ${
            isSm ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-0.5 text-xs'
          } font-medium text-amber-400 font-mono tracking-tight ${className}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Warning
        </span>
      );
    case 'NOMINAL':
    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded border border-emerald-500/30 bg-emerald-500/10 ${
            isSm ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-0.5 text-xs'
          } font-medium text-emerald-400 font-mono tracking-tight ${className}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Nominal
        </span>
      );
  }
};

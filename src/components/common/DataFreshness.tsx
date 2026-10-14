import React from 'react';
import { RefreshCw } from 'lucide-react';

interface DataFreshnessProps {
  lastUpdatedUtc?: string;
  source?: string;
  isFetching?: boolean;
  isDemo?: boolean;
  onRefresh?: () => void;
  className?: string;
}

export const DataFreshness: React.FC<DataFreshnessProps> = ({
  lastUpdatedUtc = '12:00 UTC',
  source = 'Public TLE',
  isFetching = false,
  isDemo = false,
  onRefresh,
  className = '',
}) => {
  return (
    <div className={`inline-flex items-center gap-2 text-xs text-slate-400 font-mono ${className}`}>
      <span className="flex items-center gap-1.5">
        {isDemo ? (
          // Static dot for demo data
          <span className="inline-flex rounded-full h-2 w-2 bg-amber-400/90" title="Static demo feed" />
        ) : (
          // Pulsing dot for live data
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-40" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
        )}
        <span>
          {isDemo ? (
            <span className="text-amber-300/90">Demo data</span>
          ) : (
            <span>Data updated</span>
          )}{' '}
          <span className="text-slate-300">({lastUpdatedUtc})</span>
        </span>
      </span>

      {source && (
        <span className="hidden sm:inline-block text-slate-500">
          • <span className="text-slate-400">{source}</span>
        </span>
      )}

      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={isFetching}
          title="Refresh data feed"
          className="p-1 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-aerospace disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      )}
    </div>
  );
};

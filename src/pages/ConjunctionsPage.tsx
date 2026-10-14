import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, ArrowUpDown, ChevronRight, ShieldAlert, Orbit, RefreshCw } from 'lucide-react';
import { fetchConjunctions } from '../api/client';
import type { RiskLevel } from '../api/types';
import { RiskBadge } from '../components/common/RiskBadge';
import { formatUtcDateTime } from '../hooks/useUtcClock';
import { useSimulationStore } from '../store/simulationStore';

export const ConjunctionsPage: React.FC = () => {
  const navigate = useNavigate();
  const highlightConjunction = useSimulationStore((s) => s.highlightConjunction);

  const [searchTerm, setSearchTerm] = useState('');
  const [riskFilter, setRiskFilter] = useState<'ALL' | RiskLevel>('ALL');
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [sortField, setSortField] = useState<'tca' | 'missDistance' | 'pc'>('pc');
  const [sortAsc, setSortAsc] = useState(false);

  // Poll conjunctions every 30 seconds
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['conjunctions'],
    queryFn: fetchConjunctions,
    refetchInterval: 30000,
  });

  const conjunctions = useMemo(() => data?.data || [], [data?.data]);
  const isDemo = data?.isDemo || (conjunctions.length > 0 && conjunctions[0]?.dataSource === 'demo');

  // Filter and sort conjunctions
  const filteredConjunctions = useMemo(() => {
    return conjunctions
      .filter((conj) => {
        // Search term
        const query = searchTerm.toLowerCase();
        const matchesSearch =
          conj.primarySat.name.toLowerCase().includes(query) ||
          conj.secondarySat.name.toLowerCase().includes(query) ||
          conj.primarySat.noradId.toString().includes(query) ||
          conj.secondarySat.noradId.toString().includes(query) ||
          conj.id.toLowerCase().includes(query);

        if (!matchesSearch) return false;

        // Risk level filter
        if (riskFilter !== 'ALL' && conj.riskLevel !== riskFilter) return false;

        // Watchlist only
        if (watchlistOnly && !conj.primarySat.isWatchlist) return false;

        return true;
      })
      .sort((a, b) => {
        let cmp = 0;
        if (sortField === 'tca') {
          cmp = a.tcaMs - b.tcaMs;
        } else if (sortField === 'missDistance') {
          cmp = a.missDistanceKm - b.missDistanceKm;
        } else if (sortField === 'pc') {
          cmp = b.calibratedProbability - a.calibratedProbability;
        }
        return sortAsc ? -cmp : cmp;
      });
  }, [conjunctions, searchTerm, riskFilter, watchlistOnly, sortField, sortAsc]);

  const toggleSort = (field: 'tca' | 'missDistance' | 'pc') => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] text-slate-200 px-4 md:px-8 py-6 max-w-7xl mx-auto flex flex-col gap-5">
      {/* Block 1: Page Header with Data Status */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-white/[0.08] pb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <ShieldAlert className="w-4 h-4 text-cyan-400" />
            <h1 className="text-xl font-semibold text-white tracking-tight">
              Conjunction Assessment
            </h1>
            {isDemo && (
              <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Demo data
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 max-w-xl">
            Orbital close approaches detected from public TLE surveillance. Collision risk probabilities are calibrated with Gagan Suraksha ML drag and covariance correction models.
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Auto-refreshing (30s)</span>
          </span>
          <span>•</span>
          <span>Data updated 12:15 UTC</span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh conjunction data"
            className="p-1 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-aerospace"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Block 2: Filters and Search Controls */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-3 flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        {/* Search Input */}
        <div className="relative w-full md:w-80">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search satellite name or NORAD ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#070B12] border border-white/[0.08] rounded-md pl-8 pr-3 py-1.5 text-slate-200 placeholder-slate-500 font-mono text-xs focus:outline-none focus:border-cyan-500/50"
          />
        </div>

        {/* Filter Badges */}
        <div className="flex items-center gap-2 w-full md:w-auto overflow-x-auto">
          {/* Risk Filters */}
          <div className="flex items-center bg-[#070B12] p-0.5 rounded border border-white/[0.04]">
            {(['ALL', 'CRITICAL', 'WARNING', 'NOMINAL'] as const).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setRiskFilter(lvl)}
                className={`px-2.5 py-1 rounded text-[11px] font-mono transition-aerospace ${
                  riskFilter === lvl
                    ? 'bg-slate-800 text-cyan-300 font-medium'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {lvl === 'ALL' ? 'All Risks' : lvl}
              </button>
            ))}
          </div>

          {/* Watchlist Toggle */}
          <button
            onClick={() => setWatchlistOnly(!watchlistOnly)}
            className={`px-2.5 py-1.5 rounded border text-[11px] font-mono transition-aerospace flex items-center gap-1.5 ${
              watchlistOnly
                ? 'bg-cyan-950/40 border-cyan-500/40 text-cyan-300'
                : 'border-white/[0.08] bg-[#070B12] text-slate-400 hover:text-slate-200'
            }`}
          >
            <Orbit className="w-3.5 h-3.5" />
            <span>Watchlist Only</span>
          </button>
        </div>
      </div>

      {/* Block 3: Clean Conjunctions Table */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/[0.08] bg-[#070B12]/80 text-slate-400 font-mono text-[11px] uppercase tracking-wider select-none">
                <th className="py-3 px-4">Object Pair</th>
                <th
                  onClick={() => toggleSort('tca')}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-400 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>TCA (UTC)</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort('missDistance')}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-400 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>Miss Dist (km)</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="py-3 px-4">Rel V (km/s)</th>
                <th
                  onClick={() => toggleSort('pc')}
                  className="py-3 px-4 cursor-pointer hover:text-cyan-400 transition-colors"
                >
                  <div className="flex items-center gap-1">
                    <span>Calibrated Pc</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="py-3 px-4">Risk Status</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 font-mono">
                    Loading conjunction stream...
                  </td>
                </tr>
              ) : filteredConjunctions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 font-mono">
                    No conjunction events found matching the active filters.
                  </td>
                </tr>
              ) : (
                filteredConjunctions.map((conj) => (
                  <tr
                    key={conj.id}
                    onClick={() => navigate(`/conjunctions/${conj.id}`)}
                    className="hover:bg-slate-800/40 cursor-pointer transition-aerospace group"
                  >
                    {/* Object Pair */}
                    <td className="py-3 px-4">
                      <div className="flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-100 group-hover:text-cyan-300 transition-colors">
                            {conj.primarySat.name}
                          </span>
                          <span className="text-[10px] font-mono text-cyan-400/90 bg-cyan-950/30 px-1 py-0.2 rounded border border-cyan-500/20">
                            #{conj.primarySat.noradId}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-400 font-mono text-[11px]">
                          <span className="text-slate-500">vs</span>
                          <span>{conj.secondarySat.name}</span>
                          <span className="text-[10px] text-slate-500">#{conj.secondarySat.noradId}</span>
                        </div>
                      </div>
                    </td>

                    {/* TCA (UTC) */}
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {formatUtcDateTime(conj.tcaUtc)}
                    </td>

                    {/* Miss Distance */}
                    <td className="py-3 px-4 font-mono">
                      <span
                        className={`font-semibold ${
                          conj.missDistanceKm < 0.5
                            ? 'text-rose-400'
                            : conj.missDistanceKm < 1.0
                            ? 'text-amber-400'
                            : 'text-slate-200'
                        }`}
                      >
                        {conj.missDistanceKm.toFixed(3)}
                      </span>
                      <span className="text-slate-500 ml-1">km</span>
                    </td>

                    {/* Rel V */}
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {conj.relativeVelocityKmS.toFixed(2)}
                      <span className="text-slate-500 ml-1">km/s</span>
                    </td>

                    {/* Calibrated Pc */}
                    <td className="py-3 px-4 font-mono">
                      <div className="flex flex-col">
                        <span
                          className={`font-semibold ${
                            (conj.pcMlCalibrated ?? conj.calibratedProbability) > 1e-4
                              ? 'text-rose-400'
                              : (conj.pcMlCalibrated ?? conj.calibratedProbability) > 1e-5
                              ? 'text-amber-400'
                              : 'text-slate-300'
                          }`}
                        >
                          {(conj.pcMlCalibrated ?? conj.calibratedProbability).toExponential(2)}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          raw: {(conj.pcRaw ?? conj.rawProbability).toExponential(2)}
                        </span>
                      </div>
                    </td>

                    {/* Risk Badge */}
                    <td className="py-3 px-4">
                      <RiskBadge level={conj.riskLevel} size="sm" />
                    </td>

                    {/* Action */}
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            highlightConjunction(conj.id, true);
                            navigate('/simulator');
                          }}
                          title="View 3D Trajectory"
                          className="px-2 py-1 rounded bg-[#070B12] hover:bg-slate-800 text-[11px] font-mono text-cyan-400 border border-white/[0.06] transition-aerospace"
                        >
                          3D
                        </button>
                        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 transition-colors" />
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

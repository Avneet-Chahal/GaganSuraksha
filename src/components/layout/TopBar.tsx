import React from 'react';
import { NavLink } from 'react-router-dom';
import { Orbit, ShieldAlert, Cpu, BarChart3, Radio, Database } from 'lucide-react';
import { useUtcClock } from '../../hooks/useUtcClock';
import { DataFreshness } from '../common/DataFreshness';
import { useSimulationStore } from '../../store/simulationStore';

export const TopBar: React.FC = () => {
  const utcClock = useUtcClock();
  const isDemoMode = useSimulationStore((s) => s.isDemoMode);

  const navItems = [
    { to: '/simulator', label: 'Simulator', icon: Orbit },
    { to: '/conjunctions', label: 'Conjunctions', icon: ShieldAlert },
    { to: '/conjunctions/CONJ-2026-NETRA-01', label: 'Maneuvers', icon: Cpu },
    { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    { to: '/watchlist', label: 'Watchlist', icon: Radio },
  ];

  return (
    <header className="h-12 border-b border-white/[0.08] bg-[#070B12]/95 backdrop-blur-sm px-4 flex items-center justify-between select-none z-30 sticky top-0">
      {/* Wordmark & Agency Identification */}
      <div className="flex items-center gap-6">
        <NavLink to="/simulator" className="flex items-center gap-2.5 group">
          <div className="w-6 h-6 rounded bg-[#0D131D] border border-cyan-500/40 flex items-center justify-center text-cyan-400 group-hover:border-cyan-400 transition-aerospace">
            <Orbit className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold tracking-wide text-slate-100">
              Gagan Suraksha
            </span>
            <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-500/90 font-medium hidden md:inline">
              ISRO ISTRAC • NETRA SSA
            </span>
          </div>
        </NavLink>

        {/* Navigation links */}
        <nav className="hidden lg:flex items-center gap-1 text-xs">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5 transition-aerospace ${
                    isActive
                      ? 'text-cyan-400 bg-cyan-950/30 border border-cyan-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
                  }`
                }
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Right controls: UTC Clock, Data Freshness, Demo Data Badge */}
      <div className="flex items-center gap-4 text-xs font-mono">
        {/* Data freshness */}
        <DataFreshness lastUpdatedUtc="12:15 UTC" source="NETRA" />

        {/* Demo Mode Badge */}
        {isDemoMode && (
          <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 text-[11px] font-mono">
            <Database className="w-2.5 h-2.5" />
            Demo data
          </span>
        )}

        {/* Live Mission Control UTC Clock */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#0D131D] border border-white/[0.08] text-slate-200 font-mono text-[11px] tabular-nums">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>{utcClock}</span>
        </div>
      </div>
    </header>
  );
};

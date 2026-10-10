import React from 'react';
import {
  Crosshair,
  RotateCcw,
  Layers,
  CircleDot,
  Radio,
  Filter,
  Database,
} from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';
import type { RegimeFilter } from '../../store/simulationStore';

export const SimulationToolbar: React.FC = () => {
  const showOrbits = useSimulationStore((s) => s.showOrbits);
  const showDebris = useSimulationStore((s) => s.showDebris);
  const showSatellites = useSimulationStore((s) => s.showSatellites);
  const orbitRegimeFilter = useSimulationStore((s) => s.orbitRegimeFilter);
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const focusedObjectId = useSimulationStore((s) => s.focusedObjectId);
  const isDemoMode = useSimulationStore((s) => s.isDemoMode);

  const toggleOrbits = useSimulationStore((s) => s.toggleOrbits);
  const toggleDebris = useSimulationStore((s) => s.toggleDebris);
  const toggleSatellites = useSimulationStore((s) => s.toggleSatellites);
  const setRegimeFilter = useSimulationStore((s) => s.setRegimeFilter);
  const focusObject = useSimulationStore((s) => s.focusObject);
  const setIsDemoMode = useSimulationStore((s) => s.setIsDemoMode);

  const cycleRegime = () => {
    const list: RegimeFilter[] = ['ALL', 'LEO', 'MEO', 'GEO'];
    const currIdx = list.indexOf(orbitRegimeFilter);
    const next = list[(currIdx + 1) % list.length];
    setRegimeFilter(next);
  };

  const handleFocus = () => {
    if (focusedObjectId) {
      focusObject(null);
    } else if (selectedObjectId) {
      focusObject(selectedObjectId);
    }
  };

  const handleResetView = () => {
    focusObject(null);
    window.dispatchEvent(new CustomEvent('reset-3d-view'));
  };

  return (
    <aside
      aria-label="Simulation Controls"
      className="absolute top-4 left-4 z-20 flex flex-col items-center w-12 bg-[#0D131D]/90 backdrop-blur-md border border-white/[0.08] rounded-lg p-1.5 gap-1.5 shadow-xl select-none"
    >
      {/* Focus selected object */}
      <button
        onClick={handleFocus}
        disabled={!selectedObjectId}
        title={
          focusedObjectId
            ? 'Unfocus camera'
            : selectedObjectId
            ? 'Focus camera on selected object'
            : 'Select an object to focus'
        }
        className={`w-9 h-9 rounded flex items-center justify-center transition-aerospace ${
          focusedObjectId
            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
            : selectedObjectId
            ? 'text-slate-300 hover:text-white hover:bg-slate-800'
            : 'text-slate-600 cursor-not-allowed'
        }`}
      >
        <Crosshair className="w-4 h-4" />
      </button>

      {/* Reset view */}
      <button
        onClick={handleResetView}
        title="Reset camera view"
        className="w-9 h-9 rounded flex items-center justify-center text-slate-300 hover:text-white hover:bg-slate-800 transition-aerospace"
      >
        <RotateCcw className="w-4 h-4" />
      </button>

      <div className="w-6 h-[1px] bg-white/[0.08] my-0.5" />

      {/* Toggle Orbit Paths */}
      <button
        onClick={toggleOrbits}
        title={`Orbit paths: ${showOrbits} (Click to cycle)`}
        className={`w-9 h-9 rounded flex flex-col items-center justify-center transition-aerospace relative ${
          showOrbits !== 'NONE'
            ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-500/30'
            : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
        }`}
      >
        <Layers className="w-4 h-4" />
        <span className="text-[8px] font-mono leading-none mt-0.5">
          {showOrbits === 'WATCHLIST' ? 'WL' : showOrbits === 'ALL' ? 'ALL' : 'OFF'}
        </span>
      </button>

      {/* Toggle Satellites */}
      <button
        onClick={toggleSatellites}
        title={`Satellites layer: ${showSatellites ? 'Visible' : 'Hidden'}`}
        className={`w-9 h-9 rounded flex items-center justify-center transition-aerospace ${
          showSatellites
            ? 'text-cyan-400 hover:bg-slate-800'
            : 'text-slate-600 hover:text-slate-400'
        }`}
      >
        <Radio className="w-4 h-4" />
      </button>

      {/* Toggle Debris */}
      <button
        onClick={toggleDebris}
        title={`Debris layer: ${showDebris ? 'Visible' : 'Hidden'}`}
        className={`w-9 h-9 rounded flex items-center justify-center transition-aerospace ${
          showDebris
            ? 'text-slate-300 hover:text-white hover:bg-slate-800'
            : 'text-slate-600 hover:text-slate-400'
        }`}
      >
        <CircleDot className="w-4 h-4" />
      </button>

      <div className="w-6 h-[1px] bg-white/[0.08] my-0.5" />

      {/* Filter Regime (LEO, MEO, GEO, ALL) */}
      <button
        onClick={cycleRegime}
        title={`Filter Orbit Regime: ${orbitRegimeFilter} (Click to cycle)`}
        className="w-9 h-9 rounded flex flex-col items-center justify-center text-slate-300 hover:text-cyan-300 hover:bg-slate-800 transition-aerospace"
      >
        <Filter className="w-3.5 h-3.5" />
        <span className="text-[8px] font-mono font-semibold text-cyan-400 leading-none mt-0.5">
          {orbitRegimeFilter}
        </span>
      </button>

      {/* Toggle Demo Mode Indicator */}
      <button
        onClick={() => setIsDemoMode(!isDemoMode)}
        title={isDemoMode ? 'Demo data active (Click to simulate live)' : 'Live data feed active'}
        className={`w-9 h-9 rounded flex items-center justify-center transition-aerospace ${
          isDemoMode
            ? 'text-amber-400 hover:bg-slate-800'
            : 'text-emerald-400 hover:bg-slate-800'
        }`}
      >
        <Database className="w-3.5 h-3.5" />
      </button>
    </aside>
  );
};

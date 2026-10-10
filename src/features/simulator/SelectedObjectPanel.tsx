import React from 'react';
import { useNavigate } from 'react-router-dom';
import { X, AlertTriangle, ShieldCheck, Crosshair, ArrowUpRight } from 'lucide-react';
import { ALL_SATELLITES_CATALOG, CONJUNCTION_EVENTS } from '../../api/mockData';
import { useSimulationStore } from '../../store/simulationStore';
import { RiskBadge } from '../../components/common/RiskBadge';
import { formatUtcDateTime } from '../../hooks/useUtcClock';

export const SelectedObjectPanel: React.FC = () => {
  const navigate = useNavigate();
  const selectedObjectId = useSimulationStore((s) => s.selectedObjectId);
  const rightPanelOpen = useSimulationStore((s) => s.rightPanelOpen);
  const setRightPanelOpen = useSimulationStore((s) => s.setRightPanelOpen);
  const selectObject = useSimulationStore((s) => s.selectObject);
  const focusObject = useSimulationStore((s) => s.focusObject);
  const highlightConjunction = useSimulationStore((s) => s.highlightConjunction);

  if (!rightPanelOpen || !selectedObjectId) return null;

  const obj = ALL_SATELLITES_CATALOG.find((s) => s.id === selectedObjectId);
  if (!obj) return null;

  // Check if there is an active close approach event involving this object
  const closeApproachEvent = CONJUNCTION_EVENTS.find(
    (c) => c.primarySat.id === obj.id || c.secondarySat.id === obj.id
  );

  const isPrimary = closeApproachEvent?.primarySat.id === obj.id;
  const targetCounterpart = isPrimary
    ? closeApproachEvent?.secondarySat
    : closeApproachEvent?.primarySat;

  return (
    <aside
      aria-label="Selected Object Telemetry"
      className="absolute top-4 right-4 z-20 w-80 max-w-[calc(100vw-2rem)] bg-[#0D131D]/95 backdrop-blur-md border border-white/[0.08] rounded-lg shadow-2xl p-4 flex flex-col gap-3.5 select-none transition-aerospace"
    >
      {/* Header with Title, NORAD ID, and Close */}
      <div className="flex items-start justify-between border-b border-white/[0.08] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-white tracking-tight">
              {obj.name}
            </h2>
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                obj.type === 'DEBRIS'
                  ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                  : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
              }`}
            >
              {obj.type}
            </span>
          </div>
          <div className="text-xs text-slate-400 font-mono mt-0.5 flex items-center gap-2">
            <span>NORAD #{obj.noradId}</span>
            <span>•</span>
            <span>{obj.regime}</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => focusObject(obj.id)}
            title="Focus camera"
            className="p-1 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-aerospace"
          >
            <Crosshair className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => {
              setRightPanelOpen(false);
              selectObject(null);
            }}
            title="Close panel"
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-aerospace"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Primary Orbital Telemetry Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div className="bg-[#070B12] rounded p-2 border border-white/[0.04]">
          <span className="text-[10px] text-slate-500 block">ALTITUDE</span>
          <span className="text-slate-100 font-semibold">{obj.altitudeKm.toLocaleString()} km</span>
        </div>
        <div className="bg-[#070B12] rounded p-2 border border-white/[0.04]">
          <span className="text-[10px] text-slate-500 block">VELOCITY</span>
          <span className="text-slate-100 font-semibold">{obj.velocityKmS.toFixed(2)} km/s</span>
        </div>
        <div className="bg-[#070B12] rounded p-2 border border-white/[0.04]">
          <span className="text-[10px] text-slate-500 block">INCLINATION</span>
          <span className="text-slate-100 font-semibold">{obj.inclinationDeg}°</span>
        </div>
        <div className="bg-[#070B12] rounded p-2 border border-white/[0.04]">
          <span className="text-[10px] text-slate-500 block">PERIOD</span>
          <span className="text-slate-100 font-semibold">{obj.periodMin} min</span>
        </div>
      </div>

      {/* Epoch & Operator details */}
      <div className="text-[11px] font-mono text-slate-400 border-t border-white/[0.06] pt-2 flex flex-col gap-1">
        <div className="flex justify-between">
          <span className="text-slate-500">Operator</span>
          <span className="text-slate-200">{obj.operator || obj.ownerCountry}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">TLE Epoch (UTC)</span>
          <span className="text-slate-300">{formatUtcDateTime(obj.tleEpoch).slice(0, 16)}</span>
        </div>
      </div>

      {/* Close Approach Conjunction Card */}
      {closeApproachEvent ? (
        <div className="rounded border border-rose-500/30 bg-rose-950/20 p-2.5 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-rose-300 uppercase tracking-wider flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              Close Approach Alert
            </span>
            <RiskBadge level={closeApproachEvent.riskLevel} size="sm" />
          </div>

          <div className="text-xs text-slate-300">
            Conjunction with <strong className="text-white">{targetCounterpart?.name}</strong>
          </div>

          <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono">
            <div className="bg-[#070B12]/80 p-1.5 rounded">
              <span className="text-slate-500 text-[9px] block">MISS DISTANCE</span>
              <span className="text-rose-300 font-semibold">
                {closeApproachEvent.missDistanceKm.toFixed(3)} km
              </span>
            </div>
            <div className="bg-[#070B12]/80 p-1.5 rounded">
              <span className="text-slate-500 text-[9px] block">REL VELOCITY</span>
              <span className="text-slate-200 font-semibold">
                {closeApproachEvent.relativeVelocityKmS.toFixed(2)} km/s
              </span>
            </div>
            <div className="bg-[#070B12]/80 p-1.5 rounded col-span-2">
              <span className="text-slate-500 text-[9px] block">TCA (UTC)</span>
              <span className="text-slate-200 font-semibold">
                {formatUtcDateTime(closeApproachEvent.tcaUtc)}
              </span>
            </div>
            <div className="bg-[#070B12]/80 p-1.5 rounded col-span-2 flex justify-between items-center">
              <div>
                <span className="text-slate-500 text-[9px] block">CALIBRATED Pc</span>
                <span className="text-amber-300 font-semibold">
                  {closeApproachEvent.calibratedProbability.toExponential(2)}
                </span>
              </div>
              <div className="text-right">
                <span className="text-slate-500 text-[9px] block">RAW Pc</span>
                <span className="text-slate-400 line-through">
                  {closeApproachEvent.rawProbability.toExponential(2)}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 mt-1">
            <button
              onClick={() => highlightConjunction(closeApproachEvent.id, true)}
              className="flex-1 py-1 px-2 rounded bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 transition-aerospace"
            >
              Inspect at TCA
            </button>
            <button
              onClick={() => navigate(`/conjunctions/${closeApproachEvent.id}`)}
              className="flex-1 py-1 px-2 rounded bg-cyan-600 hover:bg-cyan-500 text-xs font-medium text-white flex items-center justify-center gap-1 transition-aerospace"
            >
              <span>Maneuver</span>
              <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded border border-emerald-500/20 bg-emerald-950/10 p-2.5 flex items-center gap-2 text-xs text-emerald-400 font-mono">
          <ShieldCheck className="w-4 h-4 shrink-0" />
          <span>Nominal orbit trajectory. No predicted close approaches &lt; 5.0 km within 7 days.</span>
        </div>
      )}
    </aside>
  );
};

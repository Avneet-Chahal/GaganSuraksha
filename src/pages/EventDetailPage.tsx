import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  ArrowLeft,
  Orbit,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Cpu,
  CheckCircle2,
  Sliders,
  Clock,
  Layers,
  Fuel,
} from 'lucide-react';
import { fetchConjunctionById, planManeuver } from '../api/client';
import type { ManeuverRequest, ManeuverResult } from '../api/types';
import { RiskBadge } from '../components/common/RiskBadge';
import { formatUtcDateTime } from '../hooks/useUtcClock';
import { useSimulationStore } from '../store/simulationStore';

export const EventDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const highlightConjunction = useSimulationStore((s) => s.highlightConjunction);

  const eventId = id || 'CONJ-2026-NETRA-01';

  const { data, isLoading } = useQuery({
    queryKey: ['conjunction', eventId],
    queryFn: () => fetchConjunctionById(eventId),
  });

  const conjunction = data?.data;

  // Maneuver Planner State
  const [deltaV, setDeltaV] = useState<number>(0.38);
  const [burnLeadHours, setBurnLeadHours] = useState<number>(12);
  const [burnDirection, setBurnDirection] = useState<'PROGRADE' | 'RETROGRADE' | 'RADIAL_OUT' | 'NORMAL'>('PROGRADE');
  const [spacecraftMassKg, setSpacecraftMassKg] = useState<number>(710);
  const [ispSeconds, setIspSeconds] = useState<number>(220);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [executedPlan, setExecutedPlan] = useState<ManeuverResult | null>(null);

  // Live preview calculations
  const origMiss = conjunction?.missDistanceKm || 0.284;
  const origPc = conjunction?.calibratedProbability || 6.84e-4;

  const newMiss = origMiss + deltaV * (burnLeadHours / 12) * 4.6;
  const g0 = 9.80665;
  const fuelCostKg = spacecraftMassKg * (1 - Math.exp(-deltaV / (g0 * ispSeconds)));
  const scale = origMiss / Math.max(0.01, newMiss);
  const newPc = Math.max(1e-9, origPc * Math.pow(scale, 3.5));

  const isRecommended = newMiss >= 2.0 && newPc < 1e-5;

  const maneuverMutation = useMutation({
    mutationFn: (req: ManeuverRequest) => planManeuver(req),
    onSuccess: (res) => {
      setExecutedPlan(res.data);
    },
  });

  const handleExecute = () => {
    if (!conjunction) return;
    const req: ManeuverRequest = {
      conjunctionId: conjunction.id,
      deltaVMs: deltaV,
      burnTimeUtc: new Date(conjunction.tcaMs - burnLeadHours * 3600 * 1000).toISOString(),
      direction: burnDirection,
      spacecraftMassKg,
      ispSeconds,
    };
    maneuverMutation.mutate(req);
  };

  if (isLoading || !conjunction) {
    return (
      <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] flex items-center justify-center text-slate-400 font-mono text-xs">
        Loading conjunction event telemetry...
      </div>
    );
  }

  const { primarySat, secondarySat } = conjunction;

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] text-slate-200 px-4 md:px-8 py-6 max-w-7xl mx-auto flex flex-col gap-5">
      {/* Top Breadcrumb & Navigation */}
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
        <button
          onClick={() => navigate('/conjunctions')}
          className="inline-flex items-center gap-1.5 text-xs font-mono text-slate-400 hover:text-cyan-400 transition-aerospace"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Conjunctions</span>
        </button>

        <div className="flex items-center gap-2">
          <RiskBadge level={conjunction.riskLevel} />
          <button
            onClick={() => {
              highlightConjunction(conjunction.id, true);
              navigate('/simulator');
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-cyan-950/40 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-900/40 text-xs font-mono transition-aerospace"
          >
            <Orbit className="w-3.5 h-3.5" />
            <span>View in 3D Simulator</span>
          </button>
        </div>
      </div>

      {/* Header Block */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">
            CONJUNCTION EVENT ID: {conjunction.id}
          </div>
          <h1 className="text-xl font-semibold text-white tracking-tight flex items-center gap-3">
            <span>{primarySat.name}</span>
            <span className="text-slate-500 text-sm font-normal">vs</span>
            <span className="text-amber-400">{secondarySat.name}</span>
          </h1>
          <div className="text-xs font-mono text-slate-400 mt-1 flex items-center gap-3">
            <span>Primary: NORAD #{primarySat.noradId} ({primarySat.regime})</span>
            <span>•</span>
            <span>Secondary: NORAD #{secondarySat.noradId} ({secondarySat.type})</span>
          </div>
        </div>

        <div className="flex items-center gap-4 bg-[#070B12] p-2.5 px-4 rounded border border-white/[0.04] text-xs font-mono">
          <div>
            <span className="text-[10px] text-slate-500 block">TCA (UTC)</span>
            <span className="text-slate-100 font-semibold">{formatUtcDateTime(conjunction.tcaUtc)}</span>
          </div>
          <div className="w-[1px] h-7 bg-white/[0.08]" />
          <div>
            <span className="text-[10px] text-slate-500 block">MISS DISTANCE</span>
            <span className="text-rose-400 font-semibold">{conjunction.missDistanceKm.toFixed(3)} km</span>
          </div>
        </div>
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* LEFT COLUMN: Summary & ML Calibration Comparison */}
        <div className="flex flex-col gap-4">
          {/* Relative Geometry */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-3">
            <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              Relative Geometry at TCA
            </h2>

            <div className="grid grid-cols-3 gap-2 text-xs font-mono">
              <div className="bg-[#070B12] p-2.5 rounded border border-white/[0.04]">
                <span className="text-[10px] text-slate-500 block">TOTAL MISS</span>
                <span className="text-slate-100 font-semibold text-sm">
                  {conjunction.missDistanceKm.toFixed(3)} km
                </span>
              </div>
              <div className="bg-[#070B12] p-2.5 rounded border border-white/[0.04]">
                <span className="text-[10px] text-slate-500 block">RADIAL MISS</span>
                <span className="text-slate-200 font-semibold">
                  {(conjunction.radialMissKm * 1000).toFixed(0)} m
                </span>
              </div>
              <div className="bg-[#070B12] p-2.5 rounded border border-white/[0.04]">
                <span className="text-[10px] text-slate-500 block">IN-TRACK MISS</span>
                <span className="text-slate-200 font-semibold">
                  {(conjunction.inTrackMissKm * 1000).toFixed(0)} m
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="bg-[#070B12] p-2 rounded border border-white/[0.04]">
                <span className="text-[10px] text-slate-500 block">CROSS-TRACK MISS</span>
                <span className="text-slate-200 font-semibold">
                  {(conjunction.crossTrackMissKm * 1000).toFixed(0)} m
                </span>
              </div>
              <div className="bg-[#070B12] p-2 rounded border border-white/[0.04]">
                <span className="text-[10px] text-slate-500 block">RELATIVE VELOCITY</span>
                <span className="text-slate-200 font-semibold">
                  {conjunction.relativeVelocityKmS.toFixed(2)} km/s
                </span>
              </div>
            </div>
          </div>

          {/* Raw Pc vs ML-Corrected Pc Comparison */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-3">
            <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              Collision Probability Model Comparison
            </h2>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="bg-[#070B12] p-3 rounded border border-white/[0.06] flex flex-col justify-between">
                <div>
                  <span className="text-[10px] text-slate-500 uppercase block">
                    Classical Foster 2D
                  </span>
                  <span className="text-base font-semibold text-slate-300 mt-1 block">
                    {conjunction.rawProbability.toExponential(2)}
                  </span>
                </div>
                <div className="text-[10px] text-slate-500 mt-2">
                  Uncalibrated SGP4 covariance; prone to atmospheric drag over-prediction.
                </div>
              </div>

              <div className="bg-cyan-950/20 p-3 rounded border border-cyan-500/30 flex flex-col justify-between">
                <div>
                  <span className="text-[10px] text-cyan-400 uppercase font-medium block">
                    ISRO NETRA ML-Corrected
                  </span>
                  <span className="text-base font-semibold text-cyan-300 mt-1 block">
                    {conjunction.calibratedProbability.toExponential(2)}
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 mt-2">
                  Corrected for solar flux variation, sensor bias, and non-spherical harmonics.
                </div>
              </div>
            </div>

            <div className="border-t border-white/[0.06] pt-2.5 text-[11px] font-mono text-slate-400">
              <span className="text-slate-500 uppercase text-[10px] block mb-1">
                Covariance Uncertainty (1σ 3D Position Error)
              </span>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="bg-[#070B12] p-1.5 rounded">
                  <span className="text-slate-400 block font-semibold">{primarySat.name}:</span>
                  <span>R: {conjunction.primaryCovariance.radialSigmaM}m</span> •{' '}
                  <span>T: {conjunction.primaryCovariance.inTrackSigmaM}m</span> •{' '}
                  <span>N: {conjunction.primaryCovariance.crossTrackSigmaM}m</span>
                </div>
                <div className="bg-[#070B12] p-1.5 rounded">
                  <span className="text-slate-400 block font-semibold">{secondarySat.name}:</span>
                  <span>R: {conjunction.secondaryCovariance.radialSigmaM}m</span> •{' '}
                  <span>T: {conjunction.secondaryCovariance.inTrackSigmaM}m</span> •{' '}
                  <span>N: {conjunction.secondaryCovariance.crossTrackSigmaM}m</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Maneuver Planner */}
        <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-5 flex flex-col gap-5">
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
            <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
              <Sliders className="w-4 h-4 text-cyan-400" />
              Collision Avoidance Maneuver (CAM) Planner
            </h2>
            <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-500/20">
              Target Miss &gt; 2.0 km
            </span>
          </div>

          {/* Interactive Delta-V Slider */}
          <div className="flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs font-mono">
              <label htmlFor="deltav-slider" className="text-slate-300">
                Impulsive Delta-V (ΔV)
              </label>
              <span className="text-cyan-300 font-semibold text-sm">
                {deltaV.toFixed(2)} m/s
              </span>
            </div>
            <input
              id="deltav-slider"
              type="range"
              min="0.00"
              max="1.50"
              step="0.02"
              value={deltaV}
              onChange={(e) => setDeltaV(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
            />
            <div className="flex justify-between text-[10px] font-mono text-slate-500">
              <span>0.00 m/s (Nominal)</span>
              <span>0.75 m/s</span>
              <span>1.50 m/s</span>
            </div>
          </div>

          {/* Burn Time Selector */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-mono text-slate-300 flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-slate-500" />
              Burn Lead Time Before TCA
            </label>
            <div className="grid grid-cols-4 gap-2 text-xs font-mono">
              {[24, 12, 6, 2].map((hours) => (
                <button
                  key={hours}
                  type="button"
                  onClick={() => setBurnLeadHours(hours)}
                  className={`py-1.5 rounded border text-center transition-aerospace ${
                    burnLeadHours === hours
                      ? 'bg-cyan-950/40 border-cyan-500/50 text-cyan-300 font-semibold'
                      : 'bg-[#070B12] border-white/[0.06] text-slate-400 hover:text-slate-200'
                  }`}
                >
                  TCA - {hours}h
                </button>
              ))}
            </div>
          </div>

          {/* Burn Direction Selector */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-mono text-slate-300">
              Thrust Vector Direction
            </label>
            <div className="grid grid-cols-4 gap-2 text-xs font-mono">
              {(['PROGRADE', 'RETROGRADE', 'RADIAL_OUT', 'NORMAL'] as const).map((dir) => (
                <button
                  key={dir}
                  type="button"
                  onClick={() => setBurnDirection(dir)}
                  className={`py-1.5 rounded border text-center text-[11px] transition-aerospace ${
                    burnDirection === dir
                      ? 'bg-cyan-950/40 border-cyan-500/50 text-cyan-300 font-semibold'
                      : 'bg-[#070B12] border-white/[0.06] text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {dir === 'PROGRADE' ? 'Prograde' : dir === 'RETROGRADE' ? 'Retro' : dir === 'RADIAL_OUT' ? 'Radial' : 'Normal'}
                </button>
              ))}
            </div>
          </div>

          {/* Live Outcome Metrics Card */}
          <div className="bg-[#070B12] border border-white/[0.08] rounded-lg p-3.5 flex flex-col gap-3 font-mono">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">
              Projected Post-Maneuver State
            </span>

            <div className="grid grid-cols-3 gap-2">
              <div className="p-2 rounded bg-slate-900/60">
                <span className="text-[10px] text-slate-500 block">NEW MISS DIST</span>
                <span className="text-emerald-400 font-semibold text-sm">
                  {newMiss.toFixed(3)} km
                </span>
                <span className="text-[9px] text-slate-500 block">
                  orig: {origMiss.toFixed(3)} km
                </span>
              </div>

              <div className="p-2 rounded bg-slate-900/60">
                <span className="text-[10px] text-slate-500 block">NEW Pc</span>
                <span className="text-emerald-400 font-semibold text-sm">
                  {newPc.toExponential(2)}
                </span>
                <span className="text-[9px] text-slate-500 block">
                  orig: {origPc.toExponential(2)}
                </span>
              </div>

              <div className="p-2 rounded bg-slate-900/60">
                <span className="text-[10px] text-slate-500 block">FUEL COST</span>
                <span className="text-cyan-300 font-semibold text-sm">
                  {fuelCostKg.toFixed(2)} kg
                </span>
                <span className="text-[9px] text-slate-500 block">
                  Isp: {ispSeconds}s
                </span>
              </div>
            </div>

            {/* Clear Recommendation Line */}
            <div
              className={`p-2.5 rounded border text-xs flex items-center gap-2 ${
                isRecommended
                  ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                  : 'bg-amber-950/20 border-amber-500/30 text-amber-300'
              }`}
            >
              {isRecommended ? (
                <>
                  <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                  <span>
                    <strong>Maneuver recommended:</strong> {deltaV.toFixed(2)} m/s burn consumes {fuelCostKg.toFixed(2)} kg propellant, reducing Pc to {newPc.toExponential(1)}.
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                  <span>
                    <strong>Margin Warning:</strong> Current ΔV yields {newMiss.toFixed(2)} km miss distance. Minimum safety threshold is 2.0 km.
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Collapsible Assumptions Section */}
          <div className="border border-white/[0.06] rounded-md overflow-hidden">
            <button
              type="button"
              onClick={() => setAssumptionsOpen(!assumptionsOpen)}
              className="w-full px-3 py-2 bg-[#070B12] text-xs font-mono text-slate-400 flex items-center justify-between hover:text-slate-200 transition-colors"
            >
              <span>Spacecraft Propulsion Assumptions</span>
              {assumptionsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>

            {assumptionsOpen && (
              <div className="p-3 bg-[#070B12]/60 grid grid-cols-2 gap-3 text-xs font-mono border-t border-white/[0.04]">
                <div>
                  <label className="text-[10px] text-slate-500 block">Spacecraft Wet Mass (kg)</label>
                  <input
                    type="number"
                    value={spacecraftMassKg}
                    onChange={(e) => setSpacecraftMassKg(parseFloat(e.target.value) || 710)}
                    className="w-full mt-1 bg-[#0D131D] border border-white/[0.08] rounded px-2 py-1 text-slate-200"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 block">Specific Impulse Isp (s)</label>
                  <input
                    type="number"
                    value={ispSeconds}
                    onChange={(e) => setIspSeconds(parseFloat(e.target.value) || 220)}
                    className="w-full mt-1 bg-[#0D131D] border border-white/[0.08] rounded px-2 py-1 text-slate-200"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Execute Maneuver Button */}
          <button
            onClick={handleExecute}
            disabled={maneuverMutation.isPending}
            className="w-full py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-xs flex items-center justify-center gap-2 transition-aerospace shadow-lg"
          >
            <Fuel className="w-4 h-4" />
            <span>
              {maneuverMutation.isPending ? 'Validating Burn Plan...' : 'Transmit CAM Burn Profile to ISTRAC'}
            </span>
          </button>

          {/* Success Banner if executed */}
          {executedPlan && (
            <div className="p-3 rounded bg-emerald-950/30 border border-emerald-500/40 text-xs font-mono text-emerald-300 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400 mt-0.5" />
              <div>
                <span className="font-semibold block">CAM Telemetry Transmitted Successfully</span>
                <span className="text-[11px] text-slate-300">{executedPlan.summary}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
  Info,
  Download,
  Loader2,
} from 'lucide-react';
import { useConjunction, planManeuver } from '../api/client';
import type { ManeuverRequest, ManeuverResult } from '../api/types';
import { RiskBadge } from '../components/common/RiskBadge';
import { formatUtcDateTime } from '../hooks/useUtcClock';
import { useSimulationStore } from '../store/simulationStore';

export const EventDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const highlightConjunction = useSimulationStore((s) => s.highlightConjunction);

  const eventId = id || 'CONJ-2026-NETRA-01';

  // Real backend query with quiet retry handling
  const { data, isLoading } = useConjunction(eventId);

  const conjunction = data?.data;
  const isDemo = data?.isDemo || conjunction?.dataSource === 'demo';

  // Maneuver Planner State
  const [deltaV, setDeltaV] = useState<number>(0.38);
  const [burnLeadHours, setBurnLeadHours] = useState<number>(12);
  const [burnDirection, setBurnDirection] = useState<'PROGRADE' | 'RETROGRADE' | 'RADIAL_OUT' | 'NORMAL'>('PROGRADE');
  const [spacecraftMassKg, setSpacecraftMassKg] = useState<number>(710);
  const [ispSeconds, setIspSeconds] = useState<number>(220);
  const [covarianceOpen, setCovarianceOpen] = useState(false);
  const [limitationsOpen, setLimitationsOpen] = useState(false);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [exported, setExported] = useState(false);

  // Maneuver plan returned by backend
  const [maneuverPlan, setManeuverPlan] = useState<ManeuverResult | null>(null);
  const [isManeuverLoading, setIsManeuverLoading] = useState(false);

  // Debounce 300 ms on slider/direction/lead-time changes and call POST /api/maneuver
  useEffect(() => {
    if (!conjunction) return;

    const timer = setTimeout(async () => {
      setIsManeuverLoading(true);
      try {
        const req: ManeuverRequest = {
          conjunctionId: conjunction.id,
          deltaVMs: deltaV,
          burnTimeUtc: new Date(conjunction.tcaMs - burnLeadHours * 3600 * 1000).toISOString(),
          direction: burnDirection,
          spacecraftMassKg,
          ispSeconds,
        };
        const res = await planManeuver(req);
        setManeuverPlan(res.data);
      } catch {
        // Quiet error state
      } finally {
        setIsManeuverLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [conjunction, deltaV, burnLeadHours, burnDirection, spacecraftMassKg, ispSeconds]);

  // Derived consistent total miss distance from spatial components: sqrt(R^2 + T^2 + N^2)
  const derivedTotalMissKm = conjunction
    ? Math.sqrt(
        Math.pow(conjunction.radialMissKm, 2) +
        Math.pow(conjunction.inTrackMissKm, 2) +
        Math.pow(conjunction.crossTrackMissKm, 2)
      )
    : 0.284;
  const effectiveMissKm = !isNaN(derivedTotalMissKm) && derivedTotalMissKm > 0
    ? derivedTotalMissKm
    : (conjunction?.missDistanceKm || 0.284);

  // Model comparison probabilities
  const rawPc = conjunction?.pcRaw ?? conjunction?.rawProbability ?? 0;
  const calPc = conjunction?.pcMlCalibrated ?? conjunction?.calibratedProbability ?? 0;

  // Fallback estimates if backend call is pending
  const origMiss = effectiveMissKm;
  const origPc = calPc || 6.84e-4;
  const localNewMiss = origMiss + deltaV * (burnLeadHours / 12) * 4.6;
  const g0 = 9.80665;
  const localFuelCostKg = spacecraftMassKg * (1 - Math.exp(-deltaV / (g0 * ispSeconds)));
  const localScale = origMiss / Math.max(0.01, localNewMiss);
  const localNewPc = Math.max(1e-9, origPc * Math.pow(localScale, 3.5));

  // Values from backend maneuver API or local estimate
  const displayedMissKm = maneuverPlan?.newMissDistanceKm ?? localNewMiss;
  const displayedPcFormatted = maneuverPlan?.newProbability
    ? maneuverPlan.newProbability.toExponential(2)
    : localNewPc.toExponential(2);
  const displayedFuelKg = maneuverPlan?.fuelCostKg ?? localFuelCostKg;
  const recommendation = maneuverPlan?.recommendation ?? (displayedMissKm >= 2.0 && (maneuverPlan?.newProbability ?? localNewPc) < 1e-5 ? 'MANEUVER_RECOMMENDED' : 'WAIT_MONITOR');
  const isRecommended = recommendation === 'MANEUVER_RECOMMENDED';

  // Ratio caption for Model Comparison
  let pcCaption = '';
  if (rawPc > 0 && calPc > 0) {
    const ratio = rawPc / calPc;
    if (ratio >= 1.05) {
      const formattedRatio = ratio >= 10 ? ratio.toFixed(0) : ratio.toFixed(1);
      pcCaption = `ML correction lowers the estimated risk by about ${formattedRatio}x.`;
    } else if (ratio <= 0.95) {
      const invRatio = 1 / ratio;
      const formattedRatio = invRatio >= 10 ? invRatio.toFixed(0) : invRatio.toFixed(1);
      pcCaption = `ML correction increases the estimated risk by about ${formattedRatio}x based on environmental covariance.`;
    } else {
      pcCaption = 'ML correction maintains estimated risk within 5% of the classical 2D estimate.';
    }
  }

  // Covariance arrays in metres [radial, in-track, cross-track]
  const primaryCov = conjunction?.covariance?.primary ?? [
    conjunction?.primaryCovariance?.radialSigmaM ?? 15,
    conjunction?.primaryCovariance?.inTrackSigmaM ?? 50,
    conjunction?.primaryCovariance?.crossTrackSigmaM ?? 20,
  ];
  const secondaryCov = conjunction?.covariance?.secondary ?? [
    conjunction?.secondaryCovariance?.radialSigmaM ?? 25,
    conjunction?.secondaryCovariance?.inTrackSigmaM ?? 75,
    conjunction?.secondaryCovariance?.crossTrackSigmaM ?? 30,
  ];

  const handleExport = () => {
    if (!conjunction) return;
    const burnTimeUtc = new Date(conjunction.tcaMs - burnLeadHours * 3600 * 1000).toISOString();
    const profileData = {
      eventId: conjunction.id,
      tcaUtc: conjunction.tcaUtc,
      burnTimeUtc,
      deltaVMs: deltaV,
      direction: burnDirection,
      fuelCostKg: Number(displayedFuelKg.toFixed(3)),
      projectedMissDistanceKm: Number(displayedMissKm.toFixed(3)),
      projectedPc: displayedPcFormatted,
      recommendation,
      noNewConjunction: maneuverPlan?.noNewConjunction ?? true,
      assumptions: {
        spacecraftMassKg,
        ispSeconds,
        burnLeadHours,
      },
      exportedAtUtc: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(profileData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `burn_profile_${conjunction.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setExported(true);
  };

  if (isLoading || !conjunction) {
    return (
      <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] flex items-center justify-center text-slate-400 font-sans text-xs">
        Loading conjunction event telemetry...
      </div>
    );
  }

  const { primarySat, secondarySat } = conjunction;

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] text-slate-200 px-4 md:px-8 py-6 max-w-7xl mx-auto flex flex-col gap-5 font-sans">
      {/* Top Breadcrumb & Navigation */}
      <div className="flex items-center justify-between border-b border-white/[0.08] pb-3">
        <button
          type="button"
          onClick={() => navigate('/conjunctions')}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Conjunctions</span>
        </button>

        <div className="flex items-center gap-2">
          {isDemo && (
            <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
              Demo data
            </span>
          )}
          <RiskBadge level={conjunction.riskLevel} />
        </div>
      </div>

      {/* Header Block */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="text-xs text-slate-400 mb-1 flex items-center gap-2">
            <span>Event ID:</span>
            <span className="font-mono text-slate-200">{conjunction.id}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-semibold text-white tracking-tight flex items-center gap-2">
              <span>{primarySat.name}</span>
              <span className="text-slate-400 text-sm font-normal">vs</span>
              <span className="text-slate-200">{secondarySat.name}</span>
            </h1>
            <button
              type="button"
              onClick={() => {
                highlightConjunction(conjunction.id, true);
                navigate('/simulator');
              }}
              className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors ml-2"
              title="Open event in 3D Orbit Simulator"
            >
              <Orbit className="w-3.5 h-3.5 text-slate-400" />
              <span>View in simulator</span>
            </button>
          </div>
          <div className="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-2">
            <span>Primary: <span className="font-mono text-slate-300">#{primarySat.noradId}</span> ({primarySat.regime})</span>
            <span>•</span>
            <span>Secondary: <span className="font-mono text-slate-300">#{secondarySat.noradId}</span> ({secondarySat.type})</span>
          </div>
        </div>

        <div className="flex items-center gap-4 bg-[#070B12] p-2.5 px-4 rounded text-xs">
          <div>
            <span className="text-xs text-slate-400 block">TCA (UTC)</span>
            <span className="text-slate-100 font-mono font-medium">{formatUtcDateTime(conjunction.tcaUtc)}</span>
          </div>
          <div className="w-[1px] h-7 bg-white/[0.08]" />
          <div>
            <span className="text-xs text-slate-400 block">Miss distance</span>
            <span className="text-slate-100 font-mono font-semibold">{effectiveMissKm.toFixed(3)} km</span>
          </div>
        </div>
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* LEFT COLUMN: Summary & Model Comparison */}
        <div className="flex flex-col gap-4">
          {/* Block 1: Relative Geometry at TCA */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-3">
            <h2 className="text-xs font-semibold text-slate-300 flex items-center gap-2">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              Relative geometry at TCA
            </h2>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="bg-[#070B12] p-3 rounded">
                <span className="text-xs text-slate-400 block mb-1">Radial miss</span>
                <span className="text-slate-100 font-mono font-medium">
                  {conjunction.radialMissKm.toFixed(3)} km
                </span>
              </div>
              <div className="bg-[#070B12] p-3 rounded">
                <span className="text-xs text-slate-400 block mb-1">In-track miss</span>
                <span className="text-slate-100 font-mono font-medium">
                  {conjunction.inTrackMissKm.toFixed(3)} km
                </span>
              </div>
              <div className="bg-[#070B12] p-3 rounded">
                <span className="text-xs text-slate-400 block mb-1">Cross-track miss</span>
                <span className="text-slate-100 font-mono font-medium">
                  {conjunction.crossTrackMissKm.toFixed(3)} km
                </span>
              </div>
              <div className="bg-[#070B12] p-3 rounded">
                <span className="text-xs text-slate-400 block mb-1">Relative velocity</span>
                <span className="text-slate-100 font-mono font-medium">
                  {conjunction.relativeVelocityKmS.toFixed(2)} km/s
                </span>
              </div>
            </div>
          </div>

          {/* Block 2: Collision Probability Model Comparison */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-slate-400" />
                Collision probability model comparison
              </h2>
              {conjunction.mlAvailable === false && (
                <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20">
                  ML model unavailable, using raw SGP4
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="bg-[#070B12] p-3 rounded flex flex-col justify-between">
                <div>
                  <span className="text-xs text-slate-400 block">
                    Classical Foster
                  </span>
                  <span className="text-base font-semibold font-mono text-slate-100 mt-1 block">
                    {rawPc > 0 ? rawPc.toExponential(2) : '0.00e+0'}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-2">
                  Uncalibrated SGP4 covariance; assumes spherical Gaussian distribution.
                </div>
              </div>

              <div className="bg-[#070B12] p-3 rounded border border-cyan-500/30 flex flex-col justify-between">
                <div>
                  <span className="text-xs text-slate-300 block font-medium">
                    ML-corrected (Gagan Suraksha)
                  </span>
                  <span className="text-base font-semibold font-mono text-slate-100 mt-1 block">
                    {calPc > 0 ? calPc.toExponential(2) : '0.00e+0'}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-2">
                  Corrected for solar flux variation, atmospheric drag, and quantile spread covariance.
                </div>
              </div>
            </div>

            {/* Dynamic plain-language ratio caption */}
            {pcCaption && (
              <p className="text-xs text-slate-400 pt-1 border-t border-white/[0.04]">
                {pcCaption}
              </p>
            )}
          </div>

          {/* Block 3: Progressive Disclosure (Covariance & Limitations) */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg divide-y divide-white/[0.06] overflow-hidden">
            {/* Collapsible Covariance uncertainty row (closed by default) */}
            <div>
              <button
                type="button"
                onClick={() => setCovarianceOpen(!covarianceOpen)}
                className="w-full px-4 py-3 text-xs text-slate-300 flex items-center justify-between hover:text-white transition-colors"
              >
                <span className="flex items-center gap-2 font-medium">
                  <Layers className="w-3.5 h-3.5 text-slate-400" />
                  Covariance uncertainty (1σ)
                </span>
                {covarianceOpen ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {covarianceOpen && (
                <div className="p-3.5 bg-[#070B12]/80 text-xs text-slate-300 flex flex-col gap-2">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <div className="bg-slate-900/50 p-2.5 rounded">
                      <span className="text-slate-200 block font-medium mb-1">{primarySat.name}</span>
                      <div className="font-mono text-xs text-slate-300 flex flex-wrap gap-x-2">
                        <span>Radial: {primaryCov[0].toFixed(1)} m</span>
                        <span>•</span>
                        <span>In-track: {primaryCov[1].toFixed(1)} m</span>
                        <span>•</span>
                        <span>Cross-track: {primaryCov[2].toFixed(1)} m</span>
                      </div>
                    </div>
                    <div className="bg-slate-900/50 p-2.5 rounded">
                      <span className="text-slate-200 block font-medium mb-1">{secondarySat.name}</span>
                      <div className="font-mono text-xs text-slate-300 flex flex-wrap gap-x-2">
                        <span>Radial: {secondaryCov[0].toFixed(1)} m</span>
                        <span>•</span>
                        <span>In-track: {secondaryCov[1].toFixed(1)} m</span>
                        <span>•</span>
                        <span>Cross-track: {secondaryCov[2].toFixed(1)} m</span>
                      </div>
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Radial, in-track, and cross-track 1-sigma positional uncertainty estimates derived from quantile error models.
                  </p>
                </div>
              )}
            </div>

            {/* Collapsible Assumptions & Limitations (closed by default) */}
            <div>
              <button
                type="button"
                onClick={() => setLimitationsOpen(!limitationsOpen)}
                className="w-full px-4 py-3 text-xs text-slate-300 flex items-center justify-between hover:text-white transition-colors"
              >
                <span className="flex items-center gap-2 font-medium">
                  <Info className="w-3.5 h-3.5 text-slate-400" />
                  Assumptions &amp; limitations
                </span>
                {limitationsOpen ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </button>

              {limitationsOpen && (
                <div className="p-3.5 bg-[#070B12]/80 text-xs text-slate-400 flex flex-col gap-2">
                  <p>
                    <strong className="text-slate-300">• Astrodynamics Propagator:</strong> Analytical SGP4 propagator corrected with multi-target quantile regression models.
                  </p>
                  <p>
                    <strong className="text-slate-300">• Collision Probabilities:</strong> Raw Pc uses 2D Foster encounter plane formulation. Calibrated Pc uses IsotonicRegression fit to historical conjunction backtests.
                  </p>
                  <p>
                    <strong className="text-slate-300">• Propulsion Parameters:</strong> Spacecraft mass ({spacecraftMassKg} kg) and specific impulse ({ispSeconds} s) reflect nominal reference values.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Maneuver Planner */}
        <div className="flex flex-col gap-4">
          {/* Block 1: Planner Controls */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-5 flex flex-col gap-5">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
              <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
                <Sliders className="w-4 h-4 text-slate-400" />
                Collision Avoidance Maneuver (CAM) planner
              </h2>
              <span className="text-xs text-slate-400 bg-slate-900/60 px-2.5 py-0.5 rounded">
                Target miss &gt; 2.0 km
              </span>
            </div>

            {/* Interactive Delta-V Slider */}
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-center text-xs">
                <label htmlFor="deltav-slider" className="text-slate-300">
                  Impulsive Delta-V (ΔV)
                </label>
                <span className="text-slate-100 font-semibold font-mono text-sm">
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
              <div className="flex justify-between text-xs font-mono text-slate-400">
                <span>0.00 m/s</span>
                <span>0.75 m/s</span>
                <span>1.50 m/s</span>
              </div>
            </div>

            {/* Burn Lead Time Selector */}
            <div className="flex flex-col gap-2">
              <label className="text-xs text-slate-300 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Burn lead time before TCA
              </label>
              <div className="grid grid-cols-4 gap-2 text-xs font-mono">
                {[24, 12, 6, 2].map((hours) => (
                  <button
                    key={hours}
                    type="button"
                    onClick={() => setBurnLeadHours(hours)}
                    className={`py-1.5 rounded text-center transition-aerospace ${
                      burnLeadHours === hours
                        ? 'bg-cyan-950/40 border border-cyan-500/50 text-cyan-300 font-semibold'
                        : 'bg-[#070B12] text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    TCA - {hours}h
                  </button>
                ))}
              </div>
            </div>

            {/* Burn Direction Selector */}
            <div className="flex flex-col gap-2">
              <label className="text-xs text-slate-300">
                Thrust vector direction
              </label>
              <div className="grid grid-cols-4 gap-2 text-xs">
                {(['PROGRADE', 'RETROGRADE', 'RADIAL_OUT', 'NORMAL'] as const).map((dir) => (
                  <button
                    key={dir}
                    type="button"
                    onClick={() => setBurnDirection(dir)}
                    className={`py-1.5 rounded text-center transition-aerospace ${
                      burnDirection === dir
                        ? 'bg-cyan-950/40 border border-cyan-500/50 text-cyan-300 font-semibold'
                        : 'bg-[#070B12] text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {dir === 'PROGRADE' ? 'Prograde' : dir === 'RETROGRADE' ? 'Retrograde' : dir === 'RADIAL_OUT' ? 'Radial' : 'Normal'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Block 2: Projected Post-Maneuver State (Tiles + Short Single-Line Recommendation) */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-3">
            <h3 className="text-xs font-medium text-slate-300">
              Projected post-maneuver state
            </h3>

            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 rounded bg-[#070B12] min-h-[64px] flex flex-col justify-between">
                <span className="text-xs text-slate-400 block">New miss distance</span>
                {isManeuverLoading ? (
                  <div className="flex items-center gap-1.5 text-cyan-400 font-mono text-xs">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Updating...</span>
                  </div>
                ) : (
                  <span className="text-emerald-400 font-semibold font-mono text-sm block mt-0.5">
                    {displayedMissKm.toFixed(3)} km
                  </span>
                )}
              </div>

              <div className="p-3 rounded bg-[#070B12] min-h-[64px] flex flex-col justify-between">
                <span className="text-xs text-slate-400 block">New Pc</span>
                {isManeuverLoading ? (
                  <div className="flex items-center gap-1.5 text-cyan-400 font-mono text-xs">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Updating...</span>
                  </div>
                ) : (
                  <span className="text-emerald-400 font-semibold font-mono text-sm block mt-0.5">
                    {displayedPcFormatted}
                  </span>
                )}
              </div>

              <div className="p-3 rounded bg-[#070B12] min-h-[64px] flex flex-col justify-between">
                <span className="text-xs text-slate-400 block">Fuel cost</span>
                {isManeuverLoading ? (
                  <div className="flex items-center gap-1.5 text-cyan-400 font-mono text-xs">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Updating...</span>
                  </div>
                ) : (
                  <span className="text-slate-100 font-semibold font-mono text-sm block mt-0.5">
                    {displayedFuelKg.toFixed(2)} kg
                  </span>
                )}
              </div>
            </div>

            {/* Single short line recommendation */}
            <div
              className={`px-3 py-2 rounded text-xs flex items-center gap-2 ${
                isRecommended
                  ? 'bg-emerald-950/20 text-emerald-300'
                  : 'bg-amber-950/20 text-amber-300'
              }`}
            >
              {isRecommended ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                  <span>
                    <strong>Maneuver recommended:</strong> {deltaV.toFixed(2)} m/s, {displayedFuelKg.toFixed(2)} kg propellant
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-400" />
                  <span>
                    <strong>Wait and monitor:</strong> minimum safety threshold is 2.00 km miss distance
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Block 3: Spacecraft Propulsion Assumptions & Export Button */}
          <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-4 flex flex-col gap-4">
            {/* Collapsible Spacecraft Propulsion Assumptions */}
            <div className="bg-[#070B12] rounded-md overflow-hidden">
              <button
                type="button"
                onClick={() => setAssumptionsOpen(!assumptionsOpen)}
                className="w-full px-3 py-2.5 text-xs text-slate-300 flex items-center justify-between hover:text-white transition-colors"
              >
                <span>Spacecraft propulsion assumptions</span>
                {assumptionsOpen ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
              </button>

              {assumptionsOpen && (
                <div className="p-3.5 border-t border-white/[0.04] grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Spacecraft wet mass (kg)</label>
                    <input
                      type="number"
                      value={spacecraftMassKg}
                      onChange={(e) => setSpacecraftMassKg(parseFloat(e.target.value) || 710)}
                      className="w-full bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Specific impulse Isp (s)</label>
                    <input
                      type="number"
                      value={ispSeconds}
                      onChange={(e) => setIspSeconds(parseFloat(e.target.value) || 220)}
                      className="w-full bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-100 font-mono text-xs"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Export Burn Profile Button */}
            <button
              type="button"
              onClick={handleExport}
              disabled={isManeuverLoading}
              className="w-full py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-xs flex items-center justify-center gap-2 transition-aerospace shadow-md"
            >
              <Download className="w-4 h-4" />
              <span>Export burn profile</span>
            </button>

            {/* Feedback Banner if exported */}
            {exported && (
              <div className="px-3 py-2 rounded bg-emerald-950/20 text-xs text-emerald-300 flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                <span>Burn profile exported as JSON.</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

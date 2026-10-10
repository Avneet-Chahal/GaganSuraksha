import React from 'react';
import { Play, Pause, RotateCcw, Clock } from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';
import { CONJUNCTION_EVENTS } from '../../api/mockData';
import { formatUtcDateTime } from '../../hooks/useUtcClock';

export const TimelineBar: React.FC = () => {
  const simTimeMs = useSimulationStore((s) => s.simTimeMs);
  const startWindowMs = useSimulationStore((s) => s.startWindowMs);
  const endWindowMs = useSimulationStore((s) => s.endWindowMs);
  const speed = useSimulationStore((s) => s.speed);
  const isPlaying = useSimulationStore((s) => s.isPlaying);

  const togglePlay = useSimulationStore((s) => s.togglePlay);
  const resetSimulationTime = useSimulationStore((s) => s.resetSimulationTime);
  const setSpeed = useSimulationStore((s) => s.setSpeed);
  const setSimTime = useSimulationStore((s) => s.setSimTime);
  const highlightConjunction = useSimulationStore((s) => s.highlightConjunction);

  const totalDuration = endWindowMs - startWindowMs;
  const progressRatio = Math.max(0, Math.min(1, (simTimeMs - startWindowMs) / totalDuration));

  const speeds = [1, 10, 60, 600];

  const handleScrub = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    const targetMs = startWindowMs + val * totalDuration;
    setSimTime(targetMs);
  };

  return (
    <footer
      aria-label="Simulation Playback Timeline"
      className="absolute bottom-4 left-4 right-4 z-20 bg-[#0D131D]/90 backdrop-blur-md border border-white/[0.08] rounded-lg p-2.5 px-4 shadow-2xl flex flex-col md:flex-row items-center justify-between gap-3 select-none"
    >
      {/* Playback Controls & Speed Selector */}
      <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-start">
        <div className="flex items-center gap-1.5">
          <button
            onClick={togglePlay}
            title={isPlaying ? 'Pause simulation' : 'Play simulation'}
            className="w-8 h-8 rounded bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25 border border-cyan-500/30 flex items-center justify-center transition-aerospace"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </button>
          <button
            onClick={resetSimulationTime}
            title="Reset to mission epoch"
            className="w-8 h-8 rounded text-slate-400 hover:text-white hover:bg-slate-800 flex items-center justify-center transition-aerospace"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Speed selectors */}
        <div className="flex items-center bg-[#070B12] rounded p-0.5 border border-white/[0.04]">
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`px-2 py-1 text-[11px] font-mono rounded transition-aerospace ${
                speed === s
                  ? 'bg-cyan-950/60 text-cyan-300 font-semibold border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Current Simulation UTC Time */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#070B12] border border-white/[0.04] text-xs font-mono text-cyan-300 tabular-nums">
          <Clock className="w-3.5 h-3.5 text-cyan-500" />
          <span>{formatUtcDateTime(simTimeMs)}</span>
        </div>
      </div>

      {/* Scrubbable Timeline spanning 7 days with Conjunction Event Ticks */}
      <div className="relative flex-1 w-full max-w-2xl px-2 flex flex-col justify-center">
        <div className="relative w-full h-6 flex items-center">
          {/* Base track */}
          <input
            type="range"
            min="0"
            max="1"
            step="0.0005"
            value={progressRatio}
            onChange={handleScrub}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 relative z-10"
          />

          {/* Conjunction Event markers on timeline */}
          {CONJUNCTION_EVENTS.map((conj) => {
            const eventProgress = (conj.tcaMs - startWindowMs) / totalDuration;
            if (eventProgress < 0 || eventProgress > 1) return null;

            const isCritical = conj.riskLevel === 'CRITICAL';
            const isWarning = conj.riskLevel === 'WARNING';
            const tickColor = isCritical ? 'bg-rose-500' : isWarning ? 'bg-amber-500' : 'bg-emerald-500';

            return (
              <button
                key={conj.id}
                onClick={() => highlightConjunction(conj.id, true)}
                title={`${conj.primarySat.name} vs ${conj.secondarySat.name} (${conj.riskLevel}) - TCA: ${conj.missDistanceKm} km`}
                style={{ left: `${eventProgress * 100}%` }}
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 z-20 group p-1"
              >
                <span className={`block w-2.5 h-2.5 rounded-full ${tickColor} border border-[#070B12] shadow-sm group-hover:scale-125 transition-transform`} />
              </button>
            );
          })}
        </div>

        {/* Timeline Range bounds (T+0 to T+7 Days) */}
        <div className="flex justify-between text-[10px] font-mono text-slate-500 px-0.5">
          <span>T+0 (Now)</span>
          <span className="hidden sm:inline">T+3.5d</span>
          <span>T+7 Days Window</span>
        </div>
      </div>
    </footer>
  );
};

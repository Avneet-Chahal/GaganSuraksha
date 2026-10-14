import React, { useState } from 'react';
import { SceneCanvas } from './SceneCanvas';
import { SimulationToolbar } from './SimulationToolbar';
import { SelectedObjectPanel } from './SelectedObjectPanel';
import { TimelineBar } from './TimelineBar';
import { SlidersHorizontal } from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';

export const SimulatorView: React.FC = () => {
  const isDemoMode = useSimulationStore((s) => s.isDemoMode);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);

  return (
    <main className="relative w-full h-[calc(100vh-3rem)] overflow-hidden bg-[#070B12]">
      {/* 3D Scene canvas dominates the screen */}
      <SceneCanvas />

      {/* Desktop Toolbar (Left) */}
      <div className="hidden sm:block">
        <SimulationToolbar />
      </div>

      {/* Mobile Toolbar Toggle Button */}
      <div className="sm:hidden absolute top-3 left-3 z-20">
        <button
          onClick={() => setMobileToolsOpen(!mobileToolsOpen)}
          className="p-2 rounded-lg bg-[#0D131D]/90 border border-white/[0.08] text-slate-300 shadow-lg"
          title="Toggle Simulation Tools"
        >
          <SlidersHorizontal className="w-4 h-4" />
        </button>
      </div>

      {/* Mobile Sheet Toolbar */}
      {mobileToolsOpen && (
        <div className="sm:hidden absolute top-12 left-3 z-30">
          <SimulationToolbar />
        </div>
      )}

      {/* Right Collapsible Telemetry Panel */}
      <SelectedObjectPanel />

      {/* Bottom Timeline & Controls */}
      <TimelineBar />

      {/* Small Demo Badge in bottom-left if in demo mode */}
      {isDemoMode && (
        <div className="hidden md:flex absolute bottom-18 left-4 z-10 items-center gap-1.5 px-2.5 py-1 rounded bg-[#0D131D]/90 border border-amber-500/20 text-[11px] font-mono text-amber-300">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span className="font-semibold">Demo data</span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400">SGP4 Propagator</span>
        </div>
      )}
    </main>
  );
};

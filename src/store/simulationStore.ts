import { create } from 'zustand';
import { CONJUNCTION_EVENTS } from '../api/mockData';

// 7-day prediction window
const INITIAL_NOW_MS = new Date('2026-10-10T12:00:00.000Z').getTime();
const SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000;

export type OrbitDisplayMode = 'WATCHLIST' | 'ALL' | 'NONE';
export type RegimeFilter = 'ALL' | 'LEO' | 'MEO' | 'GEO';

interface SimulationState {
  simTimeMs: number;
  startWindowMs: number;
  endWindowMs: number;
  speed: number; // 1, 10, 60, 600
  isPlaying: boolean;

  selectedObjectId: string | null;
  hoveredObjectId: string | null;
  focusedObjectId: string | null;
  highlightedConjunctionId: string | null;

  showOrbits: OrbitDisplayMode;
  showDebris: boolean;
  showSatellites: boolean;
  orbitRegimeFilter: RegimeFilter;
  useMlCorrectedOrbits: boolean;
  isDemoMode: boolean;
  rightPanelOpen: boolean;

  // Actions
  setSimTime: (timeMs: number) => void;
  advanceSimTime: (deltaSeconds: number) => void;
  setSpeed: (speed: number) => void;
  setIsPlaying: (isPlaying: boolean) => void;
  togglePlay: () => void;
  resetSimulationTime: () => void;

  selectObject: (id: string | null) => void;
  setHoveredObject: (id: string | null) => void;
  focusObject: (id: string | null) => void;
  highlightConjunction: (conjunctionId: string | null, jumpToTca?: boolean) => void;

  toggleOrbits: () => void;
  toggleDebris: () => void;
  toggleSatellites: () => void;
  setRegimeFilter: (filter: RegimeFilter) => void;
  toggleMlCorrectedOrbits: () => void;
  setUseMlCorrectedOrbits: (val: boolean) => void;
  setIsDemoMode: (isDemo: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  simTimeMs: INITIAL_NOW_MS,
  startWindowMs: INITIAL_NOW_MS,
  endWindowMs: INITIAL_NOW_MS + SEVEN_DAYS_MS,
  speed: 10,
  isPlaying: true,

  selectedObjectId: '43111', // CARTOSAT-2F initially selected to show data immediately
  hoveredObjectId: null,
  focusedObjectId: null,
  highlightedConjunctionId: 'CONJ-2026-NETRA-01', // highlight critical close approach

  showOrbits: 'WATCHLIST',
  showDebris: true,
  showSatellites: true,
  orbitRegimeFilter: 'ALL',
  useMlCorrectedOrbits: false,
  isDemoMode: true,
  rightPanelOpen: true,

  setSimTime: (timeMs) => {
    const { startWindowMs, endWindowMs } = get();
    const clamped = Math.max(startWindowMs, Math.min(endWindowMs, timeMs));
    set({ simTimeMs: clamped });
  },

  advanceSimTime: (deltaSeconds) => {
    const { simTimeMs, speed, isPlaying, startWindowMs, endWindowMs } = get();
    if (!isPlaying) return;
    const nextTime = simTimeMs + deltaSeconds * speed * 1000;
    if (nextTime > endWindowMs) {
      set({ simTimeMs: startWindowMs }); // loop smoothly
    } else {
      set({ simTimeMs: nextTime });
    }
  },

  setSpeed: (speed) => set({ speed }),

  setIsPlaying: (isPlaying) => set({ isPlaying }),

  togglePlay: () => set((state) => ({ isPlaying: !state.isPlaying })),

  resetSimulationTime: () =>
    set({
      simTimeMs: INITIAL_NOW_MS,
      isPlaying: false,
    }),

  selectObject: (id) =>
    set({
      selectedObjectId: id,
      rightPanelOpen: id !== null,
    }),

  setHoveredObject: (id) => set({ hoveredObjectId: id }),

  focusObject: (id) => set({ focusedObjectId: id }),

  highlightConjunction: (conjunctionId, jumpToTca = true) => {
    if (!conjunctionId) {
      set({ highlightedConjunctionId: null });
      return;
    }
    const conj = CONJUNCTION_EVENTS.find((c) => c.id === conjunctionId);
    if (conj) {
      const updates: Partial<SimulationState> = {
        highlightedConjunctionId: conjunctionId,
        selectedObjectId: conj.primarySat.id,
        rightPanelOpen: true,
      };
      if (jumpToTca) {
        // Jump timeline to TCA minus 10 minutes for optimal inspection
        updates.simTimeMs = Math.max(get().startWindowMs, conj.tcaMs - 10 * 60 * 1000);
      }
      set(updates);
    }
  },

  toggleOrbits: () =>
    set((state) => {
      const nextMode: OrbitDisplayMode =
        state.showOrbits === 'WATCHLIST'
          ? 'ALL'
          : state.showOrbits === 'ALL'
          ? 'NONE'
          : 'WATCHLIST';
      return { showOrbits: nextMode };
    }),

  toggleDebris: () => set((state) => ({ showDebris: !state.showDebris })),

  toggleSatellites: () => set((state) => ({ showSatellites: !state.showSatellites })),

  setRegimeFilter: (filter) => set({ orbitRegimeFilter: filter }),

  toggleMlCorrectedOrbits: () =>
    set((state) => ({ useMlCorrectedOrbits: !state.useMlCorrectedOrbits })),

  setUseMlCorrectedOrbits: (val) => set({ useMlCorrectedOrbits: val }),

  setIsDemoMode: (isDemo) => set({ isDemoMode: isDemo }),

  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
}));

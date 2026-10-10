import { create } from 'zustand';
import type { WatchlistSatelliteSetting, AlertThresholdSettings } from '../api/types';
import { INITIAL_WATCHLIST_SETTINGS, INITIAL_ALERT_SETTINGS } from '../api/mockData';

interface WatchlistState {
  watchlist: WatchlistSatelliteSetting[];
  alertSettings: AlertThresholdSettings;

  addSatellite: (noradId: number, name: string, regime: 'LEO' | 'MEO' | 'GEO') => void;
  removeSatellite: (id: string) => void;
  toggleSatelliteActive: (id: string) => void;
  updateCustomThresholds: (id: string, pc?: number, missDistanceKm?: number) => void;

  updateAlertSettings: (settings: Partial<AlertThresholdSettings>) => void;
  resetToDefaults: () => void;
}

export const useWatchlistStore = create<WatchlistState>((set) => ({
  watchlist: INITIAL_WATCHLIST_SETTINGS,
  alertSettings: INITIAL_ALERT_SETTINGS,

  addSatellite: (noradId, name, regime) =>
    set((state) => {
      const exists = state.watchlist.some((s) => s.noradId === noradId);
      if (exists) return state;
      const newItem: WatchlistSatelliteSetting = {
        id: `${noradId}`,
        noradId,
        name: name.toUpperCase(),
        regime,
        customPcThreshold: state.alertSettings.defaultPcThreshold,
        customMissDistanceKm: state.alertSettings.defaultMissDistanceKm,
        addedAt: new Date().toISOString(),
        active: true,
      };
      return { watchlist: [...state.watchlist, newItem] };
    }),

  removeSatellite: (id) =>
    set((state) => ({
      watchlist: state.watchlist.filter((s) => s.id !== id),
    })),

  toggleSatelliteActive: (id) =>
    set((state) => ({
      watchlist: state.watchlist.map((s) =>
        s.id === id ? { ...s, active: !s.active } : s
      ),
    })),

  updateCustomThresholds: (id, pc, missDistanceKm) =>
    set((state) => ({
      watchlist: state.watchlist.map((s) =>
        s.id === id
          ? {
              ...s,
              customPcThreshold: pc ?? s.customPcThreshold,
              customMissDistanceKm: missDistanceKm ?? s.customMissDistanceKm,
            }
          : s
      ),
    })),

  updateAlertSettings: (newSettings) =>
    set((state) => ({
      alertSettings: { ...state.alertSettings, ...newSettings },
    })),

  resetToDefaults: () =>
    set({
      watchlist: INITIAL_WATCHLIST_SETTINGS,
      alertSettings: INITIAL_ALERT_SETTINGS,
    }),
}));

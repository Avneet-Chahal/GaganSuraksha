import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Radio,
  Plus,
  Trash2,
  Bell,
  Database,
  CheckCircle2,
  Send,
  Mail,
  Server,
} from 'lucide-react';
import { useWatchlistStore } from '../store/watchlistStore';
import { fetchDataSources } from '../api/client';
import { formatUtcDateTime } from '../hooks/useUtcClock';

export const WatchlistPage: React.FC = () => {
  const {
    watchlist,
    alertSettings,
    addSatellite,
    removeSatellite,
    toggleSatelliteActive,
    updateAlertSettings,
  } = useWatchlistStore();

  const { data: dataSourcesData } = useQuery({
    queryKey: ['dataSources'],
    queryFn: fetchDataSources,
  });

  const dataSources = dataSourcesData?.data || [];

  // Form states
  const [newNoradId, setNewNoradId] = useState('');
  const [newName, setNewName] = useState('');
  const [newRegime, setNewRegime] = useState<'LEO' | 'MEO' | 'GEO'>('LEO');
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const norad = parseInt(newNoradId.trim(), 10);
    if (!norad || !newName.trim()) return;
    addSatellite(norad, newName.trim(), newRegime);
    setNewNoradId('');
    setNewName('');
  };

  const handleSaveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2500);
  };

  return (
    <div className="min-h-[calc(100vh-3rem)] bg-[#070B12] text-slate-200 px-4 md:px-8 py-6 max-w-7xl mx-auto flex flex-col gap-6">
      {/* Block 1: Page Header */}
      <div className="border-b border-white/[0.08] pb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Radio className="w-4 h-4 text-cyan-400" />
            <h1 className="text-xl font-semibold text-white tracking-tight">
              Asset Watchlist &amp; Alert Configuration
            </h1>
          </div>
          <p className="text-xs text-slate-400 max-w-xl">
            Configure Indian space assets under active collision monitoring, custom screening thresholds, and multi-channel telemetry dispatches.
          </p>
        </div>

        <div className="text-xs font-mono text-slate-400">
          <span>Active Watchlist: </span>
          <strong className="text-cyan-300 font-semibold">
            {watchlist.filter((s) => s.active).length} / {watchlist.length} Assets
          </strong>
        </div>
      </div>

      {/* Block 2: Monitored Indian Assets & Add Satellite */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-5 flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/[0.06] pb-3">
          <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
            <span>Primary Indian Space Assets</span>
          </h2>

          {/* Quick Add Form */}
          <form onSubmit={handleAdd} className="flex items-center gap-2 text-xs font-mono">
            <input
              type="number"
              placeholder="NORAD ID"
              value={newNoradId}
              onChange={(e) => setNewNoradId(e.target.value)}
              className="w-24 bg-[#070B12] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
              required
            />
            <input
              type="text"
              placeholder="Asset Name (e.g. EOS-07)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-44 bg-[#070B12] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
              required
            />
            <select
              value={newRegime}
              onChange={(e) => setNewRegime(e.target.value as 'LEO' | 'MEO' | 'GEO')}
              className="bg-[#070B12] border border-white/[0.08] rounded px-2 py-1 text-slate-300 focus:outline-none"
            >
              <option value="LEO">LEO</option>
              <option value="MEO">MEO</option>
              <option value="GEO">GEO</option>
            </select>
            <button
              type="submit"
              className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-medium flex items-center gap-1 transition-aerospace"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add</span>
            </button>
          </form>
        </div>

        {/* Watchlist Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-mono">
            <thead>
              <tr className="border-b border-white/[0.06] text-slate-400 text-[11px] uppercase tracking-wider">
                <th className="py-2.5 px-3">NORAD ID</th>
                <th className="py-2.5 px-3">Asset Name</th>
                <th className="py-2.5 px-3">Regime</th>
                <th className="py-2.5 px-3">Pc Threshold</th>
                <th className="py-2.5 px-3">Miss Distance Margin</th>
                <th className="py-2.5 px-3 text-center">Monitoring State</th>
                <th className="py-2.5 px-3 text-right">Remove</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {watchlist.map((sat) => (
                <tr key={sat.id} className="hover:bg-slate-800/30 transition-aerospace">
                  <td className="py-2.5 px-3 font-semibold text-cyan-400">#{sat.noradId}</td>
                  <td className="py-2.5 px-3 font-semibold text-slate-200">{sat.name}</td>
                  <td className="py-2.5 px-3 text-slate-400">{sat.regime}</td>
                  <td className="py-2.5 px-3 text-slate-300">
                    {sat.customPcThreshold?.toExponential(0) || '1e-4'}
                  </td>
                  <td className="py-2.5 px-3 text-slate-300">
                    {sat.customMissDistanceKm || 1.0} km
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <button
                      onClick={() => toggleSatelliteActive(sat.id)}
                      className={`px-2 py-0.5 rounded text-[10px] font-medium transition-aerospace ${
                        sat.active
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-slate-800 text-slate-500 border border-slate-700'
                      }`}
                    >
                      {sat.active ? 'ACTIVE' : 'MUTED'}
                    </button>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    <button
                      onClick={() => removeSatellite(sat.id)}
                      title="Remove from watchlist"
                      className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Block 3: Alert Thresholds & Channels Configuration */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-5 flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2 border-b border-white/[0.06] pb-3">
          <Bell className="w-4 h-4 text-cyan-400" />
          Alert Thresholds &amp; Dispatch Channels
        </h2>

        <form onSubmit={handleSaveSettings} className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs font-mono">
          {/* Global Thresholds */}
          <div className="flex flex-col gap-3">
            <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
              Safety Screening Margins
            </span>

            <div className="bg-[#070B12] p-3 rounded border border-white/[0.04] flex flex-col gap-2">
              <label className="text-slate-300 flex justify-between">
                <span>Default Collision Probability (Pc) Threshold</span>
                <span className="text-cyan-400 font-semibold">
                  {alertSettings.defaultPcThreshold.toExponential(0)}
                </span>
              </label>
              <input
                type="text"
                value={alertSettings.defaultPcThreshold}
                onChange={(e) =>
                  updateAlertSettings({ defaultPcThreshold: parseFloat(e.target.value) || 1e-4 })
                }
                className="bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200"
              />
              <span className="text-[10px] text-slate-500">
                Events with calibrated Pc exceeding this trigger mandatory automated Netra CAM analysis.
              </span>
            </div>

            <div className="bg-[#070B12] p-3 rounded border border-white/[0.04] flex flex-col gap-2">
              <label className="text-slate-300 flex justify-between">
                <span>Miss Distance Screening Buffer</span>
                <span className="text-cyan-400 font-semibold">
                  {alertSettings.defaultMissDistanceKm} km
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                value={alertSettings.defaultMissDistanceKm}
                onChange={(e) =>
                  updateAlertSettings({ defaultMissDistanceKm: parseFloat(e.target.value) || 1.0 })
                }
                className="bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200"
              />
              <span className="text-[10px] text-slate-500">
                Close approach events within this spherical radius will be highlighted in the 3D timeline.
              </span>
            </div>
          </div>

          {/* Notification Channels */}
          <div className="flex flex-col gap-3">
            <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
              Telemetry Dispatch Feeds
            </span>

            {/* Email Channel */}
            <div className="bg-[#070B12] p-3 rounded border border-white/[0.04] flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-200 flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  ISTRAC Duty Officer Email
                </span>
                <input
                  type="checkbox"
                  checked={alertSettings.notifyEmail}
                  onChange={(e) => updateAlertSettings({ notifyEmail: e.target.checked })}
                  className="accent-cyan-400"
                />
              </div>
              <input
                type="email"
                value={alertSettings.emailAddress}
                onChange={(e) => updateAlertSettings({ emailAddress: e.target.value })}
                className="bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200 text-xs"
              />
            </div>

            {/* Telegram Channel */}
            <div className="bg-[#070B12] p-3 rounded border border-white/[0.04] flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-200 flex items-center gap-1.5">
                  <Send className="w-3.5 h-3.5 text-slate-400" />
                  NETRA Telegram Alert Bot
                </span>
                <input
                  type="checkbox"
                  checked={alertSettings.notifyTelegram}
                  onChange={(e) => updateAlertSettings({ notifyTelegram: e.target.checked })}
                  className="accent-cyan-400"
                />
              </div>
              <input
                type="text"
                value={alertSettings.telegramChatId}
                onChange={(e) => updateAlertSettings({ telegramChatId: e.target.value })}
                className="bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200 text-xs"
              />
            </div>

            {/* ISTRAC Webhook */}
            <div className="bg-[#070B12] p-3 rounded border border-white/[0.04] flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-200 flex items-center gap-1.5">
                  <Server className="w-3.5 h-3.5 text-slate-400" />
                  ISTRAC Mission Control Webhook
                </span>
                <input
                  type="checkbox"
                  checked={alertSettings.notifyIstracWebhook}
                  onChange={(e) => updateAlertSettings({ notifyIstracWebhook: e.target.checked })}
                  className="accent-cyan-400"
                />
              </div>
              <input
                type="url"
                value={alertSettings.webhookUrl}
                onChange={(e) => updateAlertSettings({ webhookUrl: e.target.value })}
                className="bg-[#0D131D] border border-white/[0.08] rounded px-2.5 py-1 text-slate-200 text-xs"
              />
            </div>
          </div>

          <div className="col-span-1 md:col-span-2 flex items-center justify-between pt-2 border-t border-white/[0.04]">
            {saveSuccess ? (
              <span className="text-emerald-400 flex items-center gap-1 text-xs">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Alert configuration updated and applied to active surveillance pipeline.
              </span>
            ) : (
              <span className="text-slate-500 text-[11px]">
                Settings sync automatically with backend NETRA dispatchers.
              </span>
            )}

            <button
              type="submit"
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded font-medium transition-aerospace"
            >
              Save Configuration
            </button>
          </div>
        </form>
      </div>

      {/* Block 4: Sensor & Surveillance Data Sources */}
      <div className="bg-[#0D131D] border border-white/[0.08] rounded-lg p-5 flex flex-col gap-3 font-mono">
        <div className="flex items-center justify-between border-b border-white/[0.06] pb-3">
          <h2 className="text-sm font-semibold text-white tracking-tight flex items-center gap-2">
            <Database className="w-4 h-4 text-cyan-400" />
            Surveillance Data Sources &amp; Telemetry Freshness
          </h2>
          <span className="text-xs text-slate-400">ISRO NETRA Sensor Ingestion</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/[0.06] text-slate-400 text-[11px] uppercase tracking-wider">
                <th className="py-2.5 px-3">System / Sensor</th>
                <th className="py-2.5 px-3">Origin / Facility</th>
                <th className="py-2.5 px-3">Health Status</th>
                <th className="py-2.5 px-3">Last Ingested (UTC)</th>
                <th className="py-2.5 px-3 text-right">Records</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {dataSources.map((source) => (
                <tr key={source.name} className="hover:bg-slate-800/30 transition-aerospace">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">{source.name}</td>
                  <td className="py-2.5 px-3 text-slate-400">{source.source}</td>
                  <td className="py-2.5 px-3">
                    <span className="inline-flex items-center gap-1.5 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30 text-[10px]">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      {source.status}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-slate-300">
                    {formatUtcDateTime(source.lastUpdatedUtc)}
                  </td>
                  <td className="py-2.5 px-3 text-right text-cyan-300 font-semibold">
                    {source.recordCount.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

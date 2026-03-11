/**
 * VersionCompareView — Side-by-side comparison of two optimization runs.
 *
 * Shows: solver info, objective values, KPI diff, parameter diff.
 * Delta values are color-coded: green=improved, red=degraded, gray=same.
 *
 * Platform-generic: KPI labels come from backend, not hardcoded.
 */

import { ArrowLeftRight, TrendingUp, TrendingDown, Minus, X } from 'lucide-react';
import type { VersionCompare, KpiDiffEntry } from './types';

interface VersionCompareViewProps {
  data: VersionCompare;
  onClose?: () => void;
}

export default function VersionCompareView({ data, onClose }: VersionCompareViewProps) {
  return (
    <div className="h-full flex flex-col bg-slate-900">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between bg-slate-800/80">
        <div className="flex items-center gap-2">
          <ArrowLeftRight size={16} className="text-amber-400" />
          <span className="text-sm font-medium text-slate-200">
            버전 비교
          </span>
          <span className="text-xs text-slate-400">
            Run #{data.a.run_id} vs Run #{data.b.run_id}
          </span>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 hover:bg-slate-700 rounded transition-colors">
            <X size={16} className="text-slate-400" />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Solver & Status comparison */}
        <div className="grid grid-cols-2 gap-3">
          <SummaryCard label="A" summary={data.a} />
          <SummaryCard label="B" summary={data.b} />
        </div>

        {/* Change indicators */}
        <div className="flex gap-2 text-xs">
          {data.solver_changed && (
            <span className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">
              솔버 변경
            </span>
          )}
          {data.model_changed && (
            <span className="px-2 py-1 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
              모델 변경
            </span>
          )}
        </div>

        {/* KPI Comparison Table */}
        {Object.keys(data.kpi_diff).length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">
              KPI 비교
            </h3>
            <div className="rounded-lg border border-slate-700 overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-800">
                    <th className="px-3 py-2 text-left text-slate-400 font-medium">지표</th>
                    <th className="px-3 py-2 text-right text-slate-400 font-medium">A</th>
                    <th className="px-3 py-2 text-right text-slate-400 font-medium">B</th>
                    <th className="px-3 py-2 text-right text-slate-400 font-medium">Delta</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {Object.entries(data.kpi_diff).map(([key, diff]) => (
                    <KpiRow key={key} label={key} diff={diff} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Parameter Differences */}
        {Object.keys(data.param_diff).length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-slate-400 mb-2 uppercase tracking-wider">
              파라미터 변경
            </h3>
            <div className="space-y-1.5">
              {Object.entries(data.param_diff).map(([key, vals]) => (
                <div
                  key={key}
                  className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700"
                >
                  <span className="text-xs text-slate-300 font-mono">{key}</span>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400">{String(vals.a ?? '—')}</span>
                    <span className="text-slate-500">→</span>
                    <span className="text-cyan-300">{String(vals.b ?? '—')}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function SummaryCard({ label, summary }: { label: string; summary: VersionCompare['a'] }) {
  const statusColor =
    summary.status === 'OPTIMAL' ? 'text-emerald-400' :
    summary.status === 'FEASIBLE' ? 'text-blue-400' :
    summary.status === 'INFEASIBLE' ? 'text-red-400' : 'text-slate-400';

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-slate-300">{label}</span>
        <span className={`text-xs font-medium ${statusColor}`}>
          {summary.status}
        </span>
      </div>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-400">솔버</span>
          <span className="text-slate-200">{summary.solver_name || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">목적값</span>
          <span className="text-slate-200 font-mono">
            {summary.objective_value !== null ? summary.objective_value.toLocaleString() : '—'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">변수</span>
          <span className="text-slate-200">{summary.variable_count?.toLocaleString() ?? '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">실행시간</span>
          <span className="text-slate-200">
            {summary.execute_time_sec ? `${summary.execute_time_sec.toFixed(1)}s` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}


function KpiRow({ label, diff }: { label: string; diff: KpiDiffEntry }) {
  const directionIcon =
    diff.direction === 'improved' ? <TrendingUp size={12} className="text-emerald-400" /> :
    diff.direction === 'degraded' ? <TrendingDown size={12} className="text-red-400" /> :
    <Minus size={12} className="text-slate-500" />;

  const deltaColor =
    diff.direction === 'improved' ? 'text-emerald-400' :
    diff.direction === 'degraded' ? 'text-red-400' :
    'text-slate-500';

  const format = (v: any) =>
    typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2)) : String(v ?? '—');

  return (
    <tr className="hover:bg-slate-800/30">
      <td className="px-3 py-2 text-slate-300">{label}</td>
      <td className="px-3 py-2 text-right text-slate-400 font-mono">{format(diff.a)}</td>
      <td className="px-3 py-2 text-right text-slate-200 font-mono">{format(diff.b)}</td>
      <td className="px-3 py-2 text-right">
        <div className="flex items-center justify-end gap-1">
          {directionIcon}
          <span className={`font-mono ${deltaColor}`}>
            {diff.delta !== null ? (diff.delta > 0 ? '+' : '') + format(diff.delta) : '—'}
          </span>
        </div>
      </td>
    </tr>
  );
}

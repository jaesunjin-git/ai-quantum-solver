// src/components/analysis/CompareResultsPanel.tsx
// 솔버 비교 실행 결과 패널
import { Loader2, CheckCircle, XCircle, GitCompare } from 'lucide-react';

interface CompareResultsPanelProps {
  compareResults: Record<number, any>;
  compareRunning: Set<number>;
  solvers: any[];
  onReset: () => void;
}

export function CompareResultsPanel({ compareResults, compareRunning, solvers, onReset }: CompareResultsPanelProps) {
  return (
    <div className="flex-shrink-0 p-4 border-t border-slate-800 max-h-[300px] overflow-y-auto">
      <div className="flex items-center gap-2 mb-3">
        <GitCompare size={14} className="text-cyan-400" />
        <span className="text-[13px] font-bold text-white">비교 결과</span>
      </div>
      <div className="space-y-2">
        {Object.entries(compareResults).map(([idxStr, result]: [string, any]) => {
          const idx = parseInt(idxStr);
          const solver = solvers[idx];
          const isRunning = compareRunning.has(idx);
          return (
            <div key={idx} className={`p-2 rounded-lg border text-[12px] ${
              result?.success ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5'
            }`}>
              <div className="flex justify-between items-center">
                <span className="font-medium text-white">{solver?.solver_name}</span>
                {isRunning ? (
                  <Loader2 size={12} className="text-cyan-400 animate-spin" />
                ) : result?.success ? (
                  <CheckCircle size={12} className="text-green-400" />
                ) : (
                  <XCircle size={12} className="text-red-400" />
                )}
              </div>
              {result?.success && (
                <div className="flex gap-3 mt-1 text-slate-400">
                  <span>목적함수: <span className="text-cyan-400 font-mono">{result.summary?.objective_value ?? '-'}</span></span>
                  <span>시간: <span className="text-white font-mono">{result.summary?.timing?.total_sec ?? '-'}s</span></span>
                </div>
              )}
              {!result?.success && <div className="text-red-300 mt-1">{result?.error}</div>}
            </div>
          );
        })}
      </div>
      <button onClick={onReset} className="w-full mt-3 py-2 rounded-lg text-sm text-slate-300 bg-slate-800 hover:bg-slate-700 transition">
        다시 실행
      </button>
    </div>
  );
}

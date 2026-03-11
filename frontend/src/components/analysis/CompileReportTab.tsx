// src/components/analysis/CompileReportTab.tsx
// 컴파일 리포트 서브탭 (솔버, 변수, 제약조건, 경고)
import { useState } from 'react';
import { AlertTriangle, Package, ChevronDown, ChevronRight } from 'lucide-react';
import type { CompileSummary } from './types';

const formatNumber = (n: any) => {
  if (n == null) return '-';
  if (typeof n === 'number') return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
  return String(n);
};

export function CompileReportTab({
  compileSummary,
  compileWarnings,
}: {
  compileSummary: CompileSummary;
  compileWarnings: string[];
}) {
  const [warningsExpanded, setWarningsExpanded] = useState(false);
  const constraints = compileSummary.constraints || { total_in_model: 0, applied: 0, failed: 0 };

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="bg-slate-800/50 rounded-xl border border-slate-700 p-4">
        <h3 className="text-sm font-bold text-slate-300 mb-3 flex items-center gap-2">
          <Package size={14} className="text-cyan-400" /> 컴파일 요약
        </h3>
        <div className="space-y-2 text-[13px]">
          <div className="flex justify-between">
            <span className="text-slate-500">솔버</span>
            <span className="text-cyan-400 font-mono">{compileSummary.solver_name} ({compileSummary.solver_type})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">변수</span>
            <span className="text-white font-mono">{formatNumber(compileSummary.variables_created)}개</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-500">제약조건</span>
            <span className={`font-mono font-bold ${constraints.failed > 0 ? 'text-yellow-400' : 'text-green-400'}`}>
              {constraints.applied}/{constraints.total_in_model}
            </span>
          </div>
          {constraints.total_in_model > 0 && (
            <div className="mt-1">
              <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${constraints.failed === 0 ? 'bg-green-500' : 'bg-yellow-500'}`}
                  style={{ width: `${(constraints.applied / constraints.total_in_model) * 100}%` }} />
              </div>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-slate-500">목적함수</span>
            <span className={compileSummary.objective_parsed === false ? 'text-yellow-400' : 'text-green-400'}>
              {compileSummary.objective_parsed === false ? 'default' : 'parsed'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">컴파일 시간</span>
            <span className="text-white font-mono">{compileSummary.compile_time_sec ?? '-'}s</span>
          </div>
        </div>
      </div>

      {compileWarnings.length > 0 && (
        <div className="bg-yellow-500/5 rounded-xl border border-yellow-500/20 p-4">
          <button onClick={() => setWarningsExpanded(!warningsExpanded)}
            className="w-full flex items-center justify-between text-sm font-bold text-yellow-400">
            <span className="flex items-center gap-2"><AlertTriangle size={14} /> 경고 ({compileWarnings.length})</span>
            {warningsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          {warningsExpanded && (
            <div className="mt-3 space-y-1 max-h-40 overflow-y-auto custom-scrollbar">
              {compileWarnings.map((w: string, i: number) => (
                <div key={i} className="text-[11px] text-yellow-300/80">#{i+1} {w}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

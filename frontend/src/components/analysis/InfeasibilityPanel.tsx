// src/components/analysis/InfeasibilityPanel.tsx
// INFEASIBLE 진단 정보 표시 패널

interface InfeasibilityPanelProps {
  info: any;
}

export function InfeasibilityPanel({ info }: InfeasibilityPanelProps) {
  if (!info) return null;

  return (
    <div className="mt-3 space-y-3">
      {/* 제약조건 요약 */}
      <div className="p-3 bg-slate-800/60 rounded-lg">
        <p className="text-xs font-semibold text-slate-300 mb-2">적용된 제약조건</p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="text-slate-400">
            Hard 제약: <span className="text-white font-mono">
              {info.summary?.hard_constraint_count || 0}개 ({info.summary?.hard_instance_count || 0} 인스턴스)
            </span>
          </div>
          <div className="text-slate-400">
            Soft 제약: <span className="text-white font-mono">
              {info.summary?.soft_constraint_count || 0}개 ({info.summary?.soft_instance_count || 0} 인스턴스)
            </span>
          </div>
        </div>
        {info.applied_constraints?.length > 0 && (
          <div className="mt-2 space-y-1">
            {info.applied_constraints.map((c: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={`w-1.5 h-1.5 rounded-full ${c.category === 'hard' ? 'bg-red-400' : 'bg-yellow-400'}`} />
                <span className="text-slate-300">{c.name}</span>
                <span className="text-slate-500">({c.count})</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 충돌 힌트 */}
      {info.conflict_hints?.length > 0 && (
        <div className="p-3 bg-amber-900/30 border border-amber-500/30 rounded-lg">
          <p className="text-xs font-semibold text-amber-300 mb-2">충돌 가능성 분석</p>
          {info.conflict_hints.map((hint: any, i: number) => (
            <div key={i} className="mb-2 last:mb-0">
              <p className="text-xs text-amber-200">{hint.message}</p>
              {hint.constraints && (
                <p className="text-xs text-amber-400/70 mt-0.5">
                  관련 제약: {hint.constraints.join(', ')}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 컴파일 실패 제약 */}
      {info.failed_constraints?.length > 0 && (
        <div className="p-3 bg-slate-800/60 rounded-lg">
          <p className="text-xs font-semibold text-orange-300 mb-1">
            미적용 제약조건 ({info.summary?.failed_constraint_count}개)
          </p>
          <p className="text-xs text-slate-400">아래 제약은 컴파일에 실패하여 적용되지 않았습니다.</p>
          <div className="mt-1 space-y-0.5">
            {info.failed_constraints.map((c: any, i: number) => (
              <div key={i} className="text-xs text-orange-300/70">• {c.name}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

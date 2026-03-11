// src/components/analysis/DutyScheduleTab.tsx
// 듀티 배정표 서브탭 (정렬/필터, 트립 타임라인)
import { useState, useMemo } from 'react';
import { XCircle, ChevronDown, ChevronRight } from 'lucide-react';
import type { InterpretedResult, DutyDetail } from './types';

export function DutyScheduleTab({
  interpreted,
}: {
  interpreted?: InterpretedResult;
}) {
  const [expandedDuty, setExpandedDuty] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState<'duty_id' | 'trip_count' | 'start_time' | 'driving'>('duty_id');
  const [filter, setFilter] = useState<'all' | 'violations'>('all');

  if (!interpreted || !interpreted.duties?.length) {
    return <div className="text-center text-slate-500 py-8">해석된 결과가 없습니다</div>;
  }

  const sortedDuties = useMemo(() => {
    const duties = [...interpreted.duties];
    const filtered = filter === 'violations'
      ? duties.filter(d => d.violations && d.violations.length > 0)
      : duties;
    switch (sortBy) {
      case 'trip_count': return filtered.sort((a, b) => b.trip_count - a.trip_count);
      case 'start_time': return filtered.sort((a, b) => a.start_time_min - b.start_time_min);
      case 'driving': return filtered.sort((a, b) => b.total_driving_min - a.total_driving_min);
      default: return filtered.sort((a, b) => a.duty_id - b.duty_id);
    }
  }, [interpreted.duties, sortBy, filter]);

  return (
    <div className="space-y-3 animate-in fade-in duration-300">
      {/* 정렬/필터 */}
      <div className="flex gap-2 items-center">
        <select value={sortBy} onChange={e => setSortBy(e.target.value as any)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-[12px] text-slate-300">
          <option value="duty_id">듀티 번호순</option>
          <option value="start_time">시작 시각순</option>
          <option value="trip_count">트립 수순</option>
          <option value="driving">운전시간순</option>
        </select>
        <select value={filter} onChange={e => setFilter(e.target.value as any)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-[12px] text-slate-300">
          <option value="all">전체 ({interpreted.duties.length})</option>
          <option value="violations">위반만 ({interpreted.duties.filter(d => d.violations?.length).length})</option>
        </select>
        <span className="text-[11px] text-slate-500 ml-auto">{sortedDuties.length}개 듀티</span>
      </div>

      {/* 듀티 목록 */}
      <div className="space-y-2 max-h-[calc(100vh-320px)] overflow-y-auto custom-scrollbar">
        {sortedDuties.map(duty => {
          const isExpanded = expandedDuty === duty.duty_id;
          const hasViolation = duty.violations && duty.violations.length > 0;
          return (
            <div key={duty.duty_id}
              className={`rounded-xl border transition-all ${
                hasViolation
                  ? 'bg-red-500/5 border-red-500/20'
                  : 'bg-slate-800/50 border-slate-700'
              }`}>
              <button onClick={() => setExpandedDuty(isExpanded ? null : duty.duty_id)}
                className="w-full p-3 flex items-center gap-3 text-left">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold ${
                  hasViolation ? 'bg-red-500/20 text-red-400' : 'bg-cyan-500/10 text-cyan-400'
                }`}>
                  D{duty.duty_id}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] text-white font-medium">
                      {duty.start_hhmm} ~ {duty.end_hhmm}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {duty.trip_count}트립
                    </span>
                    {hasViolation && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">위반</span>
                    )}
                  </div>
                  <div className="flex gap-3 text-[11px] text-slate-500 mt-0.5">
                    <span>운전 {duty.total_driving_min}분</span>
                    <span>대기 {duty.idle_min}분</span>
                    <span>체류 {duty.total_stay_min}분</span>
                  </div>
                </div>
                {isExpanded ? <ChevronDown size={14} className="text-slate-500" />
                  : <ChevronRight size={14} className="text-slate-500" />}
              </button>

              {isExpanded && (
                <div className="px-3 pb-3 border-t border-slate-700/50">
                  {/* 위반 사항 */}
                  {hasViolation && (
                    <div className="mt-2 mb-2">
                      {duty.violations!.map((v, i) => (
                        <div key={i} className="flex items-center gap-1 text-[11px] text-red-400">
                          <XCircle size={10} /> {v}
                        </div>
                      ))}
                    </div>
                  )}
                  {/* 트립 타임라인 */}
                  <div className="mt-2 space-y-1">
                    {duty.trips.map((trip, i) => (
                      <div key={trip.trip_id}
                        className="flex items-center gap-2 text-[11px] py-1 px-2 rounded bg-slate-800/50">
                        <span className="text-slate-600 w-4">{i+1}</span>
                        <span className="text-cyan-400 font-mono w-16">{trip.dep_hhmm}→{trip.arr_hhmm}</span>
                        <span className="text-slate-400 flex-1 truncate">
                          {trip.dep_station} → {trip.arr_station}
                        </span>
                        <span className="text-slate-500 w-10 text-right">{trip.duration}분</span>
                        <span className={`w-12 text-right ${trip.direction === 'forward' ? 'text-blue-400' : 'text-amber-400'}`}>
                          {trip.direction === 'forward' ? '상행' : '하행'}
                        </span>
                      </div>
                    ))}
                  </div>
                  {/* 듀티 요약 바 */}
                  <div className="mt-2 flex gap-2 text-[10px] text-slate-500">
                    {duty.crew_id && <span>승무원 #{duty.crew_id}</span>}
                    <span>근무 {duty.total_work_min}분</span>
                    <span>체류 {duty.total_stay_min}분</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

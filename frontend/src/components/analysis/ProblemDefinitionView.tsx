// src/components/analysis/ProblemDefinitionView.tsx
// v2.0 - Edit mode + Objective change gate
import {
  ClipboardList, Check, Edit3, AlertTriangle,
  ChevronDown, ChevronUp, X, Lock, RefreshCw, Info, Shield, ShieldAlert
} from 'lucide-react';
import { useState, useCallback, useEffect } from 'react';
import type { ProblemDefinitionData } from './types';

interface ConstraintEdit {
  name: string;
  category: 'hard' | 'soft';
  origCategory: 'hard' | 'soft';
  fixed: boolean;
  changeable: boolean;
  desc: string;
  nameKo: string;
  changed: boolean;
}

export function ProblemDefinitionView({
  data, onAction,
}: {
  data: ProblemDefinitionData;
  onAction?: (type: string, message: string) => void;
}) {
  const [showParams, setShowParams] = useState(true);
  const [isEditMode, setIsEditMode] = useState(false);
  const [edits, setEdits] = useState<ConstraintEdit[]>([]);
  const [warnIdx, setWarnIdx] = useState<number | null>(null);
  const [showObjGate, setShowObjGate] = useState(false);


  const proposal = data.proposal || data.confirmed_problem;
  const isConfirmed = data.view_mode === 'problem_defined';
  const agentStatus = (data as any)?.agent_status || '';

  // Reset edit mode when constraints are rebuilt after objective change
  useEffect(() => {
    if (agentStatus === 'objective_changed_constraints_rebuilt') {
      setIsEditMode(false);
      setEdits([]);
      setShowObjGate(false);
    }
  }, [agentStatus]);

  if (!proposal) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 p-8">
        <p>{'\uBB38\uC81C \uC815\uC758 \uB370\uC774\uD130\uB97C \uBD88\uB7EC\uC624\uB294 \uC911...'}</p>
      </div>
    );
  }

  const objective = proposal.objective || {};
  const hardConstraints = proposal.hard_constraints || {};
  const softConstraints = proposal.soft_constraints || {};
  const parameters = proposal.parameters || {};

  const dataParams = Object.entries(parameters).filter(([, v]: [string, any]) => v.source === 'data');
  const defaultParams = Object.entries(parameters).filter(([, v]: [string, any]) => v.source === 'default');
  const missingParams = Object.entries(parameters).filter(([, v]: [string, any]) => v.source === 'user_input_required');

  // Build edit state
  const enterEditMode = useCallback(() => {
    const list: ConstraintEdit[] = [];
    const parse = (cs: any, cat: 'hard' | 'soft') => {
      Object.entries(cs).forEach(([k, c]: [string, any]) => {
        list.push({
          name: k,
          category: cat,
          origCategory: cat,
          fixed: c.fixed === true || c.changeable === false,
          changeable: c.changeable !== false,
          desc: c.description || '',
          nameKo: c.name_ko || c.korean_name || c.description || '',
          changed: false,
        });
      });
    };
    parse(hardConstraints, 'hard');
    parse(softConstraints, 'soft');
    setEdits(list);
    setIsEditMode(true);
  }, [hardConstraints, softConstraints]);

  const requestToggle = (idx: number) => {
    const e = edits[idx];
    if (e.fixed || !e.changeable) return;
    setWarnIdx(idx);
  };

  const confirmToggle = () => {
    if (warnIdx === null) return;
    setEdits(prev =>
      prev.map((e, i) => {
        if (i !== warnIdx) return e;
        const nc = e.category === 'hard' ? 'soft' as const : 'hard' as const;
        return { ...e, category: nc, changed: nc !== e.origCategory };
      })
    );
    setWarnIdx(null);
  };

  const applyEdits = () => {
    const msgs: string[] = [];
    edits.forEach(e => {
      if (e.changed) {
        msgs.push(e.name + ' ' + e.category + '\uB85C \uBCC0\uACBD');
      }
    });
    if (msgs.length === 0) {
      onAction?.('send', '\uD655\uC778');
    } else {
      onAction?.('send', msgs.join('\n'));
    }
    setIsEditMode(false);
    setEdits([]);
  };

  const cancelEdit = () => {
    setIsEditMode(false);
    setEdits([]);
    setWarnIdx(null);
  };

  const confirmObjChange = () => { setShowObjGate(false); setIsEditMode(false); setEdits([]); onAction?.('send', '\uBAA9\uC801\uD568\uC218 \uBCC0\uACBD'); };

    const hardEdits = edits.filter(e => e.category === 'hard');
  const softEdits = edits.filter(e => e.category === 'soft');
  const changedCount = edits.filter(e => e.changed).length;
  const warnEdit = warnIdx !== null ? edits[warnIdx] : null;

  return (
    <div className="h-full flex flex-col bg-slate-900 overflow-hidden animate-fade-in">

      {/* Header */}
      <div className="p-6 border-b border-slate-800 bg-slate-900/95 sticky top-0 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={isConfirmed ? 'p-2 rounded-lg bg-emerald-500/20 text-emerald-400' : 'p-2 rounded-lg bg-amber-500/20 text-amber-400'}>
              <ClipboardList size={20} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">
                {isConfirmed ? '\uBB38\uC81C \uC815\uC758 \uD655\uC815' : '\uBB38\uC81C \uC815\uC758 \uC81C\uC548'}
              </h2>
              <p className="text-xs text-slate-400">{isConfirmed ? '\uD655\uC815\uB428' : '\uAC80\uD1A0 \uD6C4 \uD655\uC778 \uB610\uB294 \uC218\uC815'}</p>
            </div>
          </div>
          {!isConfirmed && !isEditMode && (
            <button onClick={enterEditMode}
              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors">
              <Edit3 size={13} /> {'\uC218\uC815'}
            </button>
          )}
          {isEditMode && (
            <div className="flex items-center gap-2">
              {changedCount > 0 && <span className="text-xs text-amber-400">{changedCount + '\uAC1C \uBCC0\uACBD'}</span>}
              <button onClick={cancelEdit} className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600">
                <X size={13} /> {'\uCDE8\uC18C'}
              </button>
              <button onClick={applyEdits} className="flex items-center gap-1 px-3 py-1.5 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-500">
                <Check size={13} /> {changedCount > 0 ? '\uBCC0\uACBD \uC801\uC6A9' : '\uD655\uC778'}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">

        {/* Warning: category change */}
        {warnEdit && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4">
            <div className="flex items-start gap-2">
              <AlertTriangle size={16} className="text-amber-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-amber-300">
                  {warnEdit.category === 'hard'
                    ? '\u26A0\uFE0F Hard \u2192 Soft: \uD574\uB2F9 \uC81C\uC57D\uC744 \uC704\uBC18\uD558\uB294 \uACB0\uACFC\uAC00 \uD5C8\uC6A9\uB429\uB2C8\uB2E4.'
                    : '\u26A0\uFE0F Soft \u2192 Hard: \uC2E4\uD589 \uBD88\uAC00\uB2A5(infeasible)\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.'}
                </p>
                <p className="text-xs text-amber-400/70 mt-1">{'\uB300\uC0C1: ' + (warnEdit.nameKo || warnEdit.name)}</p>
                <div className="flex gap-2 mt-2">
                  <button onClick={confirmToggle} className="px-3 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-500">{'\uBCC0\uACBD'}</button>
                  <button onClick={() => setWarnIdx(null)} className="px-3 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600">{'\uCDE8\uC18C'}</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Objective change gate */}
        {showObjGate && (
          <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
            <div className="flex items-start gap-2">
              <RefreshCw size={16} className="text-orange-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-orange-300">{'\uBAA9\uC801\uD568\uC218\uB97C \uBCC0\uACBD\uD558\uBA74 \uC81C\uC57D\uC870\uAC74\uC774 \uC0C8\uB85C \uAD6C\uC131\uB429\uB2C8\uB2E4.'}</p>
                <p className="text-xs text-orange-400/70 mt-1">{'\uD604\uC7AC \uC218\uC815\uD55C \uC81C\uC57D\uC870\uAC74 \uD3B8\uC9D1 \uB0B4\uC6A9\uC740 \uCD08\uAE30\uD654\uB429\uB2C8\uB2E4.'}</p>
                <div className="flex gap-2 mt-2">
                  <button onClick={confirmObjChange} className="px-3 py-1 text-xs bg-orange-600 text-white rounded hover:bg-orange-500">{'\uACC4\uC18D \uBCC0\uACBD'}</button>
                  <button onClick={() => setShowObjGate(false)} className="px-3 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600">{'\uCDE8\uC18C'}</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Problem type */}
        {(proposal.stage || proposal.variant) && (
          <section className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
            <h3 className="text-sm font-semibold text-slate-300 mb-2">{'\uBB38\uC81C \uC720\uD615'}</h3>
            <div className="flex gap-4 text-sm">
              {proposal.stage && <span className="text-cyan-400">{'\uB2E8\uACC4: ' + proposal.stage}</span>}
              {proposal.variant && <span className="text-slate-300">{'\uC138\uBD80: ' + proposal.variant}</span>}
            </div>
          </section>
        )}

        {/* Objective */}
        <section className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">{'\uBAA9\uC801\uD568\uC218'}</h3>
            {!isConfirmed && !isEditMode && (
              <button onClick={() => setShowObjGate(true)} className="text-xs px-2 py-1 bg-orange-500/20 text-orange-400 rounded hover:bg-orange-500/30 transition-colors">{'\uBCC0\uACBD'}</button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-xs bg-indigo-500/20 text-indigo-400 rounded">{objective.type || 'minimize'}</span>
            <p className="text-sm text-slate-200">{objective.description_ko || objective.description || objective.target || '-'}</p>
          </div>
          {objective.alternatives && objective.alternatives.length > 0 && !isEditMode && (
            <div className="mt-2">
              <p className="text-xs text-slate-500 mb-1">{'\uB300\uC548'}:</p>
              <div className="flex gap-2 flex-wrap">
                {objective.alternatives.map((alt: any, i: number) => (
                  <span key={i} className="px-2 py-0.5 text-xs bg-slate-700 text-slate-400 rounded-full">
                    {alt.description || alt.target}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Constraints */}
        <section className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">{'\uC81C\uC57D\uC870\uAC74'}</h3>

          {/* Hard constraints */}
          {!isEditMode ? (
            <>
              {Object.keys(hardConstraints).length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-red-400 font-semibold mb-1">{'\uD544\uC218 (Hard) - ' + Object.keys(hardConstraints).length + '\uAC1C'}</p>
                  {Object.entries(hardConstraints).map(([k, v]: [string, any]) => (
                    <div key={k} className="flex items-start justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0">
                      <div className="flex items-start gap-2">
                        <Shield size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="text-slate-200 font-medium">{v.name_ko || v.korean_name || k}</span>
                          {v.description && <p className="text-xs text-slate-500">{v.description}</p>}
                        </div>
                      </div>
                      {v.changeable !== false && <span className="text-[10px] text-slate-600">{'[\uBCC0\uACBD\uAC00\uB2A5]'}</span>}
                    </div>
                  ))}
                </div>
              )}
              {Object.keys(softConstraints).length > 0 && (
                <div>
                  <p className="text-xs text-amber-400 font-semibold mb-1">{'\uC120\uD638 (Soft) - ' + Object.keys(softConstraints).length + '\uAC1C'}</p>
                  {Object.entries(softConstraints).map(([k, v]: [string, any]) => (
                    <div key={k} className="flex items-start justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0">
                      <div className="flex items-start gap-2">
                        <ShieldAlert size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="text-slate-200 font-medium">{v.name_ko || v.korean_name || k}</span>
                          {v.description && <p className="text-xs text-slate-500">{v.description}</p>}
                        </div>
                      </div>
                      <span className="text-[10px] text-slate-600">{'[\uBCC0\uACBD\uAC00\uB2A5]'}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            /* Edit mode */
            <>
              <div className="mb-3">
                <p className="text-xs text-red-400 font-semibold mb-1">{'\uD544\uC218 (Hard) - ' + hardEdits.length + '\uAC1C'}</p>
                {hardEdits.map((e) => {
                  const gIdx = edits.indexOf(e);
                  return (
                    <div key={e.name} className={e.changed ? "flex items-center justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0 bg-amber-500/10" : "flex items-center justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0"}>
                      <div className="flex items-start gap-2 flex-1">
                        <Shield size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-slate-200 font-medium">{e.nameKo || e.name}</span>
                            {e.fixed && (
                              <span className="inline-flex items-center gap-0.5 text-[10px] bg-slate-700 text-slate-500 px-1.5 py-0.5 rounded">
                                <Lock size={9} /> {'\uACE0\uC815'}
                              </span>
                            )}
                            {e.changed && <span className="text-[10px] bg-amber-500/30 text-amber-400 px-1.5 py-0.5 rounded">{'\uBCC0\uACBD\uB428'}</span>}
                          </div>
                          <p className="text-xs text-slate-500 font-mono">{e.name}</p>
                        </div>
                      </div>
                      {e.changeable && !e.fixed && (
                        <button onClick={() => requestToggle(gIdx)} className="text-xs px-2.5 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors ml-2 whitespace-nowrap">{'\u2192 Soft'}</button>
                      )}
                    </div>
                  );
                })}
              </div>
              <div>
                <p className="text-xs text-amber-400 font-semibold mb-1">{'\uC120\uD638 (Soft) - ' + softEdits.length + '\uAC1C'}</p>
                {softEdits.map((e) => {
                  const gIdx = edits.indexOf(e);
                  return (
                    <div key={e.name} className={e.changed ? "flex items-center justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0 bg-amber-500/10" : "flex items-center justify-between text-sm py-1.5 border-b border-slate-700/50 last:border-0"}>
                      <div className="flex items-start gap-2 flex-1">
                        <ShieldAlert size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-slate-200 font-medium">{e.nameKo || e.name}</span>
                            {e.changed && <span className="text-[10px] bg-amber-500/30 text-amber-400 px-1.5 py-0.5 rounded">{'\uBCC0\uACBD\uB428'}</span>}
                          </div>
                          <p className="text-xs text-slate-500 font-mono">{e.name}</p>
                        </div>
                      </div>
                      {e.changeable && !e.fixed && (
                        <button onClick={() => requestToggle(gIdx)} className="text-xs px-2.5 py-1 bg-blue-500/20 text-blue-400 rounded hover:bg-blue-500/30 transition-colors ml-2 whitespace-nowrap">{'\u2192 Hard'}</button>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>

        {/* Edit mode info */}
        {isEditMode && (
          <div className="flex items-start gap-2 p-3 bg-blue-500/10 rounded-xl border border-blue-500/20">
            <Info size={13} className="text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-[11px] text-blue-300 leading-relaxed">
              {'[\uACE0\uC815] \uC81C\uC57D\uC740 \uBCC0\uACBD \uBD88\uAC00. Hard\u2192Soft \uC2DC \uADDC\uCE59 \uC704\uBC18 \uD5C8\uC6A9, Soft\u2192Hard \uC2DC infeasible \uC704\uD5D8. \uBAA9\uC801\uD568\uC218 \uBCC0\uACBD\uC740 \uD3B8\uC9D1 \uCDE8\uC18C \uD6C4 [\uBCC0\uACBD] \uBC84\uD2BC \uC0AC\uC6A9.'}
            </p>
          </div>
        )}

        {/* Parameters */}
        <section className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
          <button onClick={() => setShowParams(!showParams)}
            className="flex items-center justify-between w-full text-sm font-semibold text-slate-300">
            <span>{'\uD30C\uB77C\uBBF8\uD130 (' + Object.keys(parameters).length + ')'}</span>
            {showParams ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showParams && (
            <div className="mt-3 space-y-3">
              {dataParams.length > 0 && (
                <div>
                  <p className="text-xs text-emerald-400 mb-1">{'\uB370\uC774\uD130 \uCD94\uCD9C'}</p>
                  {dataParams.map(([k, v]: [string, any]) => (
                    <div key={k} className="flex justify-between text-sm py-0.5">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-emerald-300 font-mono">{v.value ?? '-'}</span>
                    </div>
                  ))}
                </div>
              )}
              {defaultParams.length > 0 && (
                <div>
                  <p className="text-xs text-amber-400 mb-1">{'\uAE30\uBCF8\uAC12 (\uC218\uC815 \uAC00\uB2A5)'}</p>
                  {defaultParams.map(([k, v]: [string, any]) => (
                    <div key={k} className="flex justify-between text-sm py-0.5">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-amber-300 font-mono">{v.value ?? '-'}</span>
                    </div>
                  ))}
                </div>
              )}
              {missingParams.length > 0 && (
                <div>
                  <p className="text-xs text-red-400 mb-1">{'\uC785\uB825 \uD544\uC694'}</p>
                  {missingParams.map(([k]: [string, any]) => (
                    <div key={k} className="flex justify-between text-sm py-0.5">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-red-400 font-mono">???</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Action bar */}
      {!isEditMode && !isConfirmed && (
        <div className="p-4 border-t border-slate-800 bg-slate-900 flex gap-3">
          <button onClick={() => onAction?.('send', '\uD655\uC778')}
            className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-xl transition flex items-center justify-center gap-2">
            <Check size={18} /> {'\uD655\uC778'}
          </button>
          <button onClick={enterEditMode}
            className="px-6 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold py-3 rounded-xl transition border border-slate-700 flex items-center justify-center gap-2">
            <Edit3 size={18} /> {'\uC218\uC815'}
          </button>
        </div>
      )}
    </div>
  );
}

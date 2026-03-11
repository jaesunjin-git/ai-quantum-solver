/**
 * ValidationDrawer — Bottom slide-up panel for validation findings.
 *
 * Design:
 *   - Collapsed by default (single-line summary bar)
 *   - Auto-expands when errors exist
 *   - Each item shows: severity icon, message, action buttons
 *   - Actions: auto-fix, user input, dismiss
 *   - "Apply & Continue" button when all errors resolved
 *
 * Platform-generic: no domain-specific logic.
 * All labels come from backend ValidationItem.message.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle, CheckCircle, XCircle, Info,
  ChevronUp, ChevronDown, Wrench, X, Send
} from 'lucide-react';
import type { StageValidation, ValidationItem } from './types';

interface ValidationDrawerProps {
  validation: StageValidation | null | undefined;
  onApplyFix?: (code: string) => void;
  onDismiss?: (code: string) => void;
  onUserInput?: (code: string, value: any) => void;
  onProceed?: () => void;
}

const SEVERITY_CONFIG = {
  error:   { icon: XCircle,       color: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/30',   label: '오류' },
  warning: { icon: AlertTriangle,  color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/30', label: '경고' },
  info:    { icon: Info,           color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/30',  label: '정보' },
};

export default function ValidationDrawer({
  validation,
  onApplyFix,
  onDismiss,
  onUserInput,
  onProceed,
}: ValidationDrawerProps) {
  const [expanded, setExpanded] = useState(false);
  const [userValues, setUserValues] = useState<Record<string, string>>({});

  // Auto-expand when there are errors
  useEffect(() => {
    if (validation && validation.error_count > 0) {
      setExpanded(true);
    }
  }, [validation?.error_count]);

  const handleUserInputChange = useCallback((code: string, value: string) => {
    setUserValues(prev => ({ ...prev, [code]: value }));
  }, []);

  const handleUserInputSubmit = useCallback((code: string, param: string) => {
    const value = userValues[code];
    if (value !== undefined && onUserInput) {
      onUserInput(code, { [param]: value });
    }
  }, [userValues, onUserInput]);

  // Don't render if no validation data or empty
  if (!validation || validation.items.length === 0) {
    return null;
  }

  const activeItems = validation.items.filter(i => !i.dismissed);
  const hasErrors = validation.error_count > 0;
  const hasWarnings = validation.warning_count > 0;

  if (activeItems.length === 0) {
    // All dismissed — show simple pass bar
    return (
      <div className="border-t border-slate-700 bg-slate-800/50 px-4 py-2 flex items-center gap-2">
        <CheckCircle size={14} className="text-emerald-400" />
        <span className="text-xs text-emerald-400">검증 통과</span>
      </div>
    );
  }

  return (
    <div className={`border-t ${hasErrors ? 'border-red-500/50' : 'border-amber-500/30'} bg-slate-800/80 backdrop-blur`}>
      {/* Collapsed summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2 flex items-center justify-between hover:bg-slate-700/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {hasErrors && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <XCircle size={14} /> {validation.error_count} 오류
            </span>
          )}
          {hasWarnings && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <AlertTriangle size={14} /> {validation.warning_count} 경고
            </span>
          )}
          {validation.info_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-blue-400">
              <Info size={14} /> {validation.info_count} 안내
            </span>
          )}
        </div>
        {expanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronUp size={16} className="text-slate-400" />}
      </button>

      {/* Expanded detail panel */}
      {expanded && (
        <div className="px-4 pb-3 space-y-2 max-h-64 overflow-y-auto">
          {activeItems.map((item) => (
            <ValidationItemCard
              key={item.code}
              item={item}
              userValue={userValues[item.code]}
              onApplyFix={onApplyFix}
              onDismiss={onDismiss}
              onUserInputChange={handleUserInputChange}
              onUserInputSubmit={handleUserInputSubmit}
            />
          ))}

          {/* Proceed button */}
          {!hasErrors && onProceed && (
            <button
              onClick={onProceed}
              className="w-full mt-2 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
            >
              수정 적용 후 계속
            </button>
          )}
          {hasErrors && (
            <p className="text-xs text-red-400/70 text-center mt-1">
              오류를 해결해야 다음 단계로 진행할 수 있습니다
            </p>
          )}
        </div>
      )}
    </div>
  );
}


// ── Individual Validation Item Card ──

interface ValidationItemCardProps {
  item: ValidationItem;
  userValue?: string;
  onApplyFix?: (code: string) => void;
  onDismiss?: (code: string) => void;
  onUserInputChange: (code: string, value: string) => void;
  onUserInputSubmit: (code: string, param: string) => void;
}

function ValidationItemCard({
  item,
  userValue,
  onApplyFix,
  onDismiss,
  onUserInputChange,
  onUserInputSubmit,
}: ValidationItemCardProps) {
  const config = SEVERITY_CONFIG[item.severity];
  const Icon = config.icon;

  return (
    <div className={`rounded-lg border ${config.border} ${config.bg} p-3`}>
      <div className="flex items-start gap-2">
        <Icon size={16} className={`${config.color} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200">{item.message}</p>
          {item.detail && (
            <p className="text-xs text-slate-400 mt-1">{item.detail}</p>
          )}
          {item.suggestion && (
            <p className="text-xs text-slate-300 mt-1">{item.suggestion}</p>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {/* Auto-fix button */}
            {item.auto_fix && onApplyFix && (
              <button
                onClick={() => onApplyFix(item.code)}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium bg-cyan-600/30 text-cyan-300 hover:bg-cyan-600/50 transition-colors"
              >
                <Wrench size={12} />
                {item.auto_fix.label || `${item.auto_fix.old_val} → ${item.auto_fix.new_val} 적용`}
              </button>
            )}

            {/* User input field */}
            {item.user_input && (
              <div className="inline-flex items-center gap-1">
                <input
                  type={item.user_input.input_type === 'number' ? 'number' : 'text'}
                  placeholder={item.user_input.placeholder || item.user_input.param}
                  defaultValue={item.user_input.default ?? ''}
                  value={userValue ?? ''}
                  onChange={(e) => onUserInputChange(item.code, e.target.value)}
                  className="w-24 px-2 py-1 rounded text-xs bg-slate-700 border border-slate-600 text-slate-200 placeholder-slate-500"
                />
                {item.user_input.unit && (
                  <span className="text-xs text-slate-400">{item.user_input.unit}</span>
                )}
                <button
                  onClick={() => onUserInputSubmit(item.code, item.user_input!.param)}
                  className="p-1 rounded hover:bg-slate-600 transition-colors"
                >
                  <Send size={12} className="text-cyan-400" />
                </button>
              </div>
            )}

            {/* Dismiss button (only for warnings, not errors) */}
            {item.severity !== 'error' && onDismiss && (
              <button
                onClick={() => onDismiss(item.code)}
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors"
              >
                <X size={12} /> 무시
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

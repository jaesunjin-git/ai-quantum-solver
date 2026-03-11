// src/components/ChatInputBar.tsx
// 채팅 입력 영역 (텍스트 입력 + 파일 첨부 + 전송 버튼)
import React, { useRef } from 'react';
import { Send, Paperclip } from 'lucide-react';

export function ChatInputBar({
  inputValue,
  isLoading,
  onInputChange,
  onSend,
  onFileUpload,
}: {
  inputValue: string;
  isLoading: boolean;
  onInputChange: (value: string) => void;
  onSend: (text: string) => void;
  onFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="p-4 bg-slate-900 border-t border-slate-800">
      <div className="flex gap-3 relative max-w-4xl mx-auto">
        <input
          type="file"
          multiple
          className="hidden"
          ref={fileInputRef}
          onChange={onFileUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 h-12 w-12 flex items-center justify-center rounded-xl border border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-cyan-400 hover:border-cyan-500/50 transition-all"
        >
          <Paperclip size={20} />
        </button>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isLoading && onSend(inputValue)}
          placeholder="메시지를 입력하세요..."
          disabled={isLoading}
          className="flex-1 rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none transition-all disabled:opacity-50"
        />
        <button
          onClick={() => onSend(inputValue)}
          disabled={!inputValue.trim() || isLoading}
          className="flex-shrink-0 h-12 w-12 flex items-center justify-center rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-indigo-500/30"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
}

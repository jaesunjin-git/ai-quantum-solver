// src/components/ChatMessageBubble.tsx
// 개별 채팅 메시지 버블 (사용자/봇 + 옵션 버튼)
import { Bot, User } from 'lucide-react';

interface OptionItem {
  label: string;
  action: string;
  message?: string;
  value?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  data?: any;
  options?: OptionItem[];
}

export function ChatMessageBubble({
  message,
  onOptionClick,
}: {
  message: Message;
  onOptionClick: (opt: OptionItem) => void;
}) {
  const isUser = message.role === 'user';

  return (
    <div
      className={`flex w-full items-start gap-4 ${
        isUser ? 'justify-end' : 'justify-start'
      }`}
    >
      {!isUser && (
        <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-full bg-slate-700 border border-slate-600 shadow-sm">
          <Bot className="h-5 w-5 text-cyan-400" />
        </div>
      )}
      <div
        className={`flex flex-col gap-2 max-w-[75%] ${
          isUser ? 'items-end' : 'items-start'
        }`}
      >
        <div
          className={`rounded-2xl px-5 py-3.5 text-[15px] leading-relaxed shadow-md ${
            isUser
              ? 'bg-indigo-600 text-white rounded-tr-none'
              : 'bg-slate-800 border border-slate-700 text-slate-200 rounded-tl-none'
          }`}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>

        {message.options && message.options.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {message.options.map((opt, idx) => (
              <button
                key={idx}
                onClick={() => onOptionClick(opt)}
                className="px-3 py-1.5 text-xs font-medium text-cyan-300 bg-slate-800 border border-slate-600 hover:bg-slate-700 hover:border-cyan-500 rounded-full transition-all"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 shadow-lg shadow-indigo-500/20">
          <User className="h-5 w-5 text-white" />
        </div>
      )}
    </div>
  );
}

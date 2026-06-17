import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Message } from '../types';
import { sendConvMessage, renameConversation } from '../api';
import './ChatArea.css';

interface Props {
  convId: string | null;
  messages: Message[];
  onMessagesUpdate: (messages: Message[]) => void;
  onNeedConv: () => Promise<string>;   // 대화 없을 때 자동 생성
  onConvCreated: (id: string) => void; // 생성된 convId 부모에 알림
}

function parseInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*(.+?)\*\*|\*(.+?)\*)/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[0].startsWith('**')) parts.push(<strong key={m.index}>{m[2]}</strong>);
    else parts.push(<em key={m.index}>{m[3]}</em>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const result: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^---+$/.test(line.trim())) { result.push(<hr key={i} className="md-hr"/>); i++; continue; }
    const h3 = line.match(/^###\s+(.*)/); const h2 = line.match(/^##\s+(.*)/); const h1 = line.match(/^#\s+(.*)/);
    if (h3) { result.push(<h3 key={i} className="md-h3">{parseInline(h3[1])}</h3>); i++; continue; }
    if (h2) { result.push(<h2 key={i} className="md-h2">{parseInline(h2[1])}</h2>); i++; continue; }
    if (h1) { result.push(<h2 key={i} className="md-h2">{parseInline(h1[1])}</h2>); i++; continue; }
    if (line.trim().startsWith('|') && i+1 < lines.length && lines[i+1].trim().match(/^\|[-| :]+\|$/)) {
      const tl: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) { tl.push(lines[i]); i++; }
      const headers = tl[0].split('|').filter(c => c.trim() !== '');
      const rows = tl.slice(2).map(r => r.split('|').filter(c => c.trim() !== ''));
      result.push(
        <div key={`t-${i}`} className="md-table-wrap">
          <table className="md-table">
            <thead><tr>{headers.map((h,hi) => <th key={hi}>{parseInline(h.trim())}</th>)}</tr></thead>
            <tbody>{rows.map((row,ri) => <tr key={ri}>{row.map((cell,ci) => <td key={ci}>{parseInline(cell.trim())}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    const li = line.match(/^[-*]\s+(.*)/);
    if (li) { result.push(<li key={i} className="md-li">{parseInline(li[1])}</li>); i++; continue; }
    if (line.trim() === '') { result.push(<div key={i} className="md-gap"/>); i++; continue; }
    result.push(<p key={i} className="md-p">{parseInline(line)}</p>);
    i++;
  }
  return result;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button className="action-btn" onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }} title="복사">
      {copied
        ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
        : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      }
    </button>
  );
}

export default function ChatArea({ convId, messages, onMessagesUpdate, onNeedConv, onConvCreated }: Props) {
  const [input, setInput]               = useState('');
  const [loading, setLoading]           = useState(false);
  const [thinkSecs, setThinkSecs]       = useState(0);
  const [lastThinkSecs, setLastThinkSecs] = useState<number | null>(null);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const isEmpty     = messages.length === 0 && !loading;

  useEffect(() => {
    setInput('');
    setLastThinkSecs(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [convId]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  useEffect(() => {
    if (loading) {
      setThinkSecs(0);
      timerRef.current = setInterval(() => setThinkSecs(s => s + 1), 1000);
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
      if (thinkSecs > 0) setLastThinkSecs(thinkSecs);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  const callAgent = useCallback(async (userContent: string, optimisticMessages: Message[], targetConvId: string) => {
    setLoading(true);
    try {
      const reply = await sendConvMessage(targetConvId, userContent);
      const next = [...optimisticMessages, { role: 'assistant' as const, content: reply }];
      onMessagesUpdate(next);
      if (optimisticMessages.length === 1) {
        const title = userContent.slice(0, 30) + (userContent.length > 30 ? '...' : '');
        renameConversation(targetConvId, title).catch(() => {});
      }
    } catch {
      onMessagesUpdate([...optimisticMessages, { role: 'assistant', content: '오류가 발생했습니다. 서버를 확인해주세요.' }]);
    } finally {
      setLoading(false);
    }
  }, [onMessagesUpdate]);

  const handleSubmit = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    // 대화 없으면 자동 생성
    let targetId = convId;
    if (!targetId) {
      targetId = await onNeedConv();
      onConvCreated(targetId);
    }

    const optimistic: Message[] = [...messages, { role: 'user', content: text }];
    onMessagesUpdate(optimistic);
    await callAgent(text, optimistic, targetId);
  };

  const handleExampleClick = async (text: string) => {
    if (loading) return;

    let targetId = convId;
    if (!targetId) {
      targetId = await onNeedConv();
      onConvCreated(targetId);
    }

    const optimistic: Message[] = [...messages, { role: 'user', content: text }];
    onMessagesUpdate(optimistic);
    await callAgent(text, optimistic, targetId);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; }
  };

  const inputBox = (
    <div className="input-box">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="메시지를 입력하세요 (Shift+Enter: 줄바꿈)"
        rows={1}
        disabled={loading}
      />
      <button className="send-btn" onClick={handleSubmit} disabled={!input.trim() || loading}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
        </svg>
      </button>
    </div>
  );

  // 웰컴 화면 (convId 없거나 메시지 없을 때)
  if (isEmpty) {
    return (
      <main className="chat-area">
        <div className="centered-welcome">
          <h2>무엇을 도와드릴까요?</h2>
          <div className="example-prompts">
            <button onClick={() => handleExampleClick('철골 세우기 인건비 산출해줘')}>철골 세우기 인건비 산출</button>
            <button onClick={() => handleExampleClick('콘크리트 타설 인건비 얼마야?')}>콘크리트 타설 인건비</button>
            <button onClick={() => handleExampleClick('거푸집 설치 인건비 산출해줘')}>거푸집 설치 인건비</button>
          </div>
          <div className="centered-input-area">{inputBox}</div>
        </div>
      </main>
    );
  }

  const lastAssistantIdx = messages.map(m => m.role).lastIndexOf('assistant');

  return (
    <main className="chat-area">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'user' ? (
              <div className="user-bubble">{msg.content}</div>
            ) : (
              <div className="assistant-body">
                {i === lastAssistantIdx && lastThinkSecs !== null && (
                  <div className="think-label">{lastThinkSecs}초 동안 생각함</div>
                )}
                <div className="assistant-text">{renderMarkdown(msg.content)}</div>
                <div className="action-bar"><CopyButton text={msg.content}/></div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="loading-indicator">
              <svg width="26" height="20" viewBox="0 0 40 30" fill="none">
                <rect className="brick b1" x="0"  y="22" width="11" height="7" rx="1.5" fill="#3a7d44"/>
                <rect className="brick b2" x="13" y="22" width="11" height="7" rx="1.5" fill="#3a7d44"/>
                <rect className="brick b3" x="26" y="22" width="11" height="7" rx="1.5" fill="#3a7d44"/>
                <rect className="brick b4" x="6"  y="14" width="11" height="7" rx="1.5" fill="#2e6436"/>
                <rect className="brick b5" x="20" y="14" width="11" height="7" rx="1.5" fill="#2e6436"/>
                <rect className="brick b6" x="13" y="6"  width="11" height="7" rx="1.5" fill="#14532d"/>
              </svg>
              <span className="think-label animate">{thinkSecs}초 동안 생각 중...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef}/>
      </div>
      <div className="input-area">{inputBox}</div>
    </main>
  );
}

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { Message, AgentType } from '../types';
import { sendConvMessage, renameConversation } from '../api';
import './ChatArea.css';

const NEAR_BOTTOM_PX = 120;
const SHOW_SCROLL_BUTTON_PX = 160;

interface Props {
  convId: string | null;
  canWrite: boolean;
  messages: Message[];
  onMessagesUpdate: (messages: Message[]) => void;
  onNeedConv: () => Promise<string>;
  onConvCreated: (id: string) => void;
}

// ── 에이전트 메타 ──────────────────────────────
const AGENT_META: Record<AgentType, { label: string; color: string }> = {
  weather:   { label: '날씨 에이전트',  color: '#2563eb' },
  labor:     { label: '인건비 에이전트', color: '#16a34a' },
  equipment: { label: '장비 에이전트',  color: '#d97706' },
  material:  { label: '자재 에이전트',  color: '#7c3aed' },
  synthesize: { label: '종합 분석',     color: '#0891b2' },
  router:    { label: '라우터',         color: '#64748b' },
};

// ── Markdown 렌더러 ────────────────────────────
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
    const bq = line.match(/^>\s+(.*)/);
    if (bq) { result.push(<blockquote key={i} className="md-bq">{parseInline(bq[1])}</blockquote>); i++; continue; }
    if (line.trim() === '') { result.push(<div key={i} className="md-gap"/>); i++; continue; }
    result.push(<p key={i} className="md-p">{parseInline(line)}</p>);
    i++;
  }
  return result;
}

function formatTime(iso: string | undefined | null): string {
  if (!iso) return '';
  // 타임존 정보 없는 UTC 문자열은 'Z'를 붙여 UTC로 해석 (없으면 브라우저가 로컬 시간으로 오해석)
  const hasTimezone = iso.endsWith('Z') || /T.*[+-]/.test(iso);
  const normalized = hasTimezone ? iso : iso + 'Z';
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return '';
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (isToday) return time;
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${time}`;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="action-btn"
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      title="복사"
    >
      {copied
        ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
        : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      }
    </button>
  );
}

// ── 에이전트 카드 아이콘 ───────────────────────
function WeatherIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
    </svg>
  );
}
function LaborIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
      <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
    </svg>
  );
}
function EquipmentIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
    </svg>
  );
}
function MaterialIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
      <line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  );
}

const AGENT_CARDS = [
  {
    type: 'weather' as AgentType,
    title: '날씨 리스크',
    desc: '기상 조건이 공사에 미치는 영향 분석',
    prompt: '이번 주 현장 기상 리스크 분석해줘',
    Icon: WeatherIcon,
    accent: '#dbeafe',
    iconColor: '#2563eb',
  },
  {
    type: 'labor' as AgentType,
    title: '인건비 산출',
    desc: '표준품셈 기반 직접노무비 산출',
    prompt: '철골 세우기 인건비 산출해줘',
    Icon: LaborIcon,
    accent: '#dcfce7',
    iconColor: '#16a34a',
  },
  {
    type: 'equipment' as AgentType,
    title: '장비 현황',
    desc: '장비 가용성 및 비용 리스크 분석',
    prompt: '타워크레인 점검 현황과 비용 알려줘',
    Icon: EquipmentIcon,
    accent: '#fef3c7',
    iconColor: '#d97706',
  },
  {
    type: 'material' as AgentType,
    title: '자재 가격',
    desc: '건설 자재 시세 및 조달 리스크',
    prompt: '철근 현재 시세와 조달 리스크 알려줘',
    Icon: MaterialIcon,
    accent: '#ede9fe',
    iconColor: '#7c3aed',
  },
];

// ── 메인 컴포넌트 ──────────────────────────────
export default function ChatArea({ convId, canWrite, messages, onMessagesUpdate, onNeedConv, onConvCreated }: Props) {
  const [input, setInput]                 = useState('');
  const [loading, setLoading]             = useState(false);
  const [thinkSecs, setThinkSecs]         = useState(0);
  const [lastThinkSecs, setLastThinkSecs] = useState<number | null>(null);
  const [isNearBottom, setIsNearBottom]   = useState(true);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const bottomRef      = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);
  const timerRef       = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef       = useRef<AbortController | null>(null);
  const thinkSecsRef = useRef(0);
  const isNearBottomRef = useRef(true);
  const forceScrollNextRef = useRef(false);
  const pendingInitialScrollRef = useRef(true);
  const isEmpty     = messages.length === 0 && !loading;

  const updateScrollState = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nextIsNearBottom = distanceFromBottom < NEAR_BOTTOM_PX;
    isNearBottomRef.current = nextIsNearBottom;
    setIsNearBottom(nextIsNearBottom);
    setShowScrollBtn(distanceFromBottom > SHOW_SCROLL_BUTTON_PX);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    isNearBottomRef.current = true;
    setIsNearBottom(true);
    setShowScrollBtn(false);
    bottomRef.current?.scrollIntoView({ behavior, block: 'end' });
  }, []);

  useEffect(() => {
    setInput('');
    setLastThinkSecs(null);
    setIsNearBottom(true);
    setShowScrollBtn(false);
    isNearBottomRef.current = true;
    pendingInitialScrollRef.current = true;
    forceScrollNextRef.current = true;
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [convId]);

  useEffect(() => {
    if (pendingInitialScrollRef.current) {
      pendingInitialScrollRef.current = false;
      requestAnimationFrame(() => scrollToBottom('auto'));
      return;
    }

    if (forceScrollNextRef.current || isNearBottomRef.current) {
      forceScrollNextRef.current = false;
      requestAnimationFrame(() => scrollToBottom('smooth'));
      return;
    }

    updateScrollState();
  }, [messages.length, loading, scrollToBottom, updateScrollState]);

  useEffect(() => {
    if (loading) {
      thinkSecsRef.current = 0;
      setThinkSecs(0);
      timerRef.current = setInterval(() => {
        setThinkSecs(s => {
          const next = s + 1;
          thinkSecsRef.current = next;
          return next;
        });
      }, 1000);
    } else {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
      if (thinkSecsRef.current > 0) setLastThinkSecs(thinkSecsRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  const makeOptimisticMsg = (role: 'user' | 'assistant', content: string, targetConvId: string): Message => ({
    id: uuidv4(),
    conversation_id: targetConvId,
    role,
    content,
    agent: null,
    created_at: new Date().toISOString(),
  });

  const callAgent = useCallback(async (userContent: string, optimisticMessages: Message[], targetConvId: string) => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    try {
      const reply = await sendConvMessage(targetConvId, userContent, ctrl.signal);
      onMessagesUpdate([...optimisticMessages, reply]);
      if (optimisticMessages.length === 1) {
        const title = userContent.slice(0, 30) + (userContent.length > 30 ? '...' : '');
        renameConversation(targetConvId, title).catch(() => {});
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // 사용자가 중단함 — 낙관적 메시지만 남기고 에러 표시 안 함
      } else {
        const errMsg = makeOptimisticMsg('assistant', '오류가 발생했습니다. 서버를 확인해주세요.', targetConvId);
        onMessagesUpdate([...optimisticMessages, errMsg]);
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [onMessagesUpdate]);

  const handleRegenerate = useCallback(async () => {
    if (loading || !convId) return;
    const lastAIdx = messages.map(m => m.role).lastIndexOf('assistant');
    if (lastAIdx < 0) return;
    const lastUserMsg = messages.slice(0, lastAIdx).reverse().find(m => m.role === 'user');
    if (!lastUserMsg) return;
    const trimmed = messages.slice(0, lastAIdx);
    onMessagesUpdate(trimmed);
    await callAgent(lastUserMsg.content, trimmed, convId);
  }, [loading, convId, messages, callAgent, onMessagesUpdate]);

  const handleSubmit = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    let targetId = convId;
    if (!targetId) {
      targetId = await onNeedConv();
      onConvCreated(targetId);
    }

    const optimistic: Message[] = [...messages, makeOptimisticMsg('user', text, targetId)];
    forceScrollNextRef.current = true;
    onMessagesUpdate(optimistic);
    await callAgent(text, optimistic, targetId);
  };

  const handleExampleClick = async (text: string) => {
    if (loading || !canWrite) return;

    let targetId = convId;
    if (!targetId) {
      targetId = await onNeedConv();
      onConvCreated(targetId);
    }

    const optimistic: Message[] = [...messages, makeOptimisticMsg('user', text, targetId)];
    forceScrollNextRef.current = true;
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

  const inputBox = canWrite ? (
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
  ) : (
    <div className="readonly-notice">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
      이 대화는 읽기 전용입니다. 대화 작성자만 메시지를 보낼 수 있습니다.
    </div>
  );

  // ── 웰컴 화면 ────────────────────────────────
  if (isEmpty) {
    // 대화가 선택된 상태에서 메시지가 없을 때 — 간결한 빈 채팅 화면
    if (convId) {
      return (
        <main className="chat-area">
          <div className="centered-welcome">
            <div className="welcome-header">
              <p className="welcome-subtitle">메시지를 입력해 대화를 시작하세요</p>
            </div>
            <div className="centered-input-area">{inputBox}</div>
          </div>
        </main>
      );
    }

    // 아무 대화도 선택 안 된 초기 화면
    return (
      <main className="chat-area">
        <div className="centered-welcome">
          <div className="welcome-header">
            <div className="welcome-logo">
              Civil<span>.AI</span>
            </div>
            <h2>무엇을 도와드릴까요?</h2>
            <p className="welcome-subtitle">건설 현장 리스크를 AI로 분석합니다</p>
          </div>

          <div className="agent-cards">
            {AGENT_CARDS.map(({ type, title, desc, prompt, Icon, accent, iconColor }) => (
              <button
                key={type}
                className="agent-card"
                onClick={() => handleExampleClick(prompt)}
                style={{ '--card-accent': accent, '--card-icon-color': iconColor } as React.CSSProperties}
              >
                <div className="agent-card-icon">
                  <Icon />
                </div>
                <div className="agent-card-content">
                  <span className="agent-card-title">{title}</span>
                  <span className="agent-card-desc">{desc}</span>
                </div>
              </button>
            ))}
          </div>

          <div className="centered-input-area">{inputBox}</div>
        </div>
      </main>
    );
  }

  const lastAssistantIdx = messages.map(m => m.role).lastIndexOf('assistant');

  return (
    <main className="chat-area">
      <div className="messages-wrap">
        <div className="messages" ref={messagesContainerRef} onScroll={updateScrollState}>
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="user-msg-wrap">
                  <div className="user-bubble">{msg.content}</div>
                  <span className="msg-time user-time">{formatTime(msg.created_at)}</span>
                </div>
              ) : (
                <div className="assistant-body">
                  {msg.agent && (
                    <div className="agent-badge" style={{ color: AGENT_META[msg.agent].color }}>
                      <span className="agent-badge-dot" style={{ background: AGENT_META[msg.agent].color }}/>
                      {AGENT_META[msg.agent].label}
                    </div>
                  )}
                  {i === lastAssistantIdx && lastThinkSecs !== null && (
                    <div className="think-label">{lastThinkSecs}초 동안 생각함</div>
                  )}
                  <div className="assistant-text">{renderMarkdown(msg.content)}</div>
                  <div className="action-bar">
                    <CopyButton text={msg.content}/>
                    {i === lastAssistantIdx && !loading && canWrite && (
                      <button className="action-btn" onClick={handleRegenerate} title="재생성">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="1 4 1 10 7 10"/>
                          <path d="M3.51 15a9 9 0 1 0 .49-4.5"/>
                        </svg>
                      </button>
                    )}
                    <span className="msg-time">{formatTime(msg.created_at)}</span>
                  </div>
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
                <button className="stop-btn" onClick={() => abortRef.current?.abort()} title="생성 중단">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                  </svg>
                  중단
                </button>
              </div>
            </div>
          )}
          <div ref={bottomRef}/>
        </div>

        {showScrollBtn && !isNearBottom && (
          <button className="scroll-bottom-btn" onClick={() => scrollToBottom('smooth')} title="최신 대화로 이동">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
        )}
      </div>
      <div className="input-area">{inputBox}</div>
    </main>
  );
}

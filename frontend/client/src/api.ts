import { Project, Conversation, Message } from './types';
import { MOCK_MODE, mockSendMessage } from './mockData';

const BASE = '';

// ══════════════════════════════
// Quick conversations (프로젝트 없는 일반 대화)
// ══════════════════════════════
export async function fetchQuickConversations(): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/conversations/quick`);
  if (!res.ok) throw new Error(`fetchQuickConversations: ${res.status}`);
  return res.json();
}

export async function createQuickConversation(title = '새 대화'): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations/quick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`createQuickConversation: ${res.status}`);
  return res.json();
}

// ══════════════════════════════
// Projects
// ══════════════════════════════
export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${BASE}/projects`);
  if (!res.ok) throw new Error(`fetchProjects: ${res.status}`);
  return res.json();
}

export async function createProject(name: string, description = ''): Promise<Project> {
  const res = await fetch(`${BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error(`createProject: ${res.status}`);
  return res.json();
}

export async function deleteProject(projectId: string): Promise<void> {
  await fetch(`${BASE}/projects/${projectId}`, { method: 'DELETE' });
}

// ══════════════════════════════
// Project conversations
// ══════════════════════════════
export async function fetchConversations(projectId: string): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/projects/${projectId}/conversations`);
  if (!res.ok) throw new Error(`fetchConversations: ${res.status}`);
  return res.json();
}

export async function createConversation(projectId: string, title = '새 대화'): Promise<Conversation> {
  const res = await fetch(`${BASE}/projects/${projectId}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`createConversation: ${res.status}`);
  return res.json();
}

export async function renameConversation(convId: string, title: string): Promise<void> {
  if (MOCK_MODE) return;
  await fetch(`${BASE}/conversations/${convId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(convId: string): Promise<void> {
  if (MOCK_MODE) return;
  await fetch(`${BASE}/conversations/${convId}`, { method: 'DELETE' });
}

// ══════════════════════════════
// Messages / Chat
// ══════════════════════════════
export async function fetchMessages(convId: string): Promise<Message[]> {
  const res = await fetch(`${BASE}/conversations/${convId}/messages`);
  if (!res.ok) throw new Error(`fetchMessages: ${res.status}`);
  return res.json();
}

export async function sendConvMessage(convId: string, content: string): Promise<Message> {
  if (MOCK_MODE) {
    return mockSendMessage(convId, content);
  }
  const res = await fetch(`${BASE}/conversations/${convId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`sendConvMessage: ${res.status}`);
  const data = await res.json();
  return { role: 'assistant', content: data.content as string };
}

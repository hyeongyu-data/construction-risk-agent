import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import { Project, Conversation, Message } from './types';
import {
  fetchQuickConversations, createQuickConversation,
  fetchProjects, createProject, deleteProject,
  fetchConversations, createConversation, deleteConversation,
  fetchMessages,
} from './api';
import {
  MOCK_MODE,
  MOCK_PROJECTS, MOCK_QUICK_CONVS, MOCK_PROJECT_CONVS, MOCK_MESSAGES,
  createMockConversation,
} from './mockData';
import './App.css';

export default function App() {
  const [quickConvs, setQuickConvs]           = useState<Conversation[]>([]);
  const [projects, setProjects]               = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [projectConvs, setProjectConvs]       = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId]       = useState<string | null>(null);
  const [messages, setMessages]               = useState<Message[]>([]);
  const [sidebarOpen, setSidebarOpen]         = useState(true);
  const [showOpenBtn, setShowOpenBtn]         = useState(false);

  const activeConvIdRef = useRef<string | null>(null);
  useEffect(() => { activeConvIdRef.current = activeConvId; }, [activeConvId]);

  useEffect(() => {
    if (MOCK_MODE) {
      setQuickConvs(MOCK_QUICK_CONVS);
      setProjects(MOCK_PROJECTS);
      return;
    }
    fetchQuickConversations().then(setQuickConvs).catch(console.error);
    fetchProjects().then(setProjects).catch(console.error);
  }, []);

  useEffect(() => {
    if (!activeProjectId) { setProjectConvs([]); return; }
    if (MOCK_MODE) {
      setProjectConvs(MOCK_PROJECT_CONVS[activeProjectId] ?? []);
      return;
    }
    fetchConversations(activeProjectId).then(setProjectConvs).catch(console.error);
  }, [activeProjectId]);

  useEffect(() => {
    if (!activeConvId) { setMessages([]); return; }
    if (MOCK_MODE) {
      setMessages(MOCK_MESSAGES[activeConvId] ?? []);
      return;
    }
    fetchMessages(activeConvId).then(setMessages).catch(console.error);
  }, [activeConvId]);

  const handleNeedConv = useCallback(async (): Promise<string> => {
    if (MOCK_MODE) {
      const conv = createMockConversation();
      setQuickConvs(prev => [conv, ...prev]);
      setActiveConvId(conv.id);
      activeConvIdRef.current = conv.id;
      return conv.id;
    }
    const conv = await createQuickConversation();
    setQuickConvs(prev => [conv, ...prev]);
    setActiveConvId(conv.id);
    activeConvIdRef.current = conv.id;
    return conv.id;
  }, []);

  const handleQuickNew = useCallback(async () => {
    if (MOCK_MODE) {
      const conv = createMockConversation();
      setQuickConvs(prev => [conv, ...prev]);
      setActiveProjectId(null);
      setActiveConvId(conv.id);
      setMessages([]);
      return;
    }
    const conv = await createQuickConversation();
    setQuickConvs(prev => [conv, ...prev]);
    setActiveProjectId(null);
    setActiveConvId(conv.id);
    setMessages([]);
  }, []);

  const handleQuickDelete = useCallback(async (convId: string) => {
    await deleteConversation(convId);
    setQuickConvs(prev => prev.filter(c => c.id !== convId));
    if (activeConvIdRef.current === convId) { setActiveConvId(null); setMessages([]); }
  }, []);

  const handleCreateProject = useCallback(async (name: string, description = '') => {
    if (MOCK_MODE) {
      const proj: Project = {
        id: `p-${Date.now()}`,
        name,
        description,
        created_at: new Date().toISOString(),
      };
      setProjects(prev => [proj, ...prev]);
      setActiveProjectId(proj.id);
      return;
    }
    const proj = await createProject(name, description);
    setProjects(prev => [proj, ...prev]);
    setActiveProjectId(proj.id);
  }, []);

  const handleDeleteProject = useCallback(async (projectId: string) => {
    await deleteProject(projectId);
    setProjects(prev => prev.filter(p => p.id !== projectId));
    if (activeProjectId === projectId) {
      setActiveProjectId(null);
      setProjectConvs([]);
      if (activeConvIdRef.current) { setActiveConvId(null); setMessages([]); }
    }
  }, [activeProjectId]);

  const handleCreateProjectConv = useCallback(async () => {
    if (!activeProjectId) return;
    if (MOCK_MODE) {
      const conv = createMockConversation(activeProjectId);
      setProjectConvs(prev => [conv, ...prev]);
      setActiveConvId(conv.id);
      setMessages([]);
      return;
    }
    const conv = await createConversation(activeProjectId);
    setProjectConvs(prev => [conv, ...prev]);
    setActiveConvId(conv.id);
    setMessages([]);
  }, [activeProjectId]);

  const handleDeleteProjectConv = useCallback(async (convId: string) => {
    await deleteConversation(convId);
    setProjectConvs(prev => prev.filter(c => c.id !== convId));
    if (activeConvIdRef.current === convId) { setActiveConvId(null); setMessages([]); }
  }, []);

  const handleMessagesUpdate = useCallback((newMessages: Message[]) => {
    setMessages(newMessages);
    const cid = activeConvIdRef.current;
    if (!cid) return;
    const firstUser = newMessages.find(m => m.role === 'user');
    if (!firstUser) return;
    const title = firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '');
    setQuickConvs(prev => prev.map(c => c.id === cid ? { ...c, title } : c));
    setProjectConvs(prev => prev.map(c => c.id === cid ? { ...c, title } : c));
  }, []);

  const handleSelectConv = useCallback((id: string) => {
    setActiveConvId(id);
  }, []);

  const closeSidebar = () => { setSidebarOpen(false); setTimeout(() => setShowOpenBtn(true), 250); };
  const openSidebar  = () => { setShowOpenBtn(false); setSidebarOpen(true); };

  return (
    <div className="app">
      {showOpenBtn && (
        <button className="sidebar-open-btn" onClick={openSidebar} title="사이드바 열기">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
      )}

      <Sidebar
        quickConvs={quickConvs}
        projects={projects}
        activeProjectId={activeProjectId}
        projectConvs={projectConvs}
        activeConvId={activeConvId}
        onQuickNew={handleQuickNew}
        onQuickDelete={handleQuickDelete}
        onSelectConversation={handleSelectConv}
        onSelectProject={(id) => setActiveProjectId(id === activeProjectId ? null : id)}
        onCreateProject={handleCreateProject}
        onDeleteProject={handleDeleteProject}
        onCreateProjectConv={handleCreateProjectConv}
        onDeleteProjectConv={handleDeleteProjectConv}
        onClose={closeSidebar}
        isOpen={sidebarOpen}
      />

      <ChatArea
        convId={activeConvId}
        messages={messages}
        onMessagesUpdate={handleMessagesUpdate}
        onNeedConv={handleNeedConv}
        onConvCreated={handleSelectConv}
      />
    </div>
  );
}

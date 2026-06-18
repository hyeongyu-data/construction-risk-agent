import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import LoginPage from './components/LoginPage';
import ToastContainer from './components/ToastContainer';
import { User, Project, Conversation, Message, ProjectCreateRequest, ProjectRole } from './types';
import {
  fetchQuickConversations, createQuickConversation,
  fetchProjects, createProject, deleteProject,
  fetchConversations, createConversation, deleteConversation,
  fetchMessages,
  registerUnauthorizedHandler,
} from './api';
import { showToast } from './toast';
import {
  MOCK_MODE,
  MOCK_PROJECTS, MOCK_QUICK_CONVS, MOCK_PROJECT_CONVS, MOCK_MESSAGES,
  createMockConversation,
} from './mockData';
import './App.css';

export default function App() {
  const [user, setUser]                        = useState<User | null>(null);
  const [authReady, setAuthReady]              = useState(false);

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

  // ── 인증 복원 (새로고침 시) ─────────────────────────────────
  useEffect(() => {
    const storedUser  = localStorage.getItem('auth_user');
    const storedToken = localStorage.getItem('auth_token');
    if (storedUser && storedToken) {
      try { setUser(JSON.parse(storedUser)); } catch {}
    }
    setAuthReady(true);
  }, []);

  // ── 로그인 / 로그아웃 ───────────────────────────────────────
  const handleLogin = useCallback((u: User, token: string) => {
    localStorage.setItem('auth_token', token);
    localStorage.setItem('auth_user', JSON.stringify(u));
    setUser(u);
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    setUser(null);
    setQuickConvs([]);
    setProjects([]);
    setActiveProjectId(null);
    setProjectConvs([]);
    setActiveConvId(null);
    setMessages([]);
  }, []);

  // 401 발생 시 자동 로그아웃
  useEffect(() => {
    registerUnauthorizedHandler(() => {
      showToast('세션이 만료됐습니다. 다시 로그인해주세요.', 'error', 4000);
      handleLogout();
    });
  }, [handleLogout]);

  // ── 데이터 로드 ─────────────────────────────────────────────
  useEffect(() => {
    if (!user) return;
    if (MOCK_MODE) {
      setQuickConvs(
        MOCK_QUICK_CONVS.map(c => ({ ...c, can_write: c.owner_id === user.user_id }))
      );
      setProjects(
        MOCK_PROJECTS.map(p => ({
          ...p,
          my_project_role: (p.created_by === user.user_id ? 'owner' : 'member') as ProjectRole,
        }))
      );
      return;
    }
    fetchQuickConversations().then(setQuickConvs).catch(console.error);
    fetchProjects().then(setProjects).catch(console.error);
  }, [user]);

  useEffect(() => {
    if (!activeProjectId) { setProjectConvs([]); return; }
    if (MOCK_MODE) {
      const uid = user?.user_id ?? '';
      setProjectConvs(
        (MOCK_PROJECT_CONVS[activeProjectId] ?? []).map(c => ({ ...c, can_write: c.owner_id === uid }))
      );
      return;
    }
    fetchConversations(activeProjectId).then(setProjectConvs).catch(console.error);
  }, [activeProjectId, user]);

  useEffect(() => {
    if (!activeConvId) { setMessages([]); return; }
    if (MOCK_MODE) {
      setMessages(MOCK_MESSAGES[activeConvId] ?? []);
      return;
    }
    fetchMessages(activeConvId).then(setMessages).catch(console.error);
  }, [activeConvId]);

  // ── 대화 핸들러 ─────────────────────────────────────────────
  const handleNeedConv = useCallback(async (): Promise<string> => {
    if (!user) return '';
    if (MOCK_MODE) {
      const conv = createMockConversation(user.user_id, user.name);
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
  }, [user]);

  const handleQuickNew = useCallback(async () => {
    if (!user) return;
    if (MOCK_MODE) {
      const conv = createMockConversation(user.user_id, user.name);
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
  }, [user]);

  const handleQuickDelete = useCallback(async (convId: string) => {
    await deleteConversation(convId);
    setQuickConvs(prev => prev.filter(c => c.id !== convId));
    if (activeConvIdRef.current === convId) { setActiveConvId(null); setMessages([]); }
  }, []);

  const handleCreateProject = useCallback(async (req: ProjectCreateRequest) => {
    if (!user) return;
    if (MOCK_MODE) {
      const proj: Project = {
        id: `p-${Date.now()}`,
        ...req,
        work_type: '',
        latitude: 0,
        longitude: 0,
        created_by: user.user_id,
        created_by_name: user.name,
        my_project_role: 'owner',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setProjects(prev => [proj, ...prev]);
      setActiveProjectId(proj.id);
      showToast(`'${proj.name}' 프로젝트가 생성됐습니다.`, 'success');
      return;
    }
    try {
      const proj = await createProject(req);
      setProjects(prev => [proj, ...prev]);
      setActiveProjectId(proj.id);
      showToast(`'${proj.name}' 프로젝트가 생성됐습니다.`, 'success');
    } catch {
      showToast('프로젝트 생성에 실패했습니다.', 'error');
    }
  }, [user]);

  const handleDeleteProject = useCallback(async (projectId: string) => {
    try {
      await deleteProject(projectId);
      setProjects(prev => prev.filter(p => p.id !== projectId));
      if (activeProjectId === projectId) {
        setActiveProjectId(null);
        setProjectConvs([]);
        if (activeConvIdRef.current) { setActiveConvId(null); setMessages([]); }
      }
      showToast('프로젝트가 삭제됐습니다.', 'success');
    } catch {
      showToast('프로젝트 삭제에 실패했습니다.', 'error');
    }
  }, [activeProjectId]);

  const handleCreateProjectConv = useCallback(async () => {
    if (!activeProjectId || !user) return;
    if (MOCK_MODE) {
      const conv = createMockConversation(user.user_id, user.name, activeProjectId);
      setProjectConvs(prev => [conv, ...prev]);
      setActiveConvId(conv.id);
      setMessages([]);
      return;
    }
    const conv = await createConversation(activeProjectId);
    setProjectConvs(prev => [conv, ...prev]);
    setActiveConvId(conv.id);
    setMessages([]);
  }, [activeProjectId, user]);

  const handleGoHome = useCallback(() => {
    setActiveProjectId(null);
    setActiveConvId(null);
    setMessages([]);
  }, []);

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

  // ── 인증 확인 전 빈 화면 ────────────────────────────────────
  if (!authReady) return <ToastContainer />;

  // ── 비로그인 → 로그인 화면 ──────────────────────────────────
  if (!user) return <><LoginPage onLogin={handleLogin} /><ToastContainer /></>;

  // ── 로그인 후 메인 앱 ───────────────────────────────────────
  const activeConv = [...quickConvs, ...projectConvs].find(c => c.id === activeConvId) ?? null;

  return (
    <div className="app">
      <ToastContainer />
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
        user={user}
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
        onLogout={handleLogout}
        onGoHome={handleGoHome}
        isOpen={sidebarOpen}
      />

      <ChatArea
        convId={activeConvId}
        canWrite={activeConv?.can_write ?? true}
        messages={messages}
        onMessagesUpdate={handleMessagesUpdate}
        onNeedConv={handleNeedConv}
        onConvCreated={handleSelectConv}
      />
    </div>
  );
}

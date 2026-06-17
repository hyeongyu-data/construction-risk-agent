import React, { useState } from 'react';
import { Project, Conversation } from '../types';
import './Sidebar.css';

interface Props {
  quickConvs: Conversation[];
  projects: Project[];
  activeProjectId: string | null;
  projectConvs: Conversation[];
  activeConvId: string | null;
  onQuickNew: () => void;
  onQuickDelete: (id: string) => void;
  onSelectConversation: (id: string) => void;
  onSelectProject: (id: string) => void;
  onCreateProject: (name: string, description?: string) => void;
  onDeleteProject: (id: string) => void;
  onCreateProjectConv: () => void;
  onDeleteProjectConv: (id: string) => void;
  onClose: () => void;
  isOpen: boolean;
}

function ConvItem({
  conv, isActive, onSelect, onDelete,
}: {
  conv: Conversation; isActive: boolean;
  onSelect: () => void; onDelete: () => void;
}) {
  const [confirmDel, setConfirmDel] = useState(false);
  return (
    <div className="list-item-row">
      <button
        className={`conversation-item ${isActive ? 'active' : ''}`}
        onClick={onSelect}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <span className="conv-title">{conv.title}</span>
      </button>
      {confirmDel ? (
        <div className="delete-confirm">
          <button className="del-yes" onClick={() => { onDelete(); setConfirmDel(false); }}>삭제</button>
          <button className="del-no"  onClick={() => setConfirmDel(false)}>취소</button>
        </div>
      ) : (
        <button className="row-delete-btn" onClick={() => setConfirmDel(true)} title="삭제">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14H6L5 6"/>
            <path d="M10 11v6M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </button>
      )}
    </div>
  );
}

export default function Sidebar({
  quickConvs, projects, activeProjectId, projectConvs, activeConvId,
  onQuickNew, onQuickDelete, onSelectConversation,
  onSelectProject, onCreateProject, onDeleteProject,
  onCreateProjectConv, onDeleteProjectConv,
  onClose, isOpen,
}: Props) {
  const [projectsOpen, setProjectsOpen] = useState(true);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjName, setNewProjName]     = useState('');
  const [newProjDesc, setNewProjDesc]     = useState('');
  const [delProjId, setDelProjId]         = useState<string | null>(null);

  const activeProject = projects.find(p => p.id === activeProjectId) ?? null;

  const handleCreateProject = () => {
    const name = newProjName.trim();
    if (!name) return;
    onCreateProject(name, newProjDesc.trim());
    setNewProjName(''); setNewProjDesc('');
    setShowNewProject(false);
    setProjectsOpen(true);
  };

  return (
    <aside className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
      {/* ── 헤더 ── */}
      <div className="sidebar-header">
        <div className="logo-row">
          <span className="logo-text">Civil<span className="logo-ai">.AI</span></span>
          <button className="close-btn" onClick={onClose} title="사이드바 닫기">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
          </button>
        </div>
        <button className="new-chat-btn" onClick={onQuickNew}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5"  y1="12" x2="19" y2="12"/>
          </svg>
          새 대화
        </button>
      </div>

      {/* ── 프로젝트 섹션 (접기/펼치기) ── */}
      <div className="project-section">
        <div className="project-section-header">
          <button
            className="project-toggle-btn"
            onClick={() => setProjectsOpen(v => !v)}
          >
            <svg
              width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5"
              style={{ transform: projectsOpen ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
            >
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>프로젝트</span>
            {projects.length > 0 && <span className="proj-count">{projects.length}</span>}
          </button>
          <button
            className="icon-btn"
            onClick={() => { setShowNewProject(v => !v); setProjectsOpen(true); }}
            title="새 프로젝트"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5"  y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>

        {projectsOpen && (
          <div className="project-body">
            {/* 새 프로젝트 폼 */}
            {showNewProject && (
              <div className="new-project-form">
                <input
                  className="project-input"
                  placeholder="프로젝트명 (예: OO아파트 신축)"
                  value={newProjName}
                  onChange={e => setNewProjName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreateProject()}
                  autoFocus
                />
                <input
                  className="project-input"
                  placeholder="설명 (선택)"
                  value={newProjDesc}
                  onChange={e => setNewProjDesc(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreateProject()}
                />
                <div className="form-btn-row">
                  <button className="form-confirm-btn" onClick={handleCreateProject}>만들기</button>
                  <button className="form-cancel-btn" onClick={() => setShowNewProject(false)}>취소</button>
                </div>
              </div>
            )}

            {projects.length === 0 && !showNewProject && (
              <p className="empty-hint">+ 버튼으로 프로젝트를 만드세요</p>
            )}

            {/* 프로젝트 목록 */}
            {projects.map(proj => (
              <div key={proj.id}>
                <div className="list-item-row">
                  <button
                    className={`conversation-item project-item ${activeProjectId === proj.id ? 'active' : ''}`}
                    onClick={() => onSelectProject(proj.id)}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    </svg>
                    <span className="conv-title">{proj.name}</span>
                  </button>
                  {delProjId === proj.id ? (
                    <div className="delete-confirm">
                      <button className="del-yes" onClick={() => { onDeleteProject(proj.id); setDelProjId(null); }}>삭제</button>
                      <button className="del-no"  onClick={() => setDelProjId(null)}>취소</button>
                    </div>
                  ) : (
                    <button className="row-delete-btn" onClick={() => setDelProjId(proj.id)} title="삭제">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6l-1 14H6L5 6"/>
                        <path d="M10 11v6M14 11v6"/>
                        <path d="M9 6V4h6v2"/>
                      </svg>
                    </button>
                  )}
                </div>

                {/* 선택된 프로젝트의 대화 목록 (인덴트) */}
                {activeProjectId === proj.id && (
                  <div className="project-convs">
                    <button className="new-proj-conv-btn" onClick={onCreateProjectConv}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="12" y1="5" x2="12" y2="19"/>
                        <line x1="5"  y1="12" x2="19" y2="12"/>
                      </svg>
                      새 대화
                    </button>
                    {projectConvs.map(conv => (
                      <ConvItem
                        key={conv.id}
                        conv={conv}
                        isActive={activeConvId === conv.id}
                        onSelect={() => onSelectConversation(conv.id)}
                        onDelete={() => onDeleteProjectConv(conv.id)}
                      />
                    ))}
                    {projectConvs.length === 0 && (
                      <p className="empty-hint" style={{ paddingLeft: 8 }}>대화가 없습니다</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 일반 대화 목록 ── */}
      <div className="conversation-list">
        {quickConvs.length === 0 && (
          <p className="empty-hint">새 대화 버튼으로 시작하세요</p>
        )}
        {quickConvs.map(conv => (
          <ConvItem
            key={conv.id}
            conv={conv}
            isActive={activeConvId === conv.id}
            onSelect={() => onSelectConversation(conv.id)}
            onDelete={() => onQuickDelete(conv.id)}
          />
        ))}
      </div>

      <div className="sidebar-footer">
        <p className="footer-note">표준품셈 기반 직접노무비 산출</p>
      </div>
    </aside>
  );
}

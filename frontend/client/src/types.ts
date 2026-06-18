export type AgentType = 'weather' | 'labor' | 'equipment' | 'material' | 'synthesize' | 'router';
export type UserRole = 'admin' | 'user';
export type ProjectRole = 'owner' | 'member';
export type Visibility = 'private' | 'project_shared';

export interface User {
  user_id: string;
  name: string;
  email: string;
  role: UserRole;
}

export interface AuthResponse extends User {
  token: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  agent?: AgentType | null;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  site_name: string;
  address: string;
  latitude: number;
  longitude: number;
  work_type: string;
  start_date: string;
  end_date: string;
  description: string;
  created_by: string;
  created_by_name: string;
  my_project_role: ProjectRole;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  site_name: string;
  address: string;
  start_date: string;
  end_date: string;
  description: string;
}

export interface ProjectMember {
  user_id: string;
  name: string;
  email: string;
  project_role: ProjectRole;
}

export interface Conversation {
  id: string;
  project_id: string | null;
  owner_id: string;
  owner_name: string;
  title: string;
  visibility: Visibility;
  can_write: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
}

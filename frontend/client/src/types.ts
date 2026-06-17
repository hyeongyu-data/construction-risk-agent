export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
}

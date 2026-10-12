export interface KnowledgeBase {
  id: number;
  name: string;
  description?: string | null;
  vector_store_type: string;
  created_at: string;
}

export interface Category {
  id: number;
  knowledge_base_id: number;
  name: string;
  description?: string | null;
  parent_id?: number | null;
}

export interface DocumentItem {
  id: number;
  knowledge_base_id: number;
  category_id?: number | null;
  category_name?: string | null;
  filename: string;
  file_type: string;
  status: string;
  classify_status: string;
  classify_confidence: number;
  classify_reason?: string | null;
  chunk_count: number;
  created_at: string;
}

export interface Conversation {
  id: number;
  knowledge_base_id: number;
  category_id?: number | null;
  title: string;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | string;
  content: string;
  created_at: string;
}

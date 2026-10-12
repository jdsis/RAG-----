import axios from "axios";
import type { Category, Conversation, DocumentItem, KnowledgeBase, Message } from "./types";

export const http = axios.create({
  baseURL: "/api",
  timeout: 120000
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export function login(username: string, password: string) {
  return http.post<{ access_token: string }>("/auth/login", { username, password });
}

export function register(username: string, password: string) {
  return http.post<{ access_token: string }>("/auth/register", { username, password });
}

export const kbApi = {
  list: () => http.get<KnowledgeBase[]>("/knowledge-bases"),
  create: (data: { name: string; description?: string }) => http.post<KnowledgeBase>("/knowledge-bases", data),
  update: (id: number, data: { name?: string; description?: string }) => http.put<KnowledgeBase>(`/knowledge-bases/${id}`, data),
  remove: (id: number) => http.delete(`/knowledge-bases/${id}`)
};

export const categoryApi = {
  list: (knowledge_base_id: number) => http.get<Category[]>("/categories", { params: { knowledge_base_id } }),
  create: (data: { knowledge_base_id: number; name: string; description?: string; parent_id?: number | null }) =>
    http.post<Category>("/categories", data),
  update: (id: number, data: { name?: string; description?: string; parent_id?: number | null }) =>
    http.put<Category>(`/categories/${id}`, data),
  remove: (id: number) => http.delete(`/categories/${id}`)
};

export const documentApi = {
  list: (knowledge_base_id: number, category_id?: number | null) =>
    http.get<DocumentItem[]>("/documents", { params: { knowledge_base_id, category_id: category_id || undefined } }),
  upload: (form: FormData) => http.post<DocumentItem>("/documents/upload", form),
  importWeb: (data: { knowledge_base_id: number; url: string; auto_classify: boolean }) => http.post<DocumentItem>("/documents/web", data),
  changeCategory: (documentId: number, category_id: number | null) =>
    http.put<DocumentItem>(`/documents/${documentId}/category`, { category_id }),
  reparse: (documentId: number) => http.post<DocumentItem>(`/documents/${documentId}/reparse`),
  reclassify: (documentId: number) => http.post<DocumentItem>(`/documents/${documentId}/reclassify`),
  remove: (documentId: number) => http.delete(`/documents/${documentId}`)
};

export const chatApi = {
  conversations: () => http.get<Conversation[]>("/conversations"),
  messages: (conversationId: number) => http.get<Message[]>(`/conversations/${conversationId}/messages`)
};

export const adminApi = {
  users: () => http.get<any[]>("/admin/users"),
  logs: () => http.get<any[]>("/admin/qa-logs")
};

export const evaluationApi = {
  run: (data: { knowledge_base_id: number; cases: Array<{ question: string; expected_keywords: string[] }> }) =>
    http.post("/evaluations/run", data)
};

export async function streamChat(
  payload: { knowledge_base_id: number; question: string; category_id?: number | null; conversation_id?: number | null },
  onText: (text: string) => void
) {
  const token = localStorage.getItem("token");
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok || !response.body) throw new Error(`问答请求失败：${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    chunk.split("\n").forEach((line) => {
      if (line.startsWith("data:")) onText(line.replace(/^data:\s?/, ""));
    });
  }
}

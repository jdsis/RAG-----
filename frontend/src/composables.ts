import { ref } from "vue";
import { categoryApi, documentApi, kbApi } from "./api";
import type { Category, DocumentItem, KnowledgeBase } from "./types";

export function useKnowledgeData() {
  const knowledgeBases = ref<KnowledgeBase[]>([]);
  const categories = ref<Category[]>([]);
  const documents = ref<DocumentItem[]>([]);
  const selectedKbId = ref<number | null>(null);
  const loading = ref(false);

  async function loadKnowledgeBases() {
    const res = await kbApi.list();
    knowledgeBases.value = res.data;
    if (!selectedKbId.value && res.data[0]) selectedKbId.value = res.data[0].id;
  }

  async function loadCategories() {
    if (!selectedKbId.value) {
      categories.value = [];
      return;
    }
    const res = await categoryApi.list(selectedKbId.value);
    categories.value = res.data;
  }

  async function loadDocuments(categoryId?: number | null) {
    if (!selectedKbId.value) {
      documents.value = [];
      return;
    }
    const res = await documentApi.list(selectedKbId.value, categoryId);
    documents.value = res.data;
  }

  async function refreshAll() {
    loading.value = true;
    try {
      await loadKnowledgeBases();
      await Promise.all([loadCategories(), loadDocuments()]);
    } finally {
      loading.value = false;
    }
  }

  return { knowledgeBases, categories, documents, selectedKbId, loading, refreshAll, loadKnowledgeBases, loadCategories, loadDocuments };
}

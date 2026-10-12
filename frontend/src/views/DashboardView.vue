<script setup lang="ts">
import { computed, onMounted } from "vue";
import { BookOpen, Bot, FileText, FolderKanban } from "lucide-vue-next";
import { chatApi } from "../api";
import { useKnowledgeData } from "../composables";
import type { Conversation } from "../types";
import { ref } from "vue";

const { knowledgeBases, documents, loading, refreshAll } = useKnowledgeData();
const conversations = ref<Conversation[]>([]);

const readyDocs = computed(() => documents.value.filter((item) => item.status === "done" || item.status === "completed").length);
const chunks = computed(() => documents.value.reduce((sum, item) => sum + (item.chunk_count || 0), 0));
const recentDocs = computed(() => documents.value.slice(0, 5));
const recentConversations = computed(() => conversations.value.slice(0, 5));

onMounted(async () => {
  await refreshAll();
  try {
    conversations.value = (await chatApi.conversations()).data;
  } catch {
    conversations.value = [];
  }
});
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div>
        <h2 style="margin:0 0 6px">欢迎回来</h2>
        <div class="muted">今天可以继续整理资料、上传文档，或者直接发起知识库问答。</div>
      </div>
      <RouterLink to="/chat"><el-button type="primary" :icon="Bot">开始问答</el-button></RouterLink>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="icon-box"><BookOpen :size="22" /></div>
        <div><div class="muted">知识库数量</div><div class="value">{{ knowledgeBases.length }}</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box green"><FileText :size="22" /></div>
        <div><div class="muted">文档数量</div><div class="value">{{ documents.length }}</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box orange"><FolderKanban :size="22" /></div>
        <div><div class="muted">可检索文档</div><div class="value">{{ readyDocs }}</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box red"><Bot :size="22" /></div>
        <div><div class="muted">切片 / 会话</div><div class="value">{{ chunks }} / {{ conversations.length }}</div></div>
      </div>
    </div>

    <div class="grid-two">
      <section class="panel panel-pad">
        <div class="section-title">
          <h2>最近使用的知识库</h2>
          <RouterLink to="/knowledge"><el-link type="primary">查看全部</el-link></RouterLink>
        </div>
        <div v-if="knowledgeBases.length">
          <div v-for="kb in knowledgeBases.slice(0, 5)" :key="kb.id" class="list-row">
            <div>
              <strong>{{ kb.name }}</strong>
              <div class="muted">{{ kb.description || "暂无描述" }}</div>
            </div>
            <el-tag>{{ kb.vector_store_type }}</el-tag>
          </div>
        </div>
        <div v-else class="empty-state">还没有知识库，先创建一个用于上传资料。</div>
      </section>

      <section class="panel panel-pad">
        <div class="section-title">
          <h2>最近问答记录</h2>
          <RouterLink to="/chat"><el-link type="primary">继续问答</el-link></RouterLink>
        </div>
        <div v-if="recentConversations.length">
          <div v-for="item in recentConversations" :key="item.id" class="list-row">
            <strong>{{ item.title }}</strong>
            <span class="muted">{{ new Date(item.created_at).toLocaleString() }}</span>
          </div>
        </div>
        <div v-else class="empty-state">暂无会话记录。</div>
      </section>
    </div>

    <section class="panel panel-pad" style="margin-top:18px">
      <div class="section-title">
        <h2>最近文档</h2>
        <RouterLink to="/documents"><el-link type="primary">文档管理</el-link></RouterLink>
      </div>
      <el-table :data="recentDocs" empty-text="暂无文档">
        <el-table-column prop="filename" label="文档名称" min-width="220" />
        <el-table-column prop="file_type" label="类型" width="90" />
        <el-table-column prop="category_name" label="分类" width="150" />
        <el-table-column prop="chunk_count" label="切片数" width="100" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column label="上传时间" width="190">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

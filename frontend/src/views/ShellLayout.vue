<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { BookOpen, Bot, ChartNoAxesColumn, Database, FileText, LayoutDashboard, LogOut, Shield, Sparkles } from "lucide-vue-next";

const route = useRoute();
const router = useRouter();

const title = computed(() => {
  const map: Record<string, string> = {
    "/dashboard": "用户端工作台",
    "/chat": "知识库问答",
    "/knowledge": "知识库与分类",
    "/documents": "文档管理",
    "/admin": "管理端后台",
    "/evaluation": "评测统计"
  };
  return map[route.path] || "技术知识库问答系统";
});

function logout() {
  localStorage.removeItem("token");
  router.push("/login");
}

const nav = [
  { path: "/dashboard", label: "首页", icon: LayoutDashboard },
  { path: "/chat", label: "问答对话", icon: Bot },
  { path: "/knowledge", label: "知识库", icon: BookOpen },
  { path: "/documents", label: "文档管理", icon: FileText },
  { path: "/admin", label: "管理后台", icon: Shield },
  { path: "/evaluation", label: "系统评测", icon: ChartNoAxesColumn }
];
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Database :size="24" /></div>
        <div>
          <strong>知识库问答</strong>
          <span>RAG 管理系统</span>
        </div>
      </div>

      <nav class="nav-list">
        <RouterLink v-for="item in nav" :key="item.path" class="nav-item" :to="item.path">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-user">
        <span><Sparkles :size="15" /> 当前用户</span>
        <el-button circle size="small" :icon="LogOut" @click="logout" />
      </div>
    </aside>

    <main class="main-area">
      <header class="topbar">
        <h1>{{ title }}</h1>
        <div class="toolbar-actions">
          <el-tag type="success" effect="light">FastAPI / Ollama</el-tag>
          <el-button :icon="LogOut" @click="logout">退出</el-button>
        </div>
      </header>
      <section class="content">
        <RouterView />
      </section>
    </main>
  </div>
</template>

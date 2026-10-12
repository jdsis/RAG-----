import { createRouter, createWebHistory } from "vue-router";
import LoginView from "./views/LoginView.vue";
import ShellLayout from "./views/ShellLayout.vue";
import DashboardView from "./views/DashboardView.vue";
import ChatView from "./views/ChatView.vue";
import KnowledgeView from "./views/KnowledgeView.vue";
import DocumentsView from "./views/DocumentsView.vue";
import AdminView from "./views/AdminView.vue";
import EvaluationView from "./views/EvaluationView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/login", component: LoginView },
    {
      path: "/",
      component: ShellLayout,
      children: [
        { path: "dashboard", component: DashboardView },
        { path: "chat", component: ChatView },
        { path: "knowledge", component: KnowledgeView },
        { path: "documents", component: DocumentsView },
        { path: "admin", component: AdminView },
        { path: "evaluation", component: EvaluationView }
      ]
    }
  ]
});

router.beforeEach((to) => {
  const token = localStorage.getItem("token");
  if (to.path !== "/login" && !token) return "/login";
  if (to.path === "/login" && token) return "/dashboard";
  return true;
});

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { Bot, Database, FileText, Github, Lock, Search, ShieldCheck, UserRound } from "lucide-vue-next";
import { ElMessage } from "element-plus";
import { login, register } from "../api";
import hero from "../assets/ai-knowledge-hero.png";

const router = useRouter();
const mode = ref<"login" | "register">("login");
const username = ref("");
const password = ref("");
const loading = ref(false);

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    const res = mode.value === "login" ? await login(username.value, password.value) : await register(username.value, password.value);
    localStorage.setItem("token", res.data.access_token);
    ElMessage.success(mode.value === "login" ? "登录成功" : "注册成功");
    router.push("/dashboard");
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || "操作失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-frame">
      <div class="login-left">
        <div class="brand" style="padding:0">
          <div class="brand-mark"><Database :size="26" /></div>
          <div>
            <strong style="color:#101a33">技术知识库问答系统</strong>
            <span>智能检索 · 精准回答 · 知识赋能</span>
          </div>
        </div>

        <div class="login-copy">
          <h1>让知识管理<span>更简单</span><br />让问题解答<span>更智能</span></h1>
          <p class="muted">基于大模型与 RAG 技术的企业级知识库问答系统，帮助团队高效管理知识，快速获取精准答案。</p>
        </div>

        <div class="feature-list">
          <div class="feature-item">
            <div class="icon-box"><FileText :size="22" /></div>
            <div><strong>多格式文档管理</strong><div class="muted">支持 PDF、Word、Markdown、Excel 等多种格式</div></div>
          </div>
          <div class="feature-item">
            <div class="icon-box green"><Search :size="22" /></div>
            <div><strong>智能语义检索</strong><div class="muted">基于向量检索，快速定位相关知识</div></div>
          </div>
          <div class="feature-item">
            <div class="icon-box orange"><Bot :size="22" /></div>
            <div><strong>AI 智能问答</strong><div class="muted">结合本地模型，生成准确可靠的答案</div></div>
          </div>
          <div class="feature-item">
            <div class="icon-box red"><ShieldCheck :size="22" /></div>
            <div><strong>权限与数据安全</strong><div class="muted">多级权限控制，保障知识安全</div></div>
          </div>
        </div>

        <img class="hero-img" :src="hero" alt="AI knowledge base illustration" />
      </div>

      <div class="login-card">
        <h2>{{ mode === "login" ? "登录系统" : "注册账号" }}</h2>
        <p class="muted" style="text-align:center;margin:0">欢迎回来，请输入您的账号信息</p>
        <div class="login-tabs">
          <button class="login-tab" :class="{ active: mode === 'login' }" @click="mode = 'login'">账号密码登录</button>
          <button class="login-tab" :class="{ active: mode === 'register' }" @click="mode = 'register'">立即注册</button>
        </div>
        <el-form label-position="top" @submit.prevent>
          <el-form-item>
            <el-input v-model="username" size="large" placeholder="请输入用户名或邮箱" :prefix-icon="UserRound" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="password" size="large" placeholder="请输入密码" show-password type="password" :prefix-icon="Lock" />
          </el-form-item>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:22px">
            <el-checkbox checked>记住我</el-checkbox>
            <el-link type="primary">忘记密码?</el-link>
          </div>
          <el-button type="primary" size="large" style="width:100%;height:46px" :loading="loading" @click="submit">
            {{ mode === "login" ? "登录" : "注册并进入" }}
          </el-button>
          <div style="margin-top:28px;text-align:center">
            <span class="muted">其他登录方式</span>
            <div style="display:flex;justify-content:center;gap:18px;margin-top:16px">
              <el-button circle :icon="Github" />
              <el-button circle>G</el-button>
              <el-button circle type="success">微</el-button>
            </div>
          </div>
        </el-form>
      </div>
    </section>
  </main>
</template>

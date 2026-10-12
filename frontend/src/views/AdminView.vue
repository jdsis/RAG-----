<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { FileClock, UsersRound } from "lucide-vue-next";
import { adminApi } from "../api";

const users = ref<any[]>([]);
const logs = ref<any[]>([]);
const loading = ref(false);

const avgTime = computed(() => {
  if (!logs.value.length) return 0;
  return Math.round(logs.value.reduce((sum, item) => sum + (item.response_time_ms || 0), 0) / logs.value.length);
});

async function load() {
  loading.value = true;
  try {
    const [userRes, logRes] = await Promise.all([adminApi.users(), adminApi.logs()]);
    users.value = userRes.data;
    logs.value = logRes.data;
  } catch (error: any) {
    ElMessage.error(error.response?.status === 403 ? "当前账号不是管理员，无法访问管理接口" : "管理端数据加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div>
        <h2 style="margin:0 0 6px">管理端后台</h2>
        <div class="muted">查看用户、问答日志和系统运行指标。管理员账号才能访问真实数据。</div>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="icon-box"><UsersRound :size="22" /></div>
        <div><div class="muted">用户总数</div><div class="value">{{ users.length }}</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box green"><FileClock :size="22" /></div>
        <div><div class="muted">问答日志</div><div class="value">{{ logs.length }}</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box orange"><FileClock :size="22" /></div>
        <div><div class="muted">平均耗时</div><div class="value">{{ avgTime }}ms</div></div>
      </div>
      <div class="stat-card">
        <div class="icon-box red"><UsersRound :size="22" /></div>
        <div><div class="muted">管理员</div><div class="value">{{ users.filter(u => u.role === 'admin').length }}</div></div>
      </div>
    </div>

    <div class="grid-two">
      <section class="panel panel-pad">
        <div class="section-title"><h2>用户列表</h2></div>
        <el-table :data="users" empty-text="暂无用户数据">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="role" label="角色" width="110" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : "-" }}</template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel panel-pad">
        <div class="section-title"><h2>问答趋势</h2></div>
        <div style="height:260px;display:flex;align-items:end;gap:10px;padding:20px 6px 0;border-bottom:1px solid #e7edf5">
          <div
            v-for="(item, index) in logs.slice(0, 16).reverse()"
            :key="item.id || index"
            :title="item.question"
            :style="{ height: `${Math.max(18, Math.min(230, (item.response_time_ms || 300) / 12))}px` }"
            style="flex:1;border-radius:6px 6px 0 0;background:#2865ff"
          />
          <div v-if="!logs.length" class="empty-state" style="width:100%">暂无问答日志。</div>
        </div>
      </section>
    </div>

    <section class="panel panel-pad" style="margin-top:18px">
      <div class="section-title"><h2>最近问答日志</h2></div>
      <el-table :data="logs" empty-text="暂无日志">
        <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="answer" label="回答摘要" min-width="280" show-overflow-tooltip />
        <el-table-column prop="response_time_ms" label="耗时 ms" width="110" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.is_answered ? 'success' : 'warning'">{{ row.is_answered ? "已回答" : "拒答" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="时间" width="190">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

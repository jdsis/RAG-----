<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { PlayCircle } from "lucide-vue-next";
import { evaluationApi } from "../api";
import { useKnowledgeData } from "../composables";

const { knowledgeBases, selectedKbId, refreshAll } = useKnowledgeData();
const loading = ref(false);
const result = ref<any | null>(null);
const form = reactive({
  casesText: "Java 中线程池的核心参数有哪些？ | corePoolSize,maximumPoolSize\n什么是 RAG？ | 检索,生成"
});

function parseCases() {
  return form.casesText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [question, keywords = ""] = line.split("|");
      return {
        question: question.trim(),
        expected_keywords: keywords.split(",").map((item) => item.trim()).filter(Boolean)
      };
    });
}

async function run() {
  if (!selectedKbId.value) return ElMessage.warning("请先选择知识库");
  const cases = parseCases();
  if (!cases.length) return ElMessage.warning("请输入评测用例");
  loading.value = true;
  try {
    result.value = (await evaluationApi.run({ knowledge_base_id: selectedKbId.value, cases })).data;
    ElMessage.success("评测完成");
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || "评测失败");
  } finally {
    loading.value = false;
  }
}

onMounted(refreshAll);
</script>

<template>
  <div>
    <div class="toolbar">
      <div>
        <h2 style="margin:0 0 6px">简单评测模块</h2>
        <div class="muted">按“问题 | 关键词1,关键词2”的格式输入用例，统计命中率和无答案率。</div>
      </div>
      <el-select v-model="selectedKbId" placeholder="选择知识库" style="width:240px">
        <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
      </el-select>
    </div>

    <section class="panel panel-pad">
      <el-form label-position="top">
        <el-form-item label="评测用例">
          <el-input v-model="form.casesText" type="textarea" :rows="8" />
        </el-form-item>
        <el-button type="primary" :loading="loading" :icon="PlayCircle" @click="run">运行评测</el-button>
      </el-form>
    </section>

    <div v-if="result" class="stat-grid" style="margin-top:18px">
      <div class="stat-card">
        <div><div class="muted">用例总数</div><div class="value">{{ result.total }}</div></div>
      </div>
      <div class="stat-card">
        <div><div class="muted">命中率</div><div class="value">{{ Math.round(result.hit_rate * 100) }}%</div></div>
      </div>
      <div class="stat-card">
        <div><div class="muted">拒答率</div><div class="value">{{ Math.round(result.no_answer_rate * 100) }}%</div></div>
      </div>
    </div>

    <section v-if="result" class="panel panel-pad" style="margin-top:18px">
      <div class="section-title"><h2>评测结果</h2></div>
      <el-table :data="result.results">
        <el-table-column prop="question" label="问题" />
        <el-table-column label="是否命中" width="120">
          <template #default="{ row }"><el-tag :type="row.hit ? 'success' : 'danger'">{{ row.hit ? "命中" : "未命中" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="无答案" width="120">
          <template #default="{ row }"><el-tag :type="row.no_answer ? 'warning' : 'success'">{{ row.no_answer ? "是" : "否" }}</el-tag></template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

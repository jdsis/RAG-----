<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Link, RefreshCcw, Search, UploadCloud } from "lucide-vue-next";
import { documentApi } from "../api";
import { useKnowledgeData } from "../composables";
import type { DocumentItem } from "../types";

const { knowledgeBases, categories, documents, selectedKbId, loading, refreshAll, loadCategories, loadDocuments } = useKnowledgeData();
const selectedCategoryId = ref<number | null>(null);
const webDialog = ref(false);
const webUrl = ref("");
const autoClassify = ref(true);
const uploading = ref(false);

async function onUpload(options: any) {
  if (!selectedKbId.value) {
    ElMessage.warning("请先选择知识库");
    return;
  }
  uploading.value = true;
  try {
    const form = new FormData();
    form.append("knowledge_base_id", String(selectedKbId.value));
    form.append("auto_classify", String(autoClassify.value));
    form.append("file", options.file);
    await documentApi.upload(form);
    ElMessage.success("上传并解析完成");
    await loadDocuments(selectedCategoryId.value);
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function importWeb() {
  if (!selectedKbId.value || !webUrl.value.trim()) return;
  await documentApi.importWeb({ knowledge_base_id: selectedKbId.value, url: webUrl.value, auto_classify: autoClassify.value });
  ElMessage.success("网页已导入");
  webDialog.value = false;
  webUrl.value = "";
  await loadDocuments(selectedCategoryId.value);
}

async function changeCategory(row: DocumentItem, categoryId: number | null) {
  await documentApi.changeCategory(row.id, categoryId);
  ElMessage.success("分类已更新");
  await loadDocuments(selectedCategoryId.value);
}

async function reparse(row: DocumentItem) {
  await documentApi.reparse(row.id);
  ElMessage.success("重新解析完成");
  await loadDocuments(selectedCategoryId.value);
}

async function reclassify(row: DocumentItem) {
  await documentApi.reclassify(row.id);
  ElMessage.success("重新分类完成");
  await loadDocuments(selectedCategoryId.value);
}

async function removeDoc(row: DocumentItem) {
  await ElMessageBox.confirm(`确认删除文档「${row.filename}」及其向量数据吗？`, "删除确认", { type: "warning" });
  await documentApi.remove(row.id);
  ElMessage.success("已删除");
  await loadDocuments(selectedCategoryId.value);
}

function statusType(status: string) {
  if (["done", "completed", "success"].includes(status)) return "success";
  if (status === "failed") return "danger";
  return "warning";
}

watch(selectedKbId, async () => {
  selectedCategoryId.value = null;
  await loadCategories();
  await loadDocuments();
});

watch(selectedCategoryId, () => loadDocuments(selectedCategoryId.value));
onMounted(refreshAll);
</script>

<template>
  <div>
    <div class="toolbar">
      <div>
        <h2 style="margin:0 0 6px">文档管理</h2>
        <div class="muted">上传文件、导入网页、查看解析状态，并调整自动分类结果。</div>
      </div>
      <div class="toolbar-actions">
        <el-select v-model="selectedKbId" placeholder="选择知识库" style="width:220px">
          <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
        <el-select v-model="selectedCategoryId" clearable placeholder="全部分类" style="width:180px">
          <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-checkbox v-model="autoClassify">自动分类</el-checkbox>
        <el-upload :show-file-list="false" :http-request="onUpload" :disabled="uploading || !selectedKbId">
          <el-button type="primary" :loading="uploading" :icon="UploadCloud">上传文件</el-button>
        </el-upload>
        <el-button :icon="Link" @click="webDialog=true">导入网页</el-button>
      </div>
    </div>

    <section class="panel panel-pad" v-loading="loading">
      <el-table :data="documents" empty-text="暂无文档">
        <el-table-column prop="filename" label="文档名称" min-width="210" />
        <el-table-column prop="file_type" label="类型" width="76" />
        <el-table-column label="分类" min-width="150">
          <template #default="{ row }">
            <el-select :model-value="row.category_id" clearable placeholder="未分类" @change="(value:number|null)=>changeCategory(row, value || null)">
              <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="92">
          <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="切片" width="76" />
        <el-table-column label="置信度" width="88">
          <template #default="{ row }">{{ Math.round((row.classify_confidence || 0) * 100) }}%</template>
        </el-table-column>
        <el-table-column label="上传时间" width="168">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="185">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button link type="primary" :icon="RefreshCcw" @click="reparse(row)">解析</el-button>
              <el-button link type="primary" :icon="Search" @click="reclassify(row)">分类</el-button>
              <el-button link type="danger" @click="removeDoc(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="webDialog" title="导入网页资料" width="520px">
      <el-form label-position="top">
        <el-form-item label="网页 URL"><el-input v-model="webUrl" placeholder="https://example.com/article" /></el-form-item>
        <el-form-item><el-checkbox v-model="autoClassify">导入后自动分类</el-checkbox></el-form-item>
      </el-form>
      <template #footer><el-button @click="webDialog=false">取消</el-button><el-button type="primary" @click="importWeb">导入</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { BookPlus, FolderPlus, Pencil, Trash2 } from "lucide-vue-next";
import { categoryApi, kbApi } from "../api";
import { useKnowledgeData } from "../composables";
import type { Category, KnowledgeBase } from "../types";

const { knowledgeBases, categories, selectedKbId, loading, refreshAll, loadCategories } = useKnowledgeData();
const kbDialog = ref(false);
const categoryDialog = ref(false);
const editingKb = ref<KnowledgeBase | null>(null);
const editingCategory = ref<Category | null>(null);
const kbForm = reactive({ name: "", description: "" });
const categoryForm = reactive({ name: "", description: "", parent_id: null as number | null });

function openKb(item?: KnowledgeBase) {
  editingKb.value = item || null;
  kbForm.name = item?.name || "";
  kbForm.description = item?.description || "";
  kbDialog.value = true;
}

async function saveKb() {
  if (!kbForm.name.trim()) return ElMessage.warning("请输入知识库名称");
  if (editingKb.value) await kbApi.update(editingKb.value.id, kbForm);
  else await kbApi.create(kbForm);
  ElMessage.success("保存成功");
  kbDialog.value = false;
  await refreshAll();
}

async function removeKb(item: KnowledgeBase) {
  await ElMessageBox.confirm(`确认删除知识库「${item.name}」及其文档数据吗？`, "删除确认", { type: "warning" });
  await kbApi.remove(item.id);
  ElMessage.success("已删除");
  selectedKbId.value = null;
  await refreshAll();
}

function openCategory(item?: Category) {
  if (!selectedKbId.value) return ElMessage.warning("请先选择知识库");
  editingCategory.value = item || null;
  categoryForm.name = item?.name || "";
  categoryForm.description = item?.description || "";
  categoryForm.parent_id = item?.parent_id || null;
  categoryDialog.value = true;
}

async function saveCategory() {
  if (!selectedKbId.value || !categoryForm.name.trim()) return;
  if (editingCategory.value) await categoryApi.update(editingCategory.value.id, categoryForm);
  else await categoryApi.create({ knowledge_base_id: selectedKbId.value, ...categoryForm });
  ElMessage.success("分类已保存");
  categoryDialog.value = false;
  await loadCategories();
}

async function removeCategory(item: Category) {
  await ElMessageBox.confirm(`确认删除分类「${item.name}」吗？文档会转入未分类。`, "删除确认", { type: "warning" });
  await categoryApi.remove(item.id);
  ElMessage.success("已删除");
  await loadCategories();
}

watch(selectedKbId, () => loadCategories());
onMounted(refreshAll);
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <div>
        <h2 style="margin:0 0 6px">知识库与分类管理</h2>
        <div class="muted">创建知识库，维护 Java、Python、数据库等技术区域分类。</div>
      </div>
      <el-button type="primary" :icon="BookPlus" @click="openKb()">新建知识库</el-button>
    </div>

    <div class="grid-two">
      <section class="panel panel-pad">
        <div class="section-title"><h2>知识库列表</h2></div>
        <div v-if="knowledgeBases.length">
          <div v-for="kb in knowledgeBases" :key="kb.id" class="list-row">
            <div>
              <el-radio v-model="selectedKbId" :label="kb.id">
                <strong>{{ kb.name }}</strong>
              </el-radio>
              <div class="muted" style="padding-left:24px">{{ kb.description || "暂无描述" }}</div>
            </div>
            <div class="table-actions">
              <el-button size="small" :icon="Pencil" @click="openKb(kb)">编辑</el-button>
              <el-button size="small" type="danger" :icon="Trash2" @click="removeKb(kb)">删除</el-button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">暂无知识库。</div>
      </section>

      <section class="panel panel-pad">
        <div class="section-title">
          <h2>分类管理</h2>
          <el-button size="small" type="primary" :icon="FolderPlus" @click="openCategory()">新建分类</el-button>
        </div>
        <el-table :data="categories" empty-text="请选择知识库或创建分类">
          <el-table-column prop="name" label="分类名称" />
          <el-table-column prop="description" label="描述" />
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button size="small" link type="primary" @click="openCategory(row)">编辑</el-button>
                <el-button size="small" link type="danger" @click="removeCategory(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <el-dialog v-model="kbDialog" :title="editingKb ? '编辑知识库' : '新建知识库'" width="460px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="kbForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="kbForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="kbDialog=false">取消</el-button><el-button type="primary" @click="saveKb">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="categoryDialog" :title="editingCategory ? '编辑分类' : '新建分类'" width="460px">
      <el-form label-position="top">
        <el-form-item label="分类名称"><el-input v-model="categoryForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="categoryForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="categoryDialog=false">取消</el-button><el-button type="primary" @click="saveCategory">保存</el-button></template>
    </el-dialog>
  </div>
</template>

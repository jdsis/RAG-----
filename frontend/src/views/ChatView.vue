<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Bot, Plus, SendHorizontal } from "lucide-vue-next";
import { chatApi, streamChat } from "../api";
import { useKnowledgeData } from "../composables";
import type { Conversation, Message } from "../types";

const { knowledgeBases, categories, selectedKbId, refreshAll, loadCategories } = useKnowledgeData();
const conversations = ref<Conversation[]>([]);
const activeConversationId = ref<number | null>(null);
const messages = ref<Message[]>([]);
const question = ref("");
const selectedCategoryId = ref<number | null>(null);
const streaming = ref(false);
const messageBox = ref<HTMLElement | null>(null);

async function loadConversations() {
  conversations.value = (await chatApi.conversations()).data;
}

async function openConversation(item: Conversation) {
  activeConversationId.value = item.id;
  selectedKbId.value = item.knowledge_base_id;
  selectedCategoryId.value = item.category_id || null;
  messages.value = (await chatApi.messages(item.id)).data;
  await nextTick();
  messageBox.value?.scrollTo({ top: messageBox.value.scrollHeight });
}

function newChat() {
  activeConversationId.value = null;
  messages.value = [];
  question.value = "";
}

async function send() {
  if (!selectedKbId.value) return ElMessage.warning("请先选择知识库");
  if (!question.value.trim()) return;
  const text = question.value.trim();
  question.value = "";
  messages.value.push({ id: Date.now(), role: "user", content: text, created_at: new Date().toISOString() });
  const assistant: Message = { id: Date.now() + 1, role: "assistant", content: "", created_at: new Date().toISOString() };
  messages.value.push(assistant);
  streaming.value = true;
  try {
    await streamChat(
      {
        knowledge_base_id: selectedKbId.value,
        category_id: selectedCategoryId.value,
        conversation_id: activeConversationId.value,
        question: text
      },
      (chunk) => {
        assistant.content += chunk;
        nextTick(() => messageBox.value?.scrollTo({ top: messageBox.value.scrollHeight }));
      }
    );
    await loadConversations();
  } catch (error: any) {
    assistant.content += "\n\n请求失败，请确认后端、Ollama 和知识库数据是否可用。";
    ElMessage.error(error.message || "问答失败");
  } finally {
    streaming.value = false;
  }
}

watch(selectedKbId, () => loadCategories());

onMounted(async () => {
  await refreshAll();
  await loadConversations();
});
</script>

<template>
  <div class="chat-layout">
    <aside class="panel conversation-list">
      <div class="toolbar-actions" style="margin-bottom:12px">
        <el-button type="primary" :icon="Plus" style="width:100%" @click="newChat">新建对话</el-button>
      </div>
      <el-select v-model="selectedKbId" placeholder="选择知识库" style="width:100%;margin-bottom:10px">
        <el-option v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
      </el-select>
      <el-select v-model="selectedCategoryId" clearable placeholder="全部分类" style="width:100%;margin-bottom:12px">
        <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <button
        v-for="item in conversations"
        :key="item.id"
        class="conversation-item"
        :class="{ active: item.id === activeConversationId }"
        @click="openConversation(item)"
      >
        <strong>{{ item.title }}</strong>
        <div class="muted">{{ new Date(item.created_at).toLocaleString() }}</div>
      </button>
    </aside>

    <section class="panel chat-panel">
      <div ref="messageBox" class="messages">
        <div v-if="!messages.length" class="empty-state">
          <div>
            <Bot :size="42" />
            <p>选择知识库后输入问题，系统会检索私有资料并流式生成答案。</p>
          </div>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role === 'user' ? 'user' : 'assistant'">
          {{ msg.content || "正在生成..." }}
        </div>
      </div>
      <div class="chat-input">
        <el-input
          v-model="question"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入您的问题..."
          @keydown.ctrl.enter.prevent="send"
        />
        <el-button type="primary" :loading="streaming" :icon="SendHorizontal" @click="send">发送</el-button>
      </div>
    </section>
  </div>
</template>

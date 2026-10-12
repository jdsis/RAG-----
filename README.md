# 技术知识库问答系统后端

基于 FastAPI 的 RAG 技术知识库问答系统后端，当前已覆盖开发文档中的后端核心能力，并补齐了前端开发前需要的管理接口。

## 已实现能力

- 用户注册、登录、JWT 鉴权
- MySQL 结构化数据存储
- Chroma 向量数据库存储和检索
- 知识库创建、列表、编辑、删除
- 分类创建、列表、编辑、删除
- PDF、Word、Markdown、TXT、Excel、CSV 文档上传解析
- 网页 URL 抓取、解析和入库
- 文档自动分类、手动修改分类、重新解析、重新分类
- Ollama `qwen3-embedding:0.6b` 生成 chunk 向量
- Ollama `qwen3:8b` 生成 RAG 回答
- SSE 流式问答
- 引用来源返回
- 会话历史、问答日志、简单评测接口
- 管理员用户、知识库、分类、文档、问答日志、评测结果管理

## 启动

确保 MySQL 可用，并已创建 `.env`：

```text
DATABASE_URL=mysql+pymysql://root:123456@localhost:3350/rag_kb?charset=utf8mb4
OLLAMA_BASE_URL=http://localhost:11434
CHAT_MODEL=qwen3:8b
EMBEDDING_MODEL=qwen3-embedding:0.6b
CHROMA_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
JWT_SECRET_KEY=please-change-me
```

安装依赖并启动：

```bash
F:\Python\fastApiProject\Scripts\python.exe -m pip install -r requirements.txt
F:\Python\fastApiProject\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## Ollama

```bash
ollama serve
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
```

## 主要接口

```text
POST   /api/auth/register
POST   /api/auth/login
GET    /api/knowledge-bases
POST   /api/knowledge-bases
PUT    /api/knowledge-bases/{knowledge_base_id}
DELETE /api/knowledge-bases/{knowledge_base_id}
GET    /api/categories?knowledge_base_id=1
POST   /api/categories
PUT    /api/categories/{category_id}
DELETE /api/categories/{category_id}
POST   /api/documents/upload
POST   /api/documents/web
GET    /api/documents?knowledge_base_id=1
PUT    /api/documents/{document_id}/category
POST   /api/documents/{document_id}/reparse
POST   /api/documents/{document_id}/reclassify
DELETE /api/documents/{document_id}
POST   /api/chat/stream
GET    /api/conversations
GET    /api/conversations/{conversation_id}/messages
GET    /api/admin/users
POST   /api/admin/users
PUT    /api/admin/users/{user_id}
DELETE /api/admin/users/{user_id}
GET    /api/admin/knowledge-bases
PUT    /api/admin/knowledge-bases/{knowledge_base_id}
DELETE /api/admin/knowledge-bases/{knowledge_base_id}
GET    /api/admin/categories
PUT    /api/admin/categories/{category_id}
DELETE /api/admin/categories/{category_id}
GET    /api/admin/documents
POST   /api/admin/documents/{document_id}/reparse
POST   /api/admin/documents/{document_id}/reclassify
DELETE /api/admin/documents/{document_id}
GET    /api/admin/qa-logs
DELETE /api/admin/qa-logs/{log_id}
GET    /api/admin/evaluations
DELETE /api/admin/evaluations/{evaluation_id}
POST   /api/evaluations/run
```

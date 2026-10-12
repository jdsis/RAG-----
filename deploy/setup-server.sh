#!/usr/bin/env bash
# ============================================================
# RAG 知识库问答系统 — 服务器一键初始化脚本
# 适用：Alibaba Cloud Linux 3.2104 (OpenAnolis) / x86_64
# 用法：以 root 执行  bash setup-server.sh
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*"; }

APP_DIR=/opt/rag-kb

if [[ $EUID -ne 0 ]]; then
    err "请用 root 运行：sudo bash setup-server.sh"
    exit 1
fi

info "1/6 安装系统软件包（Python3.11 / MySQL / Nginx / OCR 依赖）"
dnf install -y python3.11 python3.11-devel python3.11-pip \
               gcc gcc-c++ make git nginx mysql-server \
               tesseract tesseract-langpack-chi_sim poppler-utils

info "2/6 启动 MySQL 并设为开机自启"
systemctl enable --now mysqld
sleep 3

info "3/6 创建数据库与专用用户"
DB_PASS=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
mysql -uroot <<SQL
CREATE DATABASE IF NOT EXISTS rag_kb DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'rag'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
ALTER USER 'rag'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON rag_kb.* TO 'rag'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

info "4/6 创建部署目录"
mkdir -p ${APP_DIR}/data/chroma ${APP_DIR}/data/uploads ${APP_DIR}/logs

info "5/6 准备 Python 虚拟环境"
if [[ ! -d ${APP_DIR}/venv ]]; then
    python3.11 -m venv ${APP_DIR}/venv
fi
${APP_DIR}/venv/bin/pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
${APP_DIR}/venv/bin/pip install --upgrade pip

info "6/6 基础服务就绪检查"
systemctl enable --now nginx
nginx -t
firewall-cmd --permanent --add-service=http  >/dev/null 2>&1 || true
firewall-cmd --permanent --add-service=https >/dev/null 2>&1 || true
firewall-cmd --reload >/dev/null 2>&1 || true

JWT_SECRET=$(python3.11 -c "import secrets; print(secrets.token_urlsafe(48))")

echo ""
echo "============================================================"
echo -e "${GREEN}  服务器基础环境部署完成${NC}"
echo "============================================================"
echo ""
echo "  请把下面两个值记下来，填入 ${APP_DIR}/.env ："
echo ""
echo -e "  ${YELLOW}数据库密码 (DATABASE_URL 用)：${NC}"
echo "     ${DB_PASS}"
echo ""
echo -e "  ${YELLOW}JWT 密钥 (JWT_SECRET_KEY 用)：${NC}"
echo "     ${JWT_SECRET}"
echo ""
echo "  下一步："
echo "    1) 把代码放到 ${APP_DIR}（git clone 或 scp 上传解包）"
echo "    2) 创建 ${APP_DIR}/.env（参考 deploy/.env.server 模板）"
echo "    3) 安装 Python 依赖："
echo "       ${APP_DIR}/venv/bin/pip install -r ${APP_DIR}/requirements.txt"
echo "    4) 构建前端（见部署手册第 5 节）"
echo "    5) 配置 systemd 与 Nginx（见部署手册第 6、7 节）"
echo ""
echo "  ${YELLOW}别忘了去阿里云控制台安全组放行 80 端口！${NC}"
echo ""

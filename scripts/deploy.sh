#!/bin/bash
set -e

# ============================================================
# ET_model 部署脚本 - Ubuntu / Debian
# 用法: bash scripts/deploy.sh
# ============================================================

echo "=== ET_model 部署开始 ==="

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$PROJECT_ROOT/venv"

# ── 1. 系统依赖 ────────────────────────────────────────────────
echo "[1/7] 安装系统依赖..."
sudo apt update -qq
sudo apt install -y -qq python3 python3-pip python3-venv nginx git curl

# ── 2. Python 虚拟环境 ────────────────────────────────────────
echo "[2/7] 创建 Python 虚拟环境..."
cd "$PROJECT_ROOT"
[ ! -d "$VENV" ] && python3 -m venv "$VENV"
source "$VENV/bin/activate"

echo "[2/7] 安装后端依赖..."
pip install -q --upgrade pip
pip install -q -r backend/requirements.txt

# ── 3. 前端构建 ────────────────────────────────────────────────
echo "[3/7] 安装前端依赖并构建..."
cd "$PROJECT_ROOT/frontend"
npm install -q
npm run build -q

# ── 4. Nginx 配置 ──────────────────────────────────────────────
echo "[4/7] 配置 Nginx..."
sudo tee /etc/nginx/sites-available/et_model > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;

    # 前端静态文件
    location / {
        root /var/www/et_model/dist;
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到 FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/et_model /etc/nginx/sites-enabled/et_model
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# ── 5. Systemd 服务 ────────────────────────────────────────────
echo "[5/7] 配置 systemd 服务..."
sudo tee /etc/systemd/system/et-model-api.service > /dev/null << 'SERVICE'
[Unit]
Description=ET_model FastAPI Backend
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/et_model
ExecStart=/opt/et_model/venv/bin/uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
Environment="PATH=/opt/et_model/venv/bin"

[Install]
WantedBy=multi-user.target
SERVICE

# ── 6. 复制项目到 /opt ─────────────────────────────────────────
echo "[6/7] 部署到 /opt/et_model..."
sudo mkdir -p /var/www/et_model
sudo cp -r "$PROJECT_ROOT/frontend/dist" /var/www/et_model/
sudo cp -r "$PROJECT_ROOT/backend" /opt/et_model/
sudo cp "$PROJECT_ROOT/.env" /opt/et_model/ 2>/dev/null || true
sudo cp -r "$PROJECT_ROOT/data" /opt/et_model/ 2>/dev/null || true
sudo cp -r "$PROJECT_ROOT/outputs_task_cluster" /opt/et_model/ 2>/dev/null || true
sudo cp -r "$PROJECT_ROOT/outputs_supervised_task" /opt/et_model/ 2>/dev/null || true
sudo chown -R www-data:www-data /var/www/et_model
sudo chown -R www-data:www-data /opt/et_model

# ── 7. 启动服务 ────────────────────────────────────────────────
echo "[7/7] 启动服务..."
sudo systemctl daemon-reload
sudo systemctl enable et-model-api
sudo systemctl restart et-model-api
sudo systemctl status et-model-api --no-pager

echo ""
echo "=== 部署完成 ==="
echo "访问 http://<your-server-ip> 查看前端"
echo "API 文档 http://<your-server-ip>/docs"
echo ""
echo "常用命令:"
echo "  sudo systemctl restart et-model-api  # 重启 API"
echo "  sudo systemctl status et-model-api   # 查看状态"
echo "  sudo journalctl -u et-model-api -f  # 查看日志"

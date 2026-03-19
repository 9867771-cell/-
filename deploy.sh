#!/usr/bin/env bash
#
# Codex Register 一键部署脚本
# 适用于 Ubuntu 20.04+ / Debian 11+
#
# 用法:
#   bash deploy.sh [选项]
#
# 选项:
#   --domain <域名>      指定域名（跳过交互式输入）
#   --email  <邮箱>      用于 Let's Encrypt 证书申请的邮箱
#   --port   <端口>      服务端口，默认 8000
#   --uninstall          完整卸载并清理所有组件
#   -h, --help           显示帮助信息
#
# 示例:
#   bash deploy.sh --domain example.com --email admin@example.com
#   bash deploy.sh --uninstall
#

set -euo pipefail

# ─── 常量 ───
REPO_URL="https://github.com/9867771-cell/-.git"
INSTALL_DIR="/opt/codex-register"
NGINX_CONF="/etc/nginx/sites-available/codex-register"
NGINX_LINK="/etc/nginx/sites-enabled/codex-register"
SERVICE_PORT=8000
COMPOSE_PROJECT="codex-register"

# ─── 颜色 ───
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

# ─── 日志 ───
log_info()    { echo -e "${BLUE}[信息]${NC} $*"; }
log_success() { echo -e "${GREEN}[成功]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[警告]${NC} $*"; }
log_error()   { echo -e "${RED}[错误]${NC} $*"; }

# ─── 错误捕获 ───
cleanup_on_error() {
    log_error "部署过程中发生错误（第 $1 行），请检查上方日志"
    exit 1
}
trap 'cleanup_on_error $LINENO' ERR

# ─── 帮助 ───
usage() {
    sed -n '2,20p' "$0" | sed 's/^#//; s/^ //'
}

# ─── 参数解析 ───
DOMAIN=""; EMAIL=""; UNINSTALL=false; CUSTOM_PORT=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)    DOMAIN="$2";      shift 2 ;;
        --email)     EMAIL="$2";       shift 2 ;;
        --port)      CUSTOM_PORT="$2"; shift 2 ;;
        --uninstall) UNINSTALL=true;   shift   ;;
        -h|--help)   usage; exit 0             ;;
        *) log_error "未知参数: $1"; usage; exit 1 ;;
    esac
done

[[ -n "$CUSTOM_PORT" ]] && SERVICE_PORT="$CUSTOM_PORT"

# ─── 卸载 ───
do_uninstall() {
    log_info "开始卸载 Codex Register..."

    if [[ -f "$INSTALL_DIR/docker-compose.yml" ]]; then
        log_info "停止并移除 Docker 容器..."
        cd "$INSTALL_DIR" && docker compose down -v 2>/dev/null || docker-compose down -v 2>/dev/null || true
    fi

    if [[ -f "$NGINX_LINK" ]]; then
        log_info "移除 Nginx 配置..."
        rm -f "$NGINX_LINK" "$NGINX_CONF"
        systemctl reload nginx 2>/dev/null || true
    fi

    if [[ -d "/etc/letsencrypt/live/$DOMAIN" ]] && [[ -n "$DOMAIN" ]]; then
        log_info "撤销 SSL 证书..."
        certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
    fi

    if [[ -d "$INSTALL_DIR" ]]; then
        log_info "删除项目目录 $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
    fi

    log_success "卸载完成"
}

if $UNINSTALL; then
    do_uninstall
    exit 0
fi

# ─── 检查 root ───
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用 root 用户或 sudo 运行此脚本"
        exit 1
    fi
    log_success "权限检查通过"
}

# ─── 检查操作系统 ───
check_os() {
    log_info "检测操作系统..."
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法识别操作系统，仅支持 Ubuntu 20.04+ / Debian 11+"
        exit 1
    fi
    source /etc/os-release
    case "$ID" in
        ubuntu)
            if [[ "${VERSION_ID%%.*}" -lt 20 ]]; then
                log_error "Ubuntu 版本过低（$VERSION_ID），需要 20.04+"
                exit 1
            fi ;;
        debian)
            if [[ "${VERSION_ID%%.*}" -lt 11 ]]; then
                log_error "Debian 版本过低（$VERSION_ID），需要 11+"
                exit 1
            fi ;;
        *)
            log_warn "未经测试的发行版: $ID $VERSION_ID，继续执行但不保证兼容" ;;
    esac
    log_success "操作系统: $PRETTY_NAME"
}

# ─── 安装依赖 ───
install_deps() {
    log_info "更新软件包索引..."
    apt-get update -qq

    local pkgs=(curl git ca-certificates gnupg lsb-release nginx certbot python3-certbot-nginx)
    log_info "安装基础依赖: ${pkgs[*]}"
    apt-get install -y -qq "${pkgs[@]}"
    log_success "基础依赖已安装"

    # Docker
    if command -v docker &>/dev/null; then
        log_success "Docker 已安装: $(docker --version)"
    else
        log_info "安装 Docker..."
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg

        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
$(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        systemctl enable --now docker
        log_success "Docker 安装完成: $(docker --version)"
    fi

    # Docker Compose（compose v2 插件优先）
    if docker compose version &>/dev/null; then
        log_success "Docker Compose (plugin): $(docker compose version --short)"
    elif command -v docker-compose &>/dev/null; then
        log_success "Docker Compose (standalone): $(docker-compose --version)"
    else
        log_info "安装 Docker Compose 插件..."
        apt-get install -y -qq docker-compose-plugin
        log_success "Docker Compose 插件已安装"
    fi
}

# ─── 检查端口 ───
check_ports() {
    log_info "检查端口占用..."
    local conflict=false
    for port in 80 443 "$SERVICE_PORT"; do
        if ss -tlnp | grep -q ":${port} "; then
            local proc
            proc=$(ss -tlnp | grep ":${port} " | head -1)
            # 如果是 nginx 占用 80/443 则跳过（后续会重载配置）
            if [[ "$port" =~ ^(80|443)$ ]] && echo "$proc" | grep -q "nginx"; then
                continue
            fi
            log_warn "端口 $port 已被占用: $proc"
            conflict=true
        fi
    done
    if $conflict; then
        read -rp "$(echo -e "${YELLOW}存在端口冲突，是否继续？[y/N]: ${NC}")" yn
        [[ "$yn" =~ ^[Yy]$ ]] || { log_error "用户取消部署"; exit 1; }
    else
        log_success "端口 80、443、$SERVICE_PORT 均可用"
    fi
}

# ─── 克隆项目 ───
clone_project() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log_info "项目目录已存在，拉取最新代码..."
        cd "$INSTALL_DIR" && git pull --ff-only
    else
        log_info "克隆项目到 $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
    log_success "项目代码就绪"
}

# ─── 生成 .env ───
generate_env() {
    local env_file="$INSTALL_DIR/.env"
    if [[ -f "$env_file" ]]; then
        log_info "检测到已有 .env 文件，保留现有配置"
        source "$env_file" 2>/dev/null || true
        return
    fi

    log_info "生成环境变量配置..."
    local password=""
    read -rp "$(echo -e "${BLUE}请设置 Web UI 访问密码 [默认: admin123]: ${NC}")" password
    password="${password:-admin123}"

    cat > "$env_file" <<EOF
# Codex Register 环境变量
APP_HOST=0.0.0.0
APP_PORT=${SERVICE_PORT}
APP_ACCESS_PASSWORD=${password}
PYTHONUNBUFFERED=1
EOF

    log_success ".env 配置文件已生成"
}

# ─── 获取域名 ───
ask_domain() {
    if [[ -n "$DOMAIN" ]]; then
        log_info "使用指定域名: $DOMAIN"
        return
    fi
    while true; do
        read -rp "$(echo -e "${BLUE}请输入域名（如 reg.example.com）: ${NC}")" DOMAIN
        if [[ -n "$DOMAIN" && "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]*\.)+[a-zA-Z]{2,}$ ]]; then
            break
        fi
        log_warn "域名格式不正确，请重新输入"
    done
    if [[ -z "$EMAIL" ]]; then
        read -rp "$(echo -e "${BLUE}请输入邮箱（用于 SSL 证书申请）[默认: admin@${DOMAIN}]: ${NC}")" EMAIL
        EMAIL="${EMAIL:-admin@${DOMAIN}}"
    fi
}

# ─── Nginx 反向代理 ───
setup_nginx() {
    log_info "配置 Nginx 反向代理..."

    # 移除默认站点
    rm -f /etc/nginx/sites-enabled/default

    cat > "$NGINX_CONF" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # Let's Encrypt 验证
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    # SSL 证书（certbot 申请后自动填充）
    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # 安全头
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=63072000" always;

    # 请求体大小
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:${SERVICE_PORT};
        proxy_http_version 1.1;

        # WebSocket 支持
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # 代理头
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
    }
}
NGINX

    ln -sf "$NGINX_CONF" "$NGINX_LINK"

    # 先只启用 HTTP（SSL 证书还没申请）
    # 临时注释掉 443 块，让 nginx 能启动
    local tmp_conf="$NGINX_CONF.tmp"
    sed -n '1,/^}/p' "$NGINX_CONF" > "$tmp_conf"
    cp "$NGINX_CONF" "$NGINX_CONF.full"
    mv "$tmp_conf" "$NGINX_CONF"

    nginx -t 2>/dev/null
    systemctl enable --now nginx
    systemctl reload nginx
    log_success "Nginx HTTP 配置完成"
}

# ─── SSL 证书 ───
setup_ssl() {
    log_info "申请 Let's Encrypt SSL 证书..."

    certbot certonly \
        --webroot \
        -w /var/www/html \
        -d "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --non-interactive \
        --force-renewal 2>&1 || {
            log_error "SSL 证书申请失败，请确认域名 $DOMAIN 已正确解析到本机 IP"
            log_warn "你可以稍后手动执行: certbot certonly --webroot -w /var/www/html -d $DOMAIN"
            return 1
        }

    # 恢复完整 Nginx 配置（含 HTTPS）
    if [[ -f "$NGINX_CONF.full" ]]; then
        mv "$NGINX_CONF.full" "$NGINX_CONF"
    fi

    nginx -t 2>/dev/null
    systemctl reload nginx
    log_success "SSL 证书已申请并配置完成"

    # 自动续期
    log_info "配置证书自动续期..."
    if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'") | crontab -
        log_success "已添加 certbot 自动续期定时任务（每天凌晨 3 点）"
    else
        log_success "certbot 自动续期定时任务已存在"
    fi
}

# ─── 构建并启动 ───
build_and_start() {
    cd "$INSTALL_DIR"

    log_info "检测部署方式..."
    if [[ -f "docker-compose.yml" ]] || [[ -f "docker-compose.yaml" ]] || [[ -f "compose.yml" ]]; then
        log_info "检测到 Docker Compose 配置，使用 Compose 部署"
        deploy_compose
    elif [[ -f "Dockerfile" ]]; then
        log_info "检测到 Dockerfile，使用 Docker 构建部署"
        deploy_dockerfile
    else
        log_info "未检测到容器配置，使用源码部署"
        deploy_source
    fi
}

deploy_compose() {
    cd "$INSTALL_DIR"
    log_info "构建 Docker 镜像..."
    if docker compose version &>/dev/null; then
        docker compose build --no-cache
        log_info "启动服务..."
        docker compose up -d
    else
        docker-compose build --no-cache
        log_info "启动服务..."
        docker-compose up -d
    fi

    # 等待服务就绪
    log_info "等待服务启动..."
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if curl -sf "http://127.0.0.1:${SERVICE_PORT}" >/dev/null 2>&1; then
            log_success "服务已启动"
            return
        fi
        sleep 2
        retries=$((retries - 1))
    done
    log_warn "服务可能尚未完全启动，请稍后检查"
}

deploy_dockerfile() {
    cd "$INSTALL_DIR"
    docker build -t codex-register .
    docker rm -f codex-register 2>/dev/null || true
    docker run -d \
        --name codex-register \
        --restart unless-stopped \
        -p "${SERVICE_PORT}:8000" \
        -v "$INSTALL_DIR/data:/app/data" \
        -v "$INSTALL_DIR/logs:/app/logs" \
        --env-file "$INSTALL_DIR/.env" \
        codex-register
    log_success "Docker 容器已启动"
}

deploy_source() {
    cd "$INSTALL_DIR"
    log_info "安装 Python 环境..."
    apt-get install -y -qq python3 python3-venv python3-pip
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

    cat > /etc/systemd/system/codex-register.service <<SVC
[Unit]
Description=Codex Register Web UI
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/.venv/bin/python webui.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
    systemctl daemon-reload
    systemctl enable --now codex-register
    log_success "源码部署完成，已注册为 systemd 服务"
}

# ─── 部署摘要 ───
print_summary() {
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Codex Register 部署完成${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  访问地址:  ${BLUE}https://${DOMAIN}${NC}"
    echo -e "  HTTP 地址: ${BLUE}http://${DOMAIN}${NC} (自动跳转 HTTPS)"
    echo -e "  服务端口:  ${BLUE}${SERVICE_PORT}${NC}"
    echo -e "  项目目录:  ${BLUE}${INSTALL_DIR}${NC}"
    echo -e "  配置文件:  ${BLUE}${INSTALL_DIR}/.env${NC}"
    echo -e "  Nginx:     ${BLUE}${NGINX_CONF}${NC}"
    echo ""
    echo -e "  管理命令:"
    echo -e "    查看日志:   ${YELLOW}cd $INSTALL_DIR && docker compose logs -f${NC}"
    echo -e "    重启服务:   ${YELLOW}cd $INSTALL_DIR && docker compose restart${NC}"
    echo -e "    停止服务:   ${YELLOW}cd $INSTALL_DIR && docker compose down${NC}"
    echo -e "    更新部署:   ${YELLOW}cd $INSTALL_DIR && git pull && docker compose up -d --build${NC}"
    echo -e "    完整卸载:   ${YELLOW}bash deploy.sh --uninstall${NC}"
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
}

# ═══════════════════════════════════════
#  主流程
# ═══════════════════════════════════════
main() {
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Codex Register 一键部署脚本${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
    echo ""

    check_root
    check_os
    install_deps
    check_ports
    ask_domain
    clone_project
    generate_env
    build_and_start
    setup_nginx
    setup_ssl
    print_summary
}

main
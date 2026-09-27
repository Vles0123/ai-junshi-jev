#!/bin/zsh
# Bootstrap: prepare the uv environment, then run the app under the native launcher.
set -u
export PYTHONDONTWRITEBYTECODE=1  # keep the signed app bundle immutable at runtime

RES="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/vles-chat"
CONFIG="$HOME/.config/vles-chat"
VENV="$SUPPORT/venv"
LOG="$HOME/Library/Logs/vles-chat.log"
mkdir -p "$SUPPORT" "$(dirname "$LOG")"

# Finder launches have a minimal PATH; add the usual install locations for uv
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

log() { print -r -- "[$(date '+%F %T')] $*" >> "$LOG"; }

die() {  # show a native dialog, then exit
    log "FATAL: $1"
    osascript -e "display alert \"ai 军师 jev 改进版 启动失败\" message \"$1\n\n详情: $LOG\" as critical" >/dev/null 2>&1
    exit 1
}

source "$RES/app/packaging/bootstrap_uv.sh" || die "包内缺少 uv 安装脚本，请重新下载应用"
jev_load_env "$CONFIG/env"
if ! jev_check_arch; then
    die "$JEV_ARCH_ERROR"
fi
if ! command -v uv >/dev/null 2>&1; then
    # non-blocking: a Finder launch has no terminal, and a silent multi-minute wait
    # for uv + deps is indistinguishable from "the app is broken"
    osascript -e 'display notification "首次启动：正在安装 uv（约 10 MB）" with title "ai 军师 jev 改进版"' >/dev/null 2>&1
fi
if ! jev_ensure_uv "$LOG"; then
    die "$JEV_UV_ERROR。也可手动运行 brew install uv 后重试。"
fi

export UV_PROJECT_ENVIRONMENT="$VENV"
export USE_TF=0                  # laya/transformers: skip the TensorFlow probe
export HF_HUB_DISABLE_TELEMETRY=1

# The venv must exist AND be the interpreter this bundle pins (3.12, written by
# build_app.sh). uv keeps an existing environment as-is, so a venv built by a different
# python would silently survive a rebuild — treat a mismatch like a missing venv.
log "检查运行环境（首次需要联网安装依赖）"
if [ ! -x "$VENV/bin/python" ]; then
    osascript -e 'display notification "首次启动正在安装运行环境，请保持联网；可能需要几分钟。" with title "ai 军师 jev 改进版"' >/dev/null 2>&1
fi
if ! uv sync --frozen --python "3.12" --project "$RES/app" --quiet >>"$LOG" 2>&1; then
    die "运行环境安装失败，请打开 ~/Library/Logs/vles-chat.log 查看原因后重试"
fi
"$VENV/bin/python" "$RES/app/src/vles_bootstrap.py" || die "创建配置失败，请检查用户目录权限"
log "启动 hud.py"
exec "$VENV/bin/python" "$RES/app/src/hud.py" >>"$LOG" 2>&1

"""Seed a private user config once, without overwriting existing settings."""
import os
from pathlib import Path

DEFAULT_CONFIG = '''# ai 军师 jev 改进版 — 在应用齿轮设置中填写你自己的密钥。
export JUDGE_BACKEND=zhipu
export WECHAT_READ_MODE=ax
export ZHIPU_API_KEY=''
export ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
export ZHIPU_MODEL=glm-5.3
export TYPESAFE_API_KEY=''
export TYPESAFE_BASE_URL=https://api.typesafe.ai
export TYPESAFE_MODEL=jev-latest
export OPENAI_API_KEY=''
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=''
export JEV_HISTORY=0
export JEV_CONTEXT_MESSAGES=20
export JEV_CANDIDATES_PER_TONE=1
'''


def seed(path=None):
    path = path or Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'vles-chat/env'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(DEFAULT_CONFIG)
    return True


if __name__ == '__main__':
    seed()

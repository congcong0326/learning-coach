"""本地 OpenAI 实验配置。

第一版允许在文件内配置，后续应迁移到 Settings 或凭据表。
如需放真实密钥，请创建同目录 `local_openai_config_local.py`，该文件已被 git 忽略。
"""

import os


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "replace-with-local-openai-api-key")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
OPENAI_TIMEOUT_SECONDS = 60.0

try:
    from backend.app.llm.local_openai_config_local import (  # type: ignore[import-not-found]
        OPENAI_API_KEY as LOCAL_OPENAI_API_KEY,
    )
    from backend.app.llm.local_openai_config_local import (
        OPENAI_BASE_URL as LOCAL_OPENAI_BASE_URL,
    )
    from backend.app.llm.local_openai_config_local import (
        OPENAI_MODEL as LOCAL_OPENAI_MODEL,
    )
except ImportError:
    pass
else:
    OPENAI_API_KEY = LOCAL_OPENAI_API_KEY
    OPENAI_BASE_URL = LOCAL_OPENAI_BASE_URL
    OPENAI_MODEL = LOCAL_OPENAI_MODEL

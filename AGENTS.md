# AGENTS.md

## 项目环境说明

当前项目运行在 WSL Ubuntu 环境中，主要用于 Python / AI Agent 方向的开发与实验。

本项目使用 `uv` 作为 Python 项目管理工具，负责 Python 版本管理、虚拟环境创建、依赖安装、依赖锁定和命令运行。

请优先使用 `uv` 相关命令，不要默认使用系统级 `pip` 或全局 Python 环境。

## 基础环境

- 操作系统：WSL Ubuntu
- Python 版本：Python 3.12
- Python 管理工具：uv
- 虚拟环境目录：`.venv/`
- 项目依赖配置：`pyproject.toml`
- 依赖锁定文件：`uv.lock`
- Python 版本固定文件：`.python-version`

## 依赖管理规则

运行依赖应写入 `pyproject.toml` 的项目依赖中。

添加运行依赖时使用：

```bash
uv add <package-name>

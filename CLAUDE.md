# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 FastAPI 的定时任务推送服务，接收时间和内容参数设置定时任务，到期后自动向 Bark/Day.app 推送 API 发送 GET 请求。

## 常用命令

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动服务
```bash
python main.py
```
服务运行在 `http://0.0.0.0:8000`

### Docker 部署
```bash
docker build -t scheduled-push .
docker run -d -p 8000:8000 --name push-service scheduled-push
```

## 核心 API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/schedule` | 设置定时任务 |
| GET | `/tasks` | 获取所有任务列表 |
| GET | `/tasks/{job_id}` | 获取单个任务详情 |
| DELETE | `/tasks/{job_id}` | 取消任务 |
| GET | `/health` | 健康检查 |

### 设置定时任务请求格式
```json
{
  "schedule_time": "2026-01-10T12:00:00+08:00",
  "content": "推送内容",
  "bark_key": "你的Bark Key"
}
```

## 架构说明

- **Web 框架**: FastAPI + Uvicorn
- **定时任务**: APScheduler `AsyncIOScheduler`，使用 `date` 触发器（单次执行）
- **HTTP 客户端**: httpx（异步）
- **数据验证**: Pydantic v2
- **任务存储**: 内存存储（`task_store` 字典），服务重启后任务丢失

### 应用生命周期
使用 `@asynccontextmanager` 管理的 `lifespan` 函数，在应用启动时启动调度器，关闭时停止调度器。

### 关键配置
- `PUSH_URL_TEMPLATE`: `https://api.day.app/{bark_key}/{content}`
- 调度器: `AsyncIOScheduler` 实例（全局单例）
- 任务存储: `task_store: Dict[str, dict]`

## 代码结构

所有业务逻辑集中在 `main.py`，包括：
- 数据模型（`ScheduleRequest`, `TaskResponse`）
- 核心功能（`send_push_notification` 异步推送函数）
- API 路由（7 个端点）
- 生命周期管理

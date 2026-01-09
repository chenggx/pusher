# FastAPI 定时任务推送服务

## 📋 项目简介

本项目是一个基于 FastAPI 的定时任务推送服务，可以接收时间和内容参数，设置定时任务，当到达指定时间后自动向推送 API 发送 GET 请求。

**主要功能：**
- ✅ 设置定时任务（支持任意未来时间）
- ✅ 自动推送通知到手机（通过 Bark/Day.app）
- ✅ 查看任务列表和状态
- ✅ 取消未执行的任务
- ✅ 完整的日志记录

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

服务将在 `http://0.0.0.0:8000` 启动。

### 3. 测试接口

#### 设置定时任务（5分钟后推送）

```bash
curl -X POST "http://127.0.0.1:8000/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_time": "2025-01-10T15:30:00",
    "content": "测试推送消息"
  }'
```

#### 设置1年后的定时任务

```bash
curl -X POST "http://127.0.0.1:8000/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_time": "2026-01-10T12:00:00",
    "content": "一年后的提醒：记得体检！"
  }'
```

#### 查看所有任务

```bash
curl http://127.0.0.1:8000/tasks
```

#### 健康检查

```bash
curl http://127.0.0.1:8000/health
```

## 📖 API 文档

### 1. 设置定时任务

**接口：** `POST /schedule`

**请求参数：**
```json
{
  "schedule_time": "2025-01-10T15:30:00",
  "content": "推送内容"
}
```

**参数说明：**
- `schedule_time`：执行时间，ISO 8601 格式（时区无关，使用服务器本地时间）
- `content`：推送到手机的内容

**成功响应：**
```json
{
  "job_id": "abc12345",
  "schedule_time": "2025-01-10T15:30:00",
  "content": "推送内容",
  "status": "scheduled",
  "message": "任务已成功设置，将于 2025-01-10T15:30:00 推送"
}
```

**错误响应（时间已过）：**
```json
{
  "detail": {
    "error": "时间验证失败",
    "message": "执行时间必须是未来时间",
    "current_time": "2025-01-09T10:00:00",
    "received_time": "2025-01-08T10:00:00"
  }
}
```

### 2. 查看所有任务

**接口：** `GET /tasks`

**响应示例：**
```json
{
  "total": 2,
  "tasks": {
    "abc12345": {
      "job_id": "abc12345",
      "schedule_time": "2025-01-10T15:30:00",
      "content": "推送内容",
      "status": "completed",
      "created_at": "2025-01-09T10:00:00"
    }
  }
}
```

### 3. 查看单个任务

**接口：** `GET /tasks/{job_id}`

### 4. 取消任务

**接口：** `DELETE /tasks/{job_id}`

### 5. 健康检查

**接口：** `GET /health`

## 🔧 配置说明

### 修改推送 Key

在 `main.py` 文件中修改以下配置：

```python
# 推送 API 配置
BARK_KEY = "你的Bark Key"
PUSH_URL_TEMPLATE = f"https://api.day.app/{BARK_KEY}/{{content}}"
```

你可以在 [Bark 官网](https://day.app/) 注册获取免费的推送 Key。

### 时区说明

当前版本使用服务器本地时间（时区无关），如需使用 UTC 时间，请修改 `ScheduleRequest` 模型中的时间处理逻辑。

## 📝 完整使用示例

### 1. 设置提醒任务

```python
import requests
import json
from datetime import datetime, timedelta

# 设置 10 分钟后的提醒
reminder_time = datetime.now() + timedelta(minutes=10)
schedule_time = reminder_time.strftime("%Y-%m-%dT%H:%M:%S")

response = requests.post(
    "http://127.0.0.1:8000/schedule",
    json={
        "schedule_time": schedule_time,
        "content": "⏰ 提醒：10分钟后有会议！"
    }
)

print(response.json())
```

### 2. 设置生日提醒（一年后）

```python
import requests
from datetime import datetime, timedelta

# 设置明年的生日提醒
next_birthday = datetime.now().replace(
    year=datetime.now().year + 1,
    month=3,
    day=15,
    hour=9,
    minute=0,
    second=0
)

response = requests.post(
    "http://127.0.0.1:8000/schedule",
    json={
        "schedule_time": next_birthday.isoformat(),
        "content": "🎂 明天是妈妈生日，别忘了祝福！"
    }
)
```

## 🐳 Docker 部署

创建 `Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]
```

构建和运行：

```bash
docker build -t scheduled-push .
docker run -d -p 8000:8000 --name push-service scheduled-push
```

## ⚠️ 注意事项

1. **时间格式**：必须使用 ISO 8601 格式，例如：`2025-01-10T15:30:00`
2. **时间验证**：设置的时间必须是未来时间，否则会返回错误
3. **内存存储**：当前使用内存存储任务信息，服务重启后任务会丢失
4. **推送服务**：确保 `BARK_KEY` 正确配置，否则无法收到推送
5. **网络要求**：服务器需要能够访问 `https://api.day.app`

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

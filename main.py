"""
FastAPI 定时任务推送服务
功能：接受时间和内容参数，设置定时任务，到期后向推送 API 发送 GET 请求
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, text

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# 推送 API 配置
# 这里填入你的 Bark 推送 key
# BARK_KEY = "6gopxrLawg7Nq6jVVki4HT"
PUSH_URL_TEMPLATE = "https://api.day.app/{bark_key}/{content}?level=critical&volume=5"

# 数据库配置（MySQL）
# 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名
# Clever Cloud: 从环境变量获取
from dotenv import load_dotenv
load_dotenv()  # 加载 .env 文件

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "scheduled_push")

DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# APScheduler 调度器（使用 SQLAlchemyJobStore 持久化）
jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
scheduler = AsyncIOScheduler(jobstores=jobstores)

# 内存缓存任务信息（用于快速查询）
task_store: Dict[str, dict] = {}

# SQLAlchemy 引擎（延迟初始化）
_engine = None


def _get_engine():
    """获取或创建数据库引擎"""
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL)
    return _engine


def init_db():
    """初始化 MySQL 数据库表"""
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS tasks (
                job_id VARCHAR(36) PRIMARY KEY,
                bark_key VARCHAR(255),
                schedule_time DATETIME,
                content TEXT,
                status VARCHAR(50),
                created_at DATETIME
            )
        '''))
        conn.commit()
    logger.info("✅ 数据库初始化完成")


def save_task_to_db(job_id: str, bark_key: str, schedule_time: datetime, content: str, status: str):
    """保存任务到数据库"""
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text('''
            INSERT INTO tasks (job_id, bark_key, schedule_time, content, status, created_at)
            VALUES (:job_id, :bark_key, :schedule_time, :content, :status, :created_at)
            ON DUPLICATE KEY UPDATE
                bark_key = :bark_key,
                schedule_time = :schedule_time,
                content = :content,
                status = :status
        '''), {
            "job_id": job_id,
            "bark_key": bark_key,
            "schedule_time": schedule_time,
            "content": content,
            "status": status,
            "created_at": datetime.now()
        })
        conn.commit()


def load_tasks_from_db():
    """从数据库加载所有任务到内存"""
    engine = _get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text('SELECT job_id, bark_key, schedule_time, content, status FROM tasks'))
            for row in result:
                job_id, bark_key, schedule_time, content, status = row
                task_store[job_id] = {
                    "job_id": job_id,
                    "bark_key": bark_key,
                    "schedule_time": schedule_time.isoformat() if schedule_time else None,
                    "content": content,
                    "status": status
                }
        logger.info(f"✅ 从数据库加载了 {len(task_store)} 个任务")
    except Exception as e:
        logger.warning(f"加载任务失败（数据库可能还未创建）: {e}")


def update_task_status_in_db(job_id: str, status: str, **extra):
    """更新任务状态"""
    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text('SELECT bark_key, schedule_time, content FROM tasks WHERE job_id = :job_id'), {"job_id": job_id})
        row = result.fetchone()
        if row:
            bark_key, schedule_time, content = row
            save_task_to_db(job_id, bark_key, schedule_time, content, status)
        conn.commit()


def delete_task_from_db(job_id: str):
    """从数据库删除任务"""
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text('DELETE FROM tasks WHERE job_id = :job_id'), {"job_id": job_id})
        conn.commit()


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 启动服务...")
    init_db()
    load_tasks_from_db()
    logger.info("🚀 启动 APScheduler 定时任务调度器...")
    scheduler.start()

    # 打印当前所有待执行任务
    jobs = scheduler.get_jobs()
    logger.info(f"✅ 调度器启动成功，当前有 {len(jobs)} 个待执行任务")
    for job in jobs:
        logger.info(f"  - 任务ID: {job.id}, 执行时间: {job.next_run_time}")

    yield

    # 关闭时
    logger.info("🛑 正在停止 APScheduler...")
    scheduler.shutdown()
    logger.info("✅ 调度器已停止")


# FastAPI 应用实例
app = FastAPI(
    title="定时任务推送服务",
    description="设置定时任务，到期后自动推送通知",
    version="1.0.0",
    lifespan=lifespan
)


# ==================== 数据模型 ====================

class ScheduleRequest(BaseModel):
    """定时任务请求模型"""
    schedule_time: datetime = Field(
        ...,
        description="执行时间 (ISO 8601 格式，如：2025-01-10T15:30:00)",
        examples=["2025-01-10T15:30:00"]
    )
    content: str = Field(
        ...,
        description="推送内容",
        examples=["提醒：该喝水了！"]
    )

    bark_key: str = Field(
        ...,
        description="Bark 的 key",
        examples=["1234567890"]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "schedule_time": (datetime.now() + timedelta(minutes=5)).isoformat(),
                "content": "测试推送消息"
            }
        }
    )


class TaskResponse(BaseModel):
    """任务响应模型"""
    job_id: str
    schedule_time: datetime
    content: str
    status: str
    message: str = ""


# ==================== 核心功能 ====================

async def send_push_notification(job_id: str, bark_key: str, content: str):
    """
    定时任务执行的函数：向推送 API 发送 GET 请求

    Args:
        job_id: 任务 ID
        content: 推送内容
        bark_key: bark 的 key
    """
    logger.info(f"任务 {job_id} 触发：推送内容 '{content}'")

    url = PUSH_URL_TEMPLATE.format(content=content, bark_key=bark_key)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)

        if response.status_code == 200:
            logger.info(f"任务 {job_id} 推送成功: {response.text}")
            if job_id in task_store:
                task_store[job_id]['status'] = 'completed'
            update_task_status_in_db(job_id, 'completed', response=response.text)
        else:
            logger.error(f"任务 {job_id} 推送失败: HTTP {response.status_code}")
            if job_id in task_store:
                task_store[job_id]['status'] = 'failed'
            update_task_status_in_db(job_id, 'failed', error=f"HTTP {response.status_code}")

    except Exception as e:
        logger.error(f"任务 {job_id} 执行异常: {str(e)}")
        if job_id in task_store:
            task_store[job_id]['status'] = 'failed'
        update_task_status_in_db(job_id, 'failed', error=str(e))


# ==================== API 接口 ====================

@app.get("/")
async def root():
    """健康检查接口"""
    return {
        "status": "running",
        "service": "定时任务推送服务",
        "scheduler_state": "started" if scheduler.running else "stopped",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.post("/schedule", response_model=TaskResponse)
async def schedule_task(request: ScheduleRequest):
    """
    设置定时任务

    - **schedule_time**: 执行时间，必须是未来时间
    - **content**: 推送内容
    """
    now = datetime.now().astimezone()

    # 1. 验证时间必须是未来时间
    request_time = request.schedule_time
    if request_time.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "时间验证失败",
                "message": "执行时间必须带时区信息",
                "current_time": now.isoformat(),
                "received_time": request.schedule_time.isoformat()
            }
        )

    if request_time <= now:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "时间验证失败",
                "message": "执行时间必须是未来时间",
                "current_time": now.isoformat(),
                "received_time": request.schedule_time.isoformat()
            }
        )

    # 2. 生成唯一任务 ID
    job_id = str(uuid.uuid4())[:8]  # 使用短 UUID 便于识别

    try:
        # 3. 添加到 APScheduler（持久化到数据库）
        scheduler.add_job(
            send_push_notification,
            'date',  # 使用 date 触发器，只执行一次
            run_date=request.schedule_time,
            args=[job_id, request.bark_key, request.content],
            id=job_id,
            replace_existing=False  # 不替换已存在的任务
        )

        # 4. 保存到数据库和内存
        task_info = {
            "job_id": job_id,
            "schedule_time": request.schedule_time.isoformat(),
            "content": request.content,
            "status": "scheduled"
        }
        task_store[job_id] = task_info
        save_task_to_db(job_id, request.bark_key, request.schedule_time, request.content, "scheduled")

        logger.info(f"✅ 任务已设置: {job_id}, 执行时间: {request.schedule_time}")

        return TaskResponse(
            job_id=job_id,
            schedule_time=request.schedule_time,
            content=request.content,
            status="scheduled",
            message=f"任务已成功设置，将于 {request.schedule_time} 推送"
        )

    except Exception as e:
        logger.error(f"❌ 设置任务失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"设置定时任务失败: {str(e)}"
        )


@app.get("/tasks")
async def list_tasks():
    """
    获取所有任务列表
    """
    # 获取 APScheduler 中的任务
    scheduler_jobs = []
    for job in scheduler.get_jobs():
        scheduler_jobs.append({
            "job_id": job.id,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None
        })

    return {
        "total": len(task_store),
        "tasks": task_store,
        "scheduler_jobs": scheduler_jobs
    }


@app.get("/tasks/{job_id}")
async def get_task(job_id: str):
    """获取单个任务详情"""
    if job_id not in task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    return task_store[job_id]


@app.delete("/tasks/{job_id}")
async def cancel_task(job_id: str):
    """取消任务"""
    if job_id not in task_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        scheduler.remove_job(job_id)
        del task_store[job_id]
        delete_task_from_db(job_id)
        logger.info(f"✅ 任务 {job_id} 已取消")
        return {"message": "任务已取消", "job_id": job_id}
    except JobLookupError:
        raise HTTPException(status_code=404, detail="任务不存在或已执行")


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False  # 生产环境设为 False
    )

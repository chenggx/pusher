# 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 运行阶段
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]
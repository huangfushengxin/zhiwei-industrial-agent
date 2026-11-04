# Credential-free tool demo. The AGH/model image is deploy/render/Dockerfile.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY tools ./tools
COPY app ./app
COPY data ./data
EXPOSE 8801
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8801/api/health', timeout=2)"
CMD ["python", "app/demo_server.py", "--mode", "offline", "--host", "0.0.0.0", "--port", "8801"]

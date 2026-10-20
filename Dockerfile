FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY support_agent ./support_agent
COPY data/policies ./data/policies
COPY data/orders.json data/users.json ./data/
ENV SUPPORT_DATA_DIR=/var/lib/support SUPPORT_ENV=production
RUN useradd --create-home support && mkdir -p /var/lib/support && chown support:support /var/lib/support
USER support
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3)"
CMD ["python", "-m", "uvicorn", "support_agent.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

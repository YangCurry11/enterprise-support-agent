@echo off
python -m uvicorn support_agent.app:app --reload --host 127.0.0.1 --port 8000

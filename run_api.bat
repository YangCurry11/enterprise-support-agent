@echo off
uvicorn support_agent.mock_api:app --reload --port 8000

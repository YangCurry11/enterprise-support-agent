#!/usr/bin/env bash
uvicorn support_agent.mock_api:app --reload --port 8000

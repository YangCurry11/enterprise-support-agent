# 配置文件 (设置中心) 统一项目管理、API地址、默认用户信息
from pathlib import Path  # path是python里的处理文件路径工具
import os  # 读取环境变量
from dotenv import load_dotenv # 读取.env文件

load_dotenv() # 加载.env文件

BASE_DIR = Path(__file__).resolve().parent.parent # 项目根目录 
DATA_DIR = BASE_DIR / "data"
POLICY_DIR = DATA_DIR / "policies"
BUSINESS_API_URL = os.getenv("BUSINESS_API_URL", "http://127.0.0.1:8000") # 业务 FastAPI 地址
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "U1001") # 默认用户编号
CORS_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
)

# __file__ 是当前文件的绝对路径，resolve() 是获取绝对路径，parent 是上级目录，两个即项目根目录
# --------------以后接大模型会加---------------
# LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

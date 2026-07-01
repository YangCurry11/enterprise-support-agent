# 命令行入口 
# 接收用户输入
# 创建 Agent
# 把用户问题交给 Agent
# 打印 Agent 执行过程和最终回复
from __future__ import annotations  

import argparse  #接受命令行输入
import json  

from support_agent.agents import CustomerSupportAgent  #从 support_agent 文件夹里的 agents.py 文件中，导入 CustomerSupportAgent 这个类。


def main():
    parser = argparse.ArgumentParser(description="企业客服多 Agent CLI Demo")
    parser.add_argument("message", nargs="*", help="用户输入，例如：我的订单 ORD1001 到哪了")  # nargs="*"：用户可以输入多个词，也可以不输入。
    parser.add_argument("--user-id", default="U1001", help="用户编号，默认 U1001")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 过程")
    args = parser.parse_args()

    message = " ".join(args.message).strip()  # " ".join(args.message)用空格把列表的词拼起来，.strip()去掉字符串前后的空格 
    if not message:
        message = input("请输入用户问题：").strip()

    agent = CustomerSupportAgent()  #创建一个企业客服agent 
    result = agent.run(message, user_id=args.user_id)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("\n========== Agent 执行过程 ==========")
    for i, step in enumerate(result["steps"], 1):
        print(f"{i}. {step['name']}: {step['detail']}")

    print("\n========== 最终回复 ==========")
    print(result["final_response"])


if __name__ == "__main__":
    main()

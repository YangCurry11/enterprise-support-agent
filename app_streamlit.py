from __future__ import annotations

import streamlit as st # 流式处理 streamlit

from support_agent.agents import CustomerSupportAgent

st.set_page_config(page_title="企业客服多 Agent Demo", page_icon="🤖", layout="wide")

st.title("🤖 企业客服工单多 Agent 系统")
st.caption("本 Demo 展示：意图识别、订单 API 调用、政策 RAG 检索、工单创建与回复生成。")

# 侧边栏
with st.sidebar:
    st.header("示例问题")
    examples = [
        "我的订单 ORD1001 到哪了？",
        "我的订单 ORD2001 到哪了？",
        "ORD1002 怎么还没发货？",
        "我买了10天的耳机还能退吗？",
        "商品坏了，无法使用，帮我处理一下",
        "我要投诉，你们服务太差了",
        "我要人工客服",
    ]
    selected = st.selectbox("选择一个示例", examples) # 下拉框 选择一个示例
    user_id = st.text_input("用户编号", value="U1001")

query = st.text_area("请输入用户问题", value=selected, height=100) # 文本框 输入用户问题

if st.button("运行 Agent", type="primary"):
    with st.spinner("Agent 正在处理..."):
        agent = CustomerSupportAgent()
        result = agent.run(query, user_id=user_id)

    st.subheader("最终回复") # 显示小标题
    st.success(result["final_response"]) # 显示绿色提示框

    st.subheader("Agent 执行过程")
    for step in result["steps"]:
        with st.expander(step["name"], expanded=False): # 创建一个可以展开/折叠的小框
            st.json(step["detail"])

    st.subheader("完整状态 JSON")
    st.json(result)

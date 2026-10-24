"""真实 FastAPI/SQLite/LangGraph 集成场景；不触碰演示库、不请求供应商。"""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import uuid
from .metrics import timing_metrics


def evaluate(cases):
    from fastapi.testclient import TestClient
    from support_agent import config, business_db, app as api, llm_client
    from support_agent.runtime import WorkflowService
    from support_agent.scoped_tools import ScopedTools
    rows, requests, tool_calls = [], [], []
    tokens = '{"eval-customer":{"user_id":"U1001","role":"customer"},"eval-other":{"user_id":"U1002","role":"customer"},"eval-reviewer":{"user_id":"S1001","role":"support"}}'
    with tempfile.TemporaryDirectory(prefix="serviceflow-eval-") as directory, ExitStack() as stack:
        root = Path(directory)
        stack.enter_context(patch.dict("os.environ", {"LLM_API_KEY":"", "LLM_INTENT_ENABLED":"false", "RAG_MODE":"tfidf", "EMBEDDING_ENABLED":"false", "RAG_REMOTE_QUERY_ENABLED":"false", "SUPPORT_ENV":"development", "SUPPORT_AUTH_TOKENS":tokens}))
        from support_agent.rag import PolicyKnowledgeBase
        from support_agent.rag_config import RagSettings
        kb = PolicyKnowledgeBase(settings=RagSettings())
        stack.enter_context(patch("support_agent.scoped_tools.policy_index", lambda: kb))
        for module, name, value in ((config,"DATA_DIR",root),(business_db,"DATA_DIR",root),(business_db,"DB_PATH",root/"business.db"),(api,"DATA_DIR",root)):
            stack.enter_context(patch.object(module,name,value))
        class ObservedTools(ScopedTools):
            def query_order(self,*args,**kwargs):
                result=super().query_order(*args,**kwargs); tool_calls.append({"tool":"query_order","ok":result["ok"]}); return result
            def search_policy(self,*args,**kwargs):
                result=super().search_policy(*args,**kwargs); tool_calls.append({"tool":"search_policy","ok":result["ok"]}); return result
            def create_ticket(self,*args,**kwargs):
                result=super().create_ticket(*args,**kwargs); tool_calls.append({"tool":"create_ticket","ok":result["ok"]}); return result
        with TestClient(api.app) as client:
            api.app.state.workflows = WorkflowService(root,tools_factory=ObservedTools)
            def call(method,path,body=None,token="eval-customer"):
                started=time.perf_counter()
                result=client.request(method,path,json=body,headers={"Authorization":"Bearer "+token})
                requests.append({"status_code":result.status_code,"latency_ms":(time.perf_counter()-started)*1000})
                return result
            def run(text,key=None):
                return call("POST","/agent/run",{"user_input":text,"request_id":key or str(uuid.uuid4())}).json()
            for case in cases:
                started=time.perf_counter(); start_tools=len(tool_calls); before=len(business_db.list_tickets()); checks={}; result={}; fallback=False
                try:
                    scenario=case["scenario"]
                    if scenario in {"multi_turn","user_isolation","clarification"}:
                        cid=call("POST","/agent/conversations",{}).json()["conversation_id"]
                        def message(text):
                            return call("POST",f"/agent/conversations/{cid}/messages",{"content":text,"request_id":str(uuid.uuid4())}).json()
                        if scenario=="multi_turn":
                            first=message("我的订单 ORD1001 到哪里了？"); second=message("那它可以退款吗？"); result=message("帮我申请售后。")
                            checks["order_reference"] = second["order_id"]==result["order_id"]=="ORD1001"
                            checks["new_run_each_turn"] = len({first["run_id"],second["run_id"],result["run_id"]})==3
                        elif scenario=="user_isolation":
                            result=message("订单 ORD1001")
                            checks["conversation_denied"] = call("GET",f"/agent/conversations/{cid}/messages",token="eval-other").status_code==404
                        else:
                            first=message(case["text"]); result=message("ORD1001")
                            checks["same_run_resumed"] = first["run_id"]==result["run_id"]
                    elif scenario in {"idempotency","review_reject"}:
                        key=str(uuid.uuid4()); result=run(case["text"],key)
                        checks["no_ticket_before_review"]=len(business_db.list_tickets())==before
                        endpoint=f"/agent/runs/{result['run_id']}/review"
                        decision={"approved":scenario=="idempotency"}
                        result=call("POST",endpoint,decision,"eval-reviewer").json()
                        call("POST",endpoint,decision,"eval-reviewer")
                        checks["ticket_count"]=len(business_db.list_tickets())-before==int(decision["approved"])
                        if scenario=="idempotency":
                            checks["same_request_run"]=run(case["text"],key)["run_id"]==result["run_id"]
                    elif scenario=="model_timeout":
                        with patch.object(llm_client,"is_llm_enabled",return_value=True), patch.object(llm_client,"generate_customer_reply",side_effect=TimeoutError("simulated")):
                            result=run(case["text"])
                        fallback=any(s["detail"].get("mode")=="fallback_template" for s in result["steps"])
                        checks["model_fallback"]=fallback
                    else:
                        result=run(case["text"])
                    if scenario=="foreign_order":
                        checks["no_foreign_data"]="机械键盘" not in str(result) and not result["tool_results"]["query_order"]["ok"]
                    if scenario=="policy": checks["has_sources"]=bool(result["retrieved_docs"])
                    observed=[step["name"] for step in result["steps"]]
                    checks["expected_agents"]=set(case["expected_agents"]).issubset(observed)
                    checks["expected_status"]=result["status"]==case["expected_status"]
                    if scenario=="review": checks["review_before_write"]=len(business_db.list_tickets())==before
                    error=None
                except Exception as exc:
                    checks["execution"]=False; observed=[]; error=type(exc).__name__
                rows.append({"id":case["id"],"input":case.get("text",case["scenario"]),"scenario":case["scenario"],
                             "passed":all(checks.values()),"checks":checks,"error":error,
                             "expected_agents":case["expected_agents"],"observed_agents":observed,
                             "status":result.get("status"),"workflow_completed":result.get("status")=="completed",
                             "tool_calls":tool_calls[start_tools:],"model_fallback":fallback,
                             "latency_ms":(time.perf_counter()-started)*1000})
    passed=sum(row["passed"] for row in rows)
    return {"metrics":{"sample_count":len(rows),"passed":passed,"failed":len(rows)-passed,
                       "pass_rate":passed/len(rows) if rows else None,"request_total":len(requests),
                       "request_success":sum(200<=r["status_code"]<300 for r in requests),
                       "request_failed":sum(not 200<=r["status_code"]<300 for r in requests),
                       "request_success_rate":sum(200<=r["status_code"]<300 for r in requests)/len(requests) if requests else None,
                       "completed_scenarios":sum(r["workflow_completed"] for r in rows),
                       "tool_call_count":len(tool_calls),"tool_success_rate":sum(t["ok"] for t in tool_calls)/len(tool_calls) if tool_calls else None,
                       "tool_denied_or_failed":sum(not t["ok"] for t in tool_calls),
                       "simulated_model_attempts":sum(c["scenario"]=="model_timeout" for c in cases),
                       "model_fallback_count":sum(r["model_fallback"] for r in rows),
                       "model_fallback_rate":sum(r["model_fallback"] for r in rows)/sum(c["scenario"]=="model_timeout" for c in cases) if any(c["scenario"]=="model_timeout" for c in cases) else None,
                       "timing":timing_metrics([r["latency_ms"] for r in requests]),"token_usage":None},"cases":rows}

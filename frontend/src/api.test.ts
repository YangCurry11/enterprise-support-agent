import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, supportApi } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("supportApi", () => {
  it("posts the user question and id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ final_response: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    await supportApi.run("订单 ORD1001 到哪了？", "U1001");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/agent/run");
    expect(JSON.parse(String(init.body))).toEqual({
      user_input: "订单 ORD1001 到哪了？",
      user_id: "U1001",
    });
  });

  it("preserves server errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "参数错误" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    })));
    await expect(supportApi.run("问题", "U1001")).rejects.toEqual(new ApiError("参数错误", 422));
  });

  it("reports network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(supportApi.health()).rejects.toMatchObject({ status: 0 });
  });
});

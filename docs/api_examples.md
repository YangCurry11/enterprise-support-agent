# API 调用示例

## 查询订单

```bash
curl http://127.0.0.1:8000/orders/ORD1001
```

## 查询用户

```bash
curl http://127.0.0.1:8000/users/U1001
```

## 创建工单

```bash
curl -X POST http://127.0.0.1:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "U1001",
    "issue_type": "complaint",
    "description": "用户投诉商品损坏",
    "order_id": "ORD1001",
    "priority": "high"
  }'
```

## 查看政策列表

```bash
curl http://127.0.0.1:8000/policies
```

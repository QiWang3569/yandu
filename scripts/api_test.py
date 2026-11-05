"""燕渡 API 自动回归测试脚本。

运行：
    .\.venv\Scripts\python.exe scripts/api_test.py

输出 stdout 为 JSON 结果数组（id / name / status / detail），status ∈ {PASS, FAIL, ENV}。
stderr 输出摘要与需要手动清理的资源 id。
"""
import io
import json
import sys

import httpx
from PIL import Image


BASE = "http://127.0.0.1:8000"
RESULTS = []
CREATED_ITEMS = []
CREATED_INTENTS = []


def record(cid, name, status, detail=""):
    RESULTS.append({"id": cid, "name": name, "status": status, "detail": detail})


def login(profile):
    c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=False)
    r = c.post("/api/v1/auth/demo", json={"profile": profile})
    if r.status_code != 200:
        raise RuntimeError(f"demo login {profile} failed: {r.status_code} {r.text[:200]}")
    return c


def jpg_bytes():
    img = Image.new("RGB", (320, 240), (120, 180, 140))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def main():
    anon = httpx.Client(base_url=BASE, timeout=30)
    buyer = login("buyer")
    seller = login("seller")
    admin = login("admin")

    # A0 环境
    r = anon.get("/api/v1/health")
    record("A0", "健康检查返回 ok", "PASS" if r.status_code == 200 and r.json().get("status") == "ok" else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/meta")
    meta = r.json()
    ok = r.status_code == 200 and len(meta.get("categories", [])) == 5 and len(meta.get("campuses", [])) == 5 and len(meta.get("conditions", [])) == 5 and meta.get("demo_mode") is True
    record("A0", "meta 返回 5 分类/5 校区/5 成色且 demo_mode=true", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/")
    record("A0", "首页返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    # A1 登录
    r = buyer.get("/api/v1/auth/me")
    record("A1", "买家 /auth/me 返回 demo-buyer", "PASS" if r.status_code == 200 and r.json().get("user", {}).get("id") == "demo-buyer" else "FAIL", f"HTTP {r.status_code}")
    r = admin.get("/api/v1/auth/me")
    record("A1", "管理员 /auth/me 返回 demo-admin", "PASS" if r.status_code == 200 and r.json().get("user", {}).get("id") == "demo-admin" else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"mine": "true"})
    record("A1", "未登录访问 mine 返回 401", "PASS" if r.status_code == 401 else "FAIL", f"HTTP {r.status_code}")
    r = buyer.patch("/api/v1/users/me", json={"nickname": "林同学", "campus": "燕园校本部", "bio": "自动化测试", "avatar_color": "sage"})
    record("A1", "修改个人资料返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
    r = buyer.patch("/api/v1/users/me", json={"nickname": "林", "campus": "燕园校本部", "bio": "", "avatar_color": "sage"})
    record("A1", "昵称少于 2 字返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = anon.post("/api/v1/auth/email/request-code", json={"email": "notpku@example.com"})
    record("A1", "非北大邮箱发码返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = anon.post("/api/v1/auth/email/request-code", json={"email": "test@pku.edu.cn"})
    record("A1", "未配置 SMTP 发码返回 503", "PASS" if r.status_code == 503 else "FAIL", f"HTTP {r.status_code}")
    r = anon.post("/api/v1/auth/password/login", json={"email": "x@pku.edu.cn", "password": "wrong-pass-1"})
    record("A1", "错误密码登录返回 401", "PASS" if r.status_code == 401 else "FAIL", f"HTTP {r.status_code}")
    bad = httpx.Client(base_url=BASE, timeout=30, headers={"Origin": "http://evil.example.com"})
    r = bad.post("/api/v1/auth/demo", json={"profile": "buyer"})
    record("A1", "非白名单 Origin 写请求返回 403", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code}")

    # A2 商品
    r = anon.get("/api/v1/items/")
    items = r.json()
    record("A2", "商品列表返回 200 且有数据", "PASS" if r.status_code == 200 and len(items.get("items", [])) > 0 else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"category": "数码与影音"})
    ok = r.status_code == 200 and all(i["category"] == "数码与影音" for i in r.json().get("items", []))
    record("A2", "分类筛选只返回对应分类", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"campus": "万柳学区"})
    ok = r.status_code == 200 and all(i["campus"] in ("万柳学区", "不限校区") for i in r.json().get("items", []))
    record("A2", "校区筛选包含不限校区", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"min_price": "0", "max_price": "50"})
    ok = r.status_code == 200 and all(0 <= i["price"] <= 50 for i in r.json().get("items", []))
    record("A2", "价格区间筛选正确", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"sort": "price_asc"})
    prices = [i["price"] for i in r.json().get("items", [])]
    record("A2", "价格升序排序正确", "PASS" if r.status_code == 200 and prices == sorted(prices) else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"q": "耳机"})
    ok = r.status_code == 200 and any("耳机" in i["title"] for i in r.json().get("items", []))
    record("A2", "关键词搜索命中商品", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"q": "airpods"})
    ok = r.status_code == 200 and any("耳机" in i["title"] for i in r.json().get("items", []))
    record("A2", "同义词搜索 airpods→耳机", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"page": "0"})
    record("A2", "page<1 返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/", params={"size": "51"})
    record("A2", "size>50 返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    first_id = items["items"][0]["id"]
    r = anon.get(f"/api/v1/items/{first_id}")
    record("A2", "商品详情返回 200", "PASS" if r.status_code == 200 and r.json().get("id") == first_id else "FAIL", f"HTTP {r.status_code}")
    r = anon.get("/api/v1/items/not-exist-id")
    record("A2", "不存在的商品返回 404", "PASS" if r.status_code == 404 else "FAIL", f"HTTP {r.status_code}")

    # A3 发布与图片
    r = seller.post("/api/v1/uploads", files={"file": ("t.jpg", jpg_bytes(), "image/jpeg")})
    ok = r.status_code == 201 and r.json().get("url", "").startswith("/uploads/")
    image_url = r.json().get("url") if r.status_code == 201 else None
    record("A3", "上传合法图片返回 201", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    r = seller.post("/api/v1/uploads", files={"file": ("t.txt", b"not an image", "text/plain")})
    record("A3", "上传非图片返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = seller.post("/api/v1/items/", json={"title": "测试商品", "description": "自动化测试商品描述", "category": "数码与影音", "price": 88.5, "campus": "燕园校本部", "condition_grade": "95新", "tags": ["测试"], "images": []})
    record("A3", "无图片发布返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = seller.post("/api/v1/items/", json={"title": "测试", "description": "描述太短", "category": "数码与影音", "price": 10, "campus": "燕园校本部", "images": [image_url]})
    record("A3", "描述少于 5 字返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    r = seller.post("/api/v1/items/", json={"title": "测试商品", "description": "自动化测试商品描述", "category": "不存在的分类", "price": 10, "campus": "燕园校本部", "images": [image_url]})
    record("A3", "无效分类返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")

    def publish(title):
        return seller.post("/api/v1/items/", json={"title": title, "description": "自动化测试商品描述", "category": "数码与影音", "price": 88.5, "campus": "燕园校本部", "condition_grade": "95新", "tags": ["测试"], "images": [image_url]})

    r = publish("测试商品A")
    item_a = r.json().get("id") if r.status_code == 201 else None
    CREATED_ITEMS.append(item_a)
    record("A3", "发布商品返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")

    # A4 收藏（itemA）
    if item_a:
        r = buyer.post(f"/api/v1/items/{item_a}/favorite")
        record("A4", "收藏商品返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.get("/api/v1/items/", params={"favorites": "true"})
        ok = r.status_code == 200 and any(i["id"] == item_a for i in r.json().get("items", []))
        record("A4", "我的收藏包含该商品", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
        r = buyer.delete(f"/api/v1/items/{item_a}/favorite")
        record("A4", "取消收藏返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.post(f"/api/v1/items/{item_a}/sale-feedback")
        record("A9", "买家反馈已售返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.post(f"/api/v1/items/{item_a}/sale-feedback")
        record("A9", "重复反馈已售返回 409", "PASS" if r.status_code == 409 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.post(f"/api/v1/items/{item_a}/reports", json={"reason": "这是自动化测试举报内容"})
        report_id = r.json().get("id") if r.status_code == 201 else None
        record("A9", "买家举报商品返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
        r = buyer.post(f"/api/v1/items/{item_a}/reports", json={"reason": "重复举报测试内容"})
        record("A9", "重复举报商品返回 409", "PASS" if r.status_code == 409 else "FAIL", f"HTTP {r.status_code}")
        r = seller.patch(f"/api/v1/items/{item_a}/status", json={"status": "RESERVED"})
        record("A3", "卖家改为预订返回 200", "PASS" if r.status_code == 200 and r.json().get("status") == "RESERVED" else "FAIL", f"HTTP {r.status_code}")
        r = seller.patch(f"/api/v1/items/{item_a}/status", json={"status": "SOLD"})
        record("A3", "卖家改为已售返回 200", "PASS" if r.status_code == 200 and r.json().get("status") == "SOLD" else "FAIL", f"HTTP {r.status_code}")
        r = seller.patch(f"/api/v1/items/{item_a}/status", json={"status": "ACTIVE"})
        record("A3", "已售商品重新上架返回 409", "PASS" if r.status_code == 409 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.patch(f"/api/v1/items/{item_a}/status", json={"status": "ACTIVE"})
        record("A3", "非本人改状态返回 403", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code}")

    # A5 求购
    r = buyer.post("/api/v1/wanted/", json={"title": "求测试商品", "description": "求购一件测试商品用于自动化验证", "category": "数码与影音", "budget": 50, "campus": "燕园校本部"})
    wanted_id = r.json().get("id") if r.status_code == 201 else None
    record("A5", "发布求购返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
    r = buyer.get("/api/v1/wanted/")
    ok = r.status_code == 200 and any(w["id"] == wanted_id for w in r.json())
    record("A5", "求购看板包含新求购", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
    if wanted_id:
        r = buyer.delete(f"/api/v1/wanted/{wanted_id}")
        record("A5", "关闭求购返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
    r = buyer.post("/api/v1/wanted/", json={"title": "求", "description": "太短", "category": "不存在", "budget": 10, "campus": "燕园校本部"})
    record("A5", "求购无效分类返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")

    # A8 会话与交易（itemB 保持 ACTIVE）
    r = publish("测试商品B")
    item_b = r.json().get("id") if r.status_code == 201 else None
    CREATED_ITEMS.append(item_b)
    if item_b:
        r = seller.post(f"/api/v1/items/{item_b}/conversations", json={"body": "给自己发"})
        record("A8", "给自己商品发消息返回 403", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.post(f"/api/v1/items/{item_b}/conversations", json={"body": "请问还在吗？"})
        conv_id = r.json().get("conversation", {}).get("id") if r.status_code == 201 else None
        record("A8", "买家发起会话返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
        if conv_id:
            r = seller.post(f"/api/v1/conversations/{conv_id}/messages", json={"body": "还在的"})
            seller_msg_id = r.json().get("id") if r.status_code == 201 else None
            record("A8", "卖家回复消息返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.get(f"/api/v1/conversations/{conv_id}/messages")
            ok = r.status_code == 200 and len(r.json().get("messages", [])) >= 2
            record("A8", "会话消息列表返回多条", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
            r = seller.post(f"/api/v1/conversations/{conv_id}/read")
            record("A8", "标记会话已读返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.post(f"/api/v1/conversations/{conv_id}/deal", json={"action": "request"})
            record("A8", "买家 request 返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.post(f"/api/v1/conversations/{conv_id}/deal", json={"action": "reserve"})
            record("A8", "买家 reserve 越权返回 403", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code}")
            r = seller.post(f"/api/v1/conversations/{conv_id}/deal", json={"action": "reserve"})
            record("A8", "卖家 reserve 返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = seller.post(f"/api/v1/conversations/{conv_id}/deal", json={"action": "sold"})
            record("A8", "卖家 sold 返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.post(f"/api/v1/conversations/{conv_id}/deal", json={"action": "confirm"})
            record("A8", "买家 confirm 返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.post(f"/api/v1/conversations/{conv_id}/block")
            record("A8", "拉黑会话返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            r = buyer.delete(f"/api/v1/conversations/{conv_id}/block")
            record("A8", "解除拉黑返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
            if seller_msg_id:
                r = buyer.post(f"/api/v1/conversations/{conv_id}/messages/{seller_msg_id}/reports", json={"reason": "聊天举报自动化测试"})
                chat_report_id = r.json().get("id") if r.status_code == 201 else None
                record("A9", "举报聊天消息返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
                if chat_report_id:
                    r = admin.post(f"/api/v1/admin/chat-reports/{chat_report_id}/review", json={"action": "dismiss", "note": "自动化测试不采纳", "confirmed": True})
                    record("A9", "管理员处理聊天举报返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
        r = buyer.get("/api/v1/admin/reports")
        record("A9", "非管理员访问 admin 返回 403", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code}")
        if report_id:
            r = admin.post(f"/api/v1/admin/reports/{report_id}/review", json={"action": "dismiss", "note": "自动化测试不采纳", "confirmed": True})
            record("A9", "管理员处理商品举报返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code} {r.text[:120]}")
        r = admin.get("/api/v1/admin/logs")
        record("A9", "管理员查看审计日志返回 200", "PASS" if r.status_code == 200 and len(r.json()) > 0 else "FAIL", f"HTTP {r.status_code}")

    # A6 代蹲
    r = buyer.post("/api/v1/intents/parse", json={"raw_query": "万柳300以内无线鼠标"})
    record("A6", "需求解析（依赖远程模型）", "ENV" if r.status_code == 502 else ("PASS" if r.status_code == 200 else "FAIL"), f"HTTP {r.status_code}（当前环境模型不可达返回 502）")

    parsed = {"category": "数码与影音", "max_price": 300, "campus": "万柳学区", "keywords": ["鼠标", "无线"], "excluded_keywords": ["游戏鼠标"], "preferences": ["静音"], "condition_grade": None, "clarification": None}
    r = buyer.post("/api/v1/intents/", json={"raw_query": "万柳300以内无线鼠标", "parsed": parsed})
    intent_id = r.json().get("intent", {}).get("id") if r.status_code == 201 else None
    CREATED_INTENTS.append(intent_id)
    record("A6", "创建代蹲任务返回 201", "PASS" if r.status_code == 201 else "FAIL", f"HTTP {r.status_code} {r.text[:150]}")
    if intent_id:
        r = buyer.get("/api/v1/intents/my")
        ok = r.status_code == 200 and any(i["id"] == intent_id for i in r.json())
        record("A6", "我的代蹲包含新任务", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
        r = buyer.patch(f"/api/v1/intents/{intent_id}", json={"action": "pause"})
        record("A6", "暂停任务返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.patch(f"/api/v1/intents/{intent_id}", json={"action": "resume"})
        record("A6", "恢复任务返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.patch(f"/api/v1/intents/{intent_id}", json={"action": "renew"})
        record("A6", "续期任务返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        r = buyer.post(f"/api/v1/intents/{intent_id}/retry")
        record("A6", "无失败任务时重试返回 409", "PASS" if r.status_code == 409 else "FAIL", f"HTTP {r.status_code}")
    conflict = {"category": None, "campus": "不限校区", "keywords": ["鼠标"], "excluded_keywords": ["鼠标"], "preferences": [], "condition_grade": None, "clarification": None}
    r = buyer.post("/api/v1/intents/", json={"raw_query": "冲突", "parsed": conflict})
    record("A6", "同名条件要求又排除返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    nokw = {"category": None, "campus": "不限校区", "keywords": [], "excluded_keywords": [], "preferences": [], "condition_grade": None, "clarification": None}
    r = buyer.post("/api/v1/intents/", json={"raw_query": "无关键词", "parsed": nokw})
    record("A6", "无关键词创建返回 422", "PASS" if r.status_code == 422 else "FAIL", f"HTTP {r.status_code}")
    limit_checked = False
    base = {"category": None, "campus": "不限校区", "keywords": ["台灯"], "excluded_keywords": [], "preferences": [], "condition_grade": None, "clarification": None}
    for n in range(6):
        rr = buyer.post("/api/v1/intents/", json={"raw_query": f"上限测试{n}", "parsed": base})
        if rr.status_code == 201:
            CREATED_INTENTS.append(rr.json()["intent"]["id"])
        else:
            record("A6", "第 6 个活跃任务返回 409", "PASS" if rr.status_code == 409 else "FAIL", f"HTTP {rr.status_code} {rr.text[:120]}")
            limit_checked = True
            break
    if not limit_checked:
        record("A6", "第 6 个活跃任务返回 409", "FAIL", "未触发 409（可能上限未生效）")

    # A7 通知（模型不可达无法生成通知，验证列表与 404）
    r = buyer.get("/api/v1/notifications/")
    record("A7", "通知列表返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
    r = buyer.patch("/api/v1/notifications/not-exist/read")
    record("A7", "不存在的通知标已读返回 404", "PASS" if r.status_code == 404 else "FAIL", f"HTTP {r.status_code}")

    # A10 登出
    r = anon.post("/api/v1/auth/logout")
    record("A10", "登出返回 200", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")

    # 清理：结束创建的代蹲任务
    for iid in CREATED_INTENTS:
        if iid:
            buyer.delete(f"/api/v1/intents/{iid}")

    print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    print(f"\nSUMMARY: PASS={sum(1 for x in RESULTS if x['status']=='PASS')} FAIL={sum(1 for x in RESULTS if x['status']=='FAIL')} ENV={sum(1 for x in RESULTS if x['status']=='ENV')}", file=sys.stderr)
    print(f"CLEANUP_ITEMS={json.dumps([x for x in CREATED_ITEMS if x])}", file=sys.stderr)
    print(f"CLEANUP_IMAGE={json.dumps(image_url)}", file=sys.stderr)


if __name__ == "__main__":
    main()

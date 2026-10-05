#!/usr/bin/env python3
import asyncio
import nats
from nats.aio.client import Client as NATSClient

NATS_SERVERS = "nats://127.0.0.1:4222"

TEST_TOPICS = [
    "client.>",
    "session.>",
    "broadcast",
    "client.*",
    "session.*",
    "client.test",
    "session.test",
    "client.123",
    "session.abc",
    "foo",
    "bar",
    "_INBOX.>",
    "$SYS.>",
    ">",
]

async def probe_permissions(servers):
    errors = []

    async def error_cb(e):
        errors.append(str(e))

    nc = NATSClient()
    try:
        await nc.connect(servers=servers, error_cb=error_cb, reconnect_time_wait=1, max_reconnect_attempts=1)
        print(f"✅ 已连接到 {servers}\n")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    # ---------- 测试订阅权限 ----------
    print("=== 正在测试 订阅 (Subscribe) 权限 ===")
    sub_results = {}
    async def empty_cb(msg):
        pass

    for topic in TEST_TOPICS:
        errors.clear()
        sub = None
        try:
            sub = await nc.subscribe(topic, cb=empty_cb)  # 使用异步回调
            await asyncio.sleep(0.3)
            perm_errors = [e for e in errors if "permissions violation" in e.lower()]
            if perm_errors:
                sub_results[topic] = f"❌ 拒绝 (原因: {perm_errors[0].strip()})"
            else:
                sub_results[topic] = "✅ 允许"
        except Exception as e:
            sub_results[topic] = f"❌ 异常: {e}"
        finally:
            if sub:
                try:
                    await sub.unsubscribe()
                except:
                    pass

    for topic, result in sub_results.items():
        print(f"  {topic}: {result}")

    # ---------- 测试发布权限 ----------
    print("\n=== 正在测试 发布 (Publish) 权限 ===")
    pub_results = {}
    for topic in TEST_TOPICS:
        errors.clear()
        try:
            await nc.publish(topic, b"test_probe")
            await asyncio.sleep(0.3)
            perm_errors = [e for e in errors if "permissions violation" in e.lower()]
            if perm_errors:
                pub_results[topic] = f"❌ 拒绝 (原因: {perm_errors[0].strip()})"
            else:
                pub_results[topic] = "✅ 允许"
        except Exception as e:
            pub_results[topic] = f"❌ 异常: {e}"

    for topic, result in pub_results.items():
        print(f"  {topic}: {result}")

    await nc.close()
    print("\n🔚 探测完成")

if __name__ == "__main__":
    asyncio.run(probe_permissions(NATS_SERVERS))
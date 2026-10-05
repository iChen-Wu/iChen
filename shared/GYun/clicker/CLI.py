"""
GYun.Clicker 交互式命令行工具
启动后进入菜单交互，支持录制、运行、查看、删除流程
"""
import sys
import json
from GYun.data.client import GyunClient
from GYun.clicker import ClickDriver, FlowCapture


def show_menu():
    print("\n==================== GYun Clicker 交互工具 ====================")
    print("1. 录制新自动化流程")
    print("2. 执行已保存流程")
    print("3. 查看数据库内全部流程")
    print("4. 删除指定流程")
    print("0. 退出程序")
    print("==============================================================")


def record_flow():
    name = input("请输入本次录制流程名称：").strip()
    if not name:
        print("名称不能为空，取消录制")
        return
    capture = FlowCapture(name)
    capture.start()


def run_flow():
    client = GyunClient()
    res = client.query_entities({"type": "auto_click_flow"})
    flow_list = res["list"]
    client.close()
    if not flow_list:
        print("数据库暂无任何自动化流程，请先录制！")
        return

    print("\n=== 现有流程列表 ===")
    for idx, item in enumerate(flow_list, 1):
        print(f"{idx}. {item['title']}  | ID:{item['entity_id']}")
    print("====================")
    sel = input("输入要执行的流程序号：").strip()
    if not sel.isdigit():
        print("输入无效，返回主菜单")
        return
    sel_idx = int(sel) - 1
    if sel_idx < 0 or sel_idx >= len(flow_list):
        print("序号超出范围")
        return

    target_title = flow_list[sel_idx]["title"]
    driver = ClickDriver()
    try:
        driver.run_flow_by_name(target_title)
    finally:
        driver.close()


def list_all_flows():
    client = GyunClient()
    res = client.query_entities({"type": "auto_click_flow"}, order_by="create_time", order="desc")
    client.close()
    data = res["list"]
    if not data:
        print("\n暂无存储的自动化流程")
        return
    print(f"\n共查询到 {len(data)} 条流程：")
    for i, ent in enumerate(data, 1):
        steps_count = len(ent["extra"].get("steps", []))
        source = ent["extra"].get("source", "manual")
        print(f"{i}. 名称：{ent['title']}")
        print(f"   ID：{ent['entity_id']} | 步骤数：{steps_count} | 创建来源：{source}")
        print("-" * 40)


def delete_flow():
    client = GyunClient()
    res = client.query_entities({"type": "auto_click_flow"})
    flow_list = res["list"]
    if not flow_list:
        print("暂无流程可删除")
        client.close()
        return

    print("\n=== 可删除流程列表 ===")
    for idx, item in enumerate(flow_list, 1):
        print(f"{idx}. {item['title']}  | ID:{item['entity_id']}")
    print("======================")
    sel = input("输入要删除的流程序号：").strip()
    if not sel.isdigit():
        print("输入无效")
        client.close()
        return
    sel_idx = int(sel) - 1
    if sel_idx < 0 or sel_idx >= len(flow_list):
        print("序号超出范围")
        client.close()
        return

    target_ent = flow_list[sel_idx]
    confirm = input(f"确认删除流程【{target_ent['title']}】？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消删除")
        client.close()
        return

    # 软删除
    client.delete_entity(target_ent["entity_id"], hard=False)
    print(f"流程 {target_ent['title']} 删除完成（软删除，可恢复）")
    client.close()


def main_loop():
    while True:
        show_menu()
        opt = input("请输入功能数字：").strip()
        if opt == "1":
            record_flow()
        elif opt == "2":
            run_flow()
        elif opt == "3":
            list_all_flows()
        elif opt == "4":
            delete_flow()
        elif opt == "0":
            print("程序退出")
            sys.exit(0)
        else:
            print("输入错误，请选择 0~4 之间数字")
        input("\n按回车返回主菜单...")


if __name__ == "__main__":
    main_loop()
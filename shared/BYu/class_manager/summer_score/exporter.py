import json
import pandas as pd
from pathlib import Path

# 读取 JSON 文件
json_path = Path("D:/data/json/积分.json")
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

ledger = data["ledger"]
group_map = data["group_map"]

# ========== 1. 展开明细数据 ==========
rows = []
for name, info in ledger.items():
    group = group_map.get(name, "未知组")
    for rec in info["records"]:
        row = rec.copy()
        # 缺科列表转为字符串
        if isinstance(row.get("missing_subjects"), list):
            row["missing_subjects"] = ", ".join(row["missing_subjects"]) if row["missing_subjects"] else ""
        row["姓名"] = name
        row["组别"] = group
        rows.append(row)

df_detail = pd.DataFrame(rows)

# 处理空值（数字填0，字符串填空）
df_detail = df_detail.fillna({
    "final_score": 0,
    "attendance_deduct": 0,
    "homework_deduct": 0,
    "morning_early_bonus": 0,
    "homework_bonus": 0,
    "morning_late_deduct": 0,
    "afternoon_chain_deduct": 0,
    "morning_checkin_deduct": 0,
    "afternoon_checkin_deduct": 0,
    "morning_chain_deduct": 0,
    "missing_subjects": "",
    "is_leave": False
})

# 日期排序
df_detail["date"] = pd.to_datetime(df_detail["date"])
df_detail = df_detail.sort_values("date").reset_index(drop=True)
df_detail["date"] = df_detail["date"].dt.strftime("%Y-%m-%d")

# ========== 2. 重命名列为中文 ==========
column_mapping = {
    "date": "日期",
    "姓名": "姓名",
    "组别": "组别",
    "is_leave": "是否请假",
    "final_score": "当日总分",
    "attendance_deduct": "考勤总扣分",
    "homework_deduct": "作业扣分",
    "morning_early_bonus": "早起加分",
    "homework_bonus": "作业加分",
    "morning_late_deduct": "迟到扣分",
    "afternoon_chain_deduct": "下午接龙扣分",
    "morning_checkin_deduct": "上午打卡扣分",
    "afternoon_checkin_deduct": "下午打卡扣分",
    "missing_subjects": "缺科列表",
    "morning_chain_deduct": "上午接龙扣分（遗留）",
}
# 只保留实际存在的列
final_cols = [col for col in column_mapping.keys() if col in df_detail.columns]
# 按你关心的顺序调整（重要字段在前）
order = ["date", "姓名", "组别", "is_leave", "final_score", "attendance_deduct", 
         "homework_deduct", "morning_early_bonus", "homework_bonus", 
         "morning_late_deduct", "afternoon_chain_deduct", "morning_checkin_deduct",
         "afternoon_checkin_deduct", "missing_subjects", "morning_chain_deduct"]
order = [col for col in order if col in df_detail.columns]
df_detail = df_detail[order]
df_detail.rename(columns=column_mapping, inplace=True)

# ========== 3. 保存明细表（Excel） ==========
out_detail = Path("积分明细表.xlsx")
df_detail.to_excel(out_detail, index=False, sheet_name="明细")
print(f"✅ 明细表已保存：{out_detail.absolute()}")

# ========== 4. 生成汇总表 ==========
summary = df_detail.groupby("姓名", as_index=False).agg(
    总天数=("日期", "count"),
    总得分=("当日总分", "sum"),
    平均得分=("当日总分", "mean"),
    考勤总扣分=("考勤总扣分", "sum"),
    作业总扣分=("作业扣分", "sum"),
    早起总加分=("早起加分", "sum"),
    作业总加分=("作业加分", "sum"),
    迟到总扣分=("迟到扣分", "sum"),
)
# 加入组别
summary = summary.merge(
    pd.DataFrame(list(group_map.items()), columns=["姓名", "组别"]),
    on="姓名",
    how="left"
)
# 调整顺序
summary = summary[["姓名", "组别", "总天数", "总得分", "平均得分", 
                   "考勤总扣分", "作业总扣分", "早起总加分", "作业总加分", "迟到总扣分"]]
summary = summary.round(2)

# 保存汇总表
out_summary = Path("积分汇总表.xlsx")
summary.to_excel(out_summary, index=False, sheet_name="汇总")
print(f"✅ 汇总表已保存：{out_summary.absolute()}")
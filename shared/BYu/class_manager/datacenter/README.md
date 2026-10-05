# datacenter — 班级数据中心

> 班级数据（学生总表 / 积分记录 / 编辑请求）的统一管理入口，基于 `GYun.data`（SQLite 实体存储，`source="class_manager"`）。

## 一、这个模块是什么

`datacenter` 负责**班级数据的浏览与管理**，核心是维护一张**学生总表（person）**，并让所有业务数据（积分记录、编辑请求）通过 `related_ids` 与总表中的学生挂钩。

```
src/BYu/class_manager/
├── datacenter/          ← 本模块：班级数据中心（person 总表 + 各类数据浏览/管理）
├── points/              ← 业务：积分识别 / 校验 / 匹配 / 上传（数据落在同一库里）
│   ├── points_store.py  ← 与 datacenter 共用同一数据库，负责 points_record / points_edit 的读写
│   └── ...
```

- **唯一数据源**：所有数据存在同一个 `GYun.data` SQLite 库（`source="class_manager"` 应用隔离）。
- **person 是"不变总表"**：学生信息只维护一份，业务数据只存 `entity_id` 引用，不重复存学生信息。

## 二、实体类型一览

| 实体类型 | 含义 | 谁创建 |
|---------|------|--------|
| `person` | 学生（总表，不变） | datacenter / 初始化脚本 |
| `points_record` | 班务日志识别出的积分记录 | points 模块 |
| `points_edit` | 纸质编辑指令（新增/删除/修改） | points 模块 |

## 三、数据是怎么跟 person 挂钩的

### 1. person（学生总表）— 被引用的"锚点"

```json
{
  "entity_id": "b6e342591e464677a5497cbb120a6790",
  "type": "person",
  "title": "田钊智",
  "content": "田钊智 (TZZ)",
  "source": "class_manager",
  "extra": {
    "name": "田钊智",     // 全名（中文）
    "pinyin": "TZZ",      // 缩写（3-4 位大写字母）
    "student_id": "66",
    "gender": "男"
  },
  "related_ids": [],
  ...
}
```

- `extra.name` / `extra.pinyin` 是**两类查找键**：中文全名 或 大写缩写。
- `entity_id` 是稳定的唯一标识，业务数据只持有这个 id 即可定位到学生。

### 2. points_record（积分记录）— 通过 `related_ids` 引用学生

```json
{
  "entity_id": "a1b2c3d4-...",
  "type": "points_record",
  "title": "早读迟到",               // 事件名
  "content": "[\"ZBY\",\"WGF\"]",     // 人员原始值（JSON 文本，GYun.data content 列为 TextField）
  "source": "class_manager",
  "extra": {
    "id": "2026080701",              // 日期(8位) + 序号(2位)，唯一
    "date": "2026-08-07",
    "score": -1.0,
    "entity_status": "pending_review | pending_match | matched | uploaded",
    "recorder": "HHR",
    "remark": "",
    "error_info": null
  },
  "related_ids": ["b6e342591e464677a5497cbb120a6790", ...],  // ← 学生 entity_id 列表
  ...
}
```

**挂钩方式**：
- `content` 保存识别时的**原始人员值**（如 `ZBY`、`张雨绮`），用于展示和纠错对照。
- `related_ids` 保存解析后的**学生 entity_id**，一个积分事件影响几个人就挂几个学生 id。
- 人员值 → 学生 id 的解析：`points_store.resolve_person_ids()`（先按缩写 `pinyin`、再按全名 `name` 匹配；缩写统一转大写兜底）。

### 3. points_edit（编辑请求）— 两类挂钩

```json
{
  "entity_id": "...",
  "type": "points_edit",
  "title": "A 积极",
  "source": "class_manager",
  "extra": {
    "id": "2026080123",              // 日期+编号
    "operation": "A | D | C",
    "target_seq": "12",              // D/C 引用的目标编号
    "target_entity_id": "...",       // 解析后回填目标 points_record 的 entity_id
    "entity_status": "pending_review | approved | applied | cancelled",
    "error_info": null
  },
  "related_ids": [ ... ]             // 涉及的学生
}
```

- **人员挂钩**：`related_ids` 关联编辑涉及的学生（与 points_record 相同）。
- **目标挂钩**：`D`(删除) / `C`(修改) 通过 `target_seq`（日期+编号）找到目标 `points_record`，校验时回填 `target_entity_id`；`A`(新增) 应用时创建新的 `points_record`。

### 4. 关联关系（文字图）

```
person (学生总表)  ◄── related_ids ──  points_record (积分记录)
     ▲                                 points_edit   (编辑请求)
     │
     └── 解析键：extra.name(全名) / extra.pinyin(缩写)
```

- 每个 `points_record` / `points_edit` 的 `related_ids` 里存的是 `person.entity_id`。
- 反向查询（某个学生被哪些积分记录引用）：`GYunClient.get_referenced_entities(person_id)`。

## 四、常用操作

```bash
# 浏览 / 管理班级数据（person 总表、积分记录、编辑请求）
python -m BYu.class_manager.datacenter.cli
```

- 白名单类型默认含：`person` / `points_record` / `points_edit` 等（`config/class_datacenter.json` 可配）。
- 积分记录、编辑请求的读写由 `points` 模块完成，`datacenter` 提供统一的浏览、查询、统计视图。

## 五、与 points 模块的分工

| 能力 | 归属 |
|------|------|
| person 总表维护 / 浏览 | datacenter |
| 积分识别 → points_record 落库 | points（`recognize_and_store`） |
| 编辑识别 → points_edit 落库 | points（`recognize_edits_and_store`） |
| 校验 / 匹配 / 上传 / 统计 | points（`validate_store` / `match_store` / `upload_store` / `statistics`） |
| 数据浏览 / 查询 | datacenter + points（`query_records` / `query_edits` / `statistics`） |

> 同一数据库、同一套实体模型，`datacenter` 管"总表与视图"，`points` 管"业务流转"。

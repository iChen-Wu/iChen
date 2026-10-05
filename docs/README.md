# iChen 文档索引

这里是 iChen 中枢开发文档（定稿区）。旧文档（v1/v2 时代的架构、契约、日志）已整体归档到
Obsidian：`D:/iChen/data/iChen_Obsidian/项目/归档/iChen旧文档_20261005/`，不再随仓库维护。

| 文档 | 用途 |
|---|---|
| [iChen 项目说明](iChen%20项目说明.md) | 定位、目录结构、三个版本（开发/正式/移动）、开发约定 |
| [App 开发指南](App%20开发指南.md) | **做 App 看这份**：目录模型、manifest、ui/core 协议、自测清单 |
| [正式版更新指南](正式版更新指南.md) | 从工作区更新 D:/iChen 的命令、同步范围与红线 |
| [数据与备份说明](数据与备份说明.md) | 业务数据位置、三版本边界、备份操作与数据红线 |
| [开发记录](开发记录.md) | v3.0.0 起的变更台账（里程碑、关键决策、事故记录） |

## 常用命令

```bash
python -m system.main                    # 启动开发版中枢
python ../workbench/tools/run_tests.py      # 全量测试（工程台在仓库外）
python ../workbench/tools/update_production.py            # 比对正式版差异（不写入）
python ../workbench/tools/update_production.py --apply    # 更新正式版（只换中枢代码）
```

## 给 AI 的一句话

- 在本仓库（中枢开发）改的是 `system/`、`shared/`；工程脚本在仓库外 `../workbench/`，动完跑测试。
- 做 App 时把工作区直接选到 `apps/`，先读 `apps/README.md`，不要改中枢代码。
- 永远不要覆盖正式版 `D:/iChen` 的 `apps/ shared/ data/`。

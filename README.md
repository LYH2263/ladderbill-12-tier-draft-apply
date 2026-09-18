# 12-ladderbill（阶梯电费）

Ladderbill — 居民阶梯电价分段累进（含尖峰系数）

## 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |

## 主链

抄表录入 → 阶梯分段计费 → 账单明细

## 阶梯草稿试算 / 应用

阶梯规则页可保存一份**未生效草稿档**（`tier_drafts` 表），草稿与正式档同时可读：

| 接口 | 说明 |
| --- | --- |
| `GET /api/tiers/draft` | 返回草稿（可能为 null）与当前正式档 |
| `PUT /api/tiers/draft` | 保存草稿序列（编辑期不校验） |
| `POST /api/tiers/draft/trial` | 用探针电量对**草稿**试算：不改正式档、不写运行记录，回包 `source="draft"`、`run_id=null` |
| `POST /api/tiers/draft/preview` | 应用前只读对比，返回同电量的 before/after 分段摘要 |
| `POST /api/tiers/draft/apply` | 草稿通过**单调上界 + 非负单价**校验后，单事务原子替换正式档并清除草稿；返回应用前后分段对比。校验失败返回 422 且旧正式档不变 |

应用成功后，测算台 `/api/bill`（读正式档）对同一探针电量的分段与应用后摘要完全一致。


## 技术栈

Python 3.12 + FastAPI + SQLite；Vue 3 + Vite + Nginx。

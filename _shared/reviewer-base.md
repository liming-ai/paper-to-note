# Reviewer Base Rules

`paper-to-note-reviewer.md` 与 `paper-to-skill-reviewer.md` 的 sub-reviewer 都遵守此规则。

## 输出格式

每个 sub-reviewer 发现的问题按下面格式列出：

```
ISSUE: <description of the problem>
LOCATION: <line number or section heading>
FIX: <specific fix with evidence>
SEVERITY: P0 | P1 | P2
REVIEWER: <sub-reviewer name, e.g. Format | Content | SourceCode | ImplementationCompleteness | CodeReferenceAccuracy | PortingFeasibility>
```

Coordinator 汇总后最终输出：

- `APPROVE` — 无 P0 也无 P1 问题（P2 可选修复）
- `REQUEST_CHANGES` — 有至少一个 P0 或 P1 问题，按 SEVERITY 降序输出所有 issue

## 严重度定义

| 级别 | 定义 | 举例 |
|---|---|---|
| P0 | 事实错误 | 数字错、函数名错、commit SHA 不存在、行号完全不对、路径不存在 |
| P1 | 结构性缺失 | 必填 section 缺失或空、伪代码基于论文而非真实代码、commit anchor 未记录 |
| P2 | 可读性/一致性/风格 | 格式不一致、措辞不当、图注缺失、可选 section 可加强 |

## 迭代规则

- 最多 3 轮
- 第一轮全 APPROVE → 立即通过，不做冗余二次确认
- 同一 LOCATION 的同类问题第 2 次出现 → 严重度升一级
- 3 轮后仍有 P0 → Coordinator 仍输出 `REQUEST_CHANGES` + 完整 issue list，但允许交付：
  - 将未修复 P0 写入产物同目录的 `.review-log.md`（`paper-to-note` 笔记同级；`paper-to-skill` skill 根目录）
  - 向用户返回 review log 路径 + P0 摘要，由用户决定是否强制交付
  - 不自动回滚已写入的文件

## Coordinator 合并规则

1. sub-reviewer **并行** 执行（Agent tool 多个 call 同一 message）
2. Coordinator 收到所有 sub-reviewer 输出后：
   - 合并所有 issue list
   - 按 SEVERITY 降序排序（P0 → P1 → P2）
   - 同一 LOCATION + 同类描述的 issue 去重
   - 不同 LOCATION 的相似 issue 合并为 "多处出现" 汇总 issue
3. 输出最终 `APPROVE` 或 `REQUEST_CHANGES + 排序后的 issue list`

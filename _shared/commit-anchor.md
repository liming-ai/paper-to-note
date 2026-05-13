# Commit Anchor 规范

两个 skill 都依赖准确的 commit SHA 来锚定伪代码和行号引用，避免代码更新后引用失效。

## 格式

| 场景 | 格式 | 示例 |
|---|---|---|
| 内联引用 | `<branch>@<short_sha>` | `main@abc12345` |
| 带日期引用 | `<branch>@<short_sha> (YYYY-MM-DD)` | `main@abc12345 (2026-04-21)` |
| 短 SHA | git commit hash 的前 8 位 | `abc12345` |

## 获取命令

```bash
gh api repos/<owner>/<repo>/commits/HEAD --jq '(.sha[:8]) + " (" + .commit.author.date[:10] + ")"'
```

输出示例：
```
abc12345 (2026-04-21)
```

如果是 default branch 以外的 branch：
```bash
gh api repos/<owner>/<repo>/commits/<branch-name> --jq '(.sha[:8]) + " (" + .commit.author.date[:10] + ")"'
```

## 存储位置

### `paper-to-note`
- Obsidian frontmatter property `github_ref`，值为 `<branch>@<short_sha>`（不含括号日期）
  ```yaml
  github_ref: main@abc12345
  ```
- 代码映射表前的 blockquote header 写完整日期版：
  ```
  > **Code reference**: `main` @ `abc12345` (2026-04-21) — pseudocode and mapping based on this commit
  ```

### `paper-to-skill`
- `sources.json` 的 `repos[].commit_anchor` 字段，值为完整日期版：
  ```json
  {"commit_anchor": "main@abc12345 (2026-04-21)"}
  ```
- `skill.md` 首节 `## Source & Commit Anchor` 的 Source 表中 `Commit` 列。

## 强制规则

- **失败条件**（reviewer 会判为 P0 或 P1）：
  - `paper-to-note` 产物缺少 Obsidian frontmatter `github_ref` 属性，或缺少代码映射表前的 `> **Code reference**: ...` blockquote header
  - `paper-to-skill` 产物缺少 `sources.json` 中 `repos[].commit_anchor` 字段，或缺少 `skill.md` 首节 `## Source & Commit Anchor` 的 Source 表 Commit 列
- **触发 reviewer**：`paper-to-note` Pitfall P5、`paper-to-skill` Reviewer B 都按上述条件执行检查
- 无开源代码的论文：写 `N/A (no public code)` 而非省略

# Known Categories & Naming Conventions

## Obsidian 分类（`paper-to-note`）

笔记存放位置：`$VAULT_PATH/notes/<Category>/<PaperTitle>.md`

已知分类：

- `RL for Visual Generation`
- `Video Generation`
- `World Model & Long Video Generation`
- `Multi-Modal Generation`
- `Visual Understanding`
- `VLA`
- `Diffusion Acceleration`
- `RL for LLM & VLM`
- `Agent Memory`

新建分类前，先用 `obsidian-cli` 查询实际存在的目录；如果没有安装该 CLI，也可以直接 `ls $VAULT_PATH/notes/`：

```bash
obsidian vault="paper_notes" folders folder="notes"
```

## paper-to-skill Skill 命名规范

产物路径：`$SKILLS_DIR/<skill-name>/skill.md`

### 命名规则

| 场景 | 格式 | 示例 |
|---|---|---|
| 单论文 | 方法名 kebab-case | `flow-grpo`、`diffusion-nft`、`mamba` |
| 综合手册 | 主题 kebab-case | `long-video-gen`、`rl-for-visual-generation` |
| 框架文档 | 框架名小写 | `accelerate`、`diffusers-training` |

### 禁止

- 使用 PaperTitle 原样（含空格、大小写混用、特殊字符）
- CamelCase（`FlowGRPO` → `flow-grpo`）
- 含日期后缀（`flow-grpo-2024` → `flow-grpo`）

### 已存在的 skill

查询命令：
```bash
ls $SKILLS_DIR/
```

# Known Categories & Naming Conventions

## Obsidian 分类（`paper-to-note`）

笔记存放位置：`paper_notes/notes/<TopCategory>/<SubCategory>/<PaperTitle>.md`
图片存放位置：`paper_notes/files/<TopCategory>/<SubCategory>/<PaperTitle>/`

> 当前 macOS vault 路径：`/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/`。部分 runtime 也可能通过 `/Users/bytedance/OneDrive/paper_notes/` 访问同一个 vault。

### 当前多层分类

```text
Agent
├── Agentic Systems & Applications
├── Memory
├── Personalization
└── RL
LLM & VLM
├── Pretraining & Architecture
├── Long-Context & Streaming
├── RL & Post-Training
├── Evaluation & Analysis
└── Theory
Multimodal Generation
├── Pretraining & Architecture
├── Video & Audio-Video Generation
├── Acceleration & Distillation
├── RL & Alignment
└── Reasoning & Test-Time Scaling
World Model
├── Long-Horizon Generation
├── Real-Time & Streaming
├── Interactive & Controllable
└── 3D & Multi-View Simulation
Physical AI
├── VLA & World-Action Models
├── Robot Data & Manipulation
├── Physical Video Generation
└── Embodied & Driving Simulation
```

### 分类规则

- 每篇论文选择一个主分类：`<TopCategory>/<SubCategory>`。
- 先查询实际存在目录，再决定是否新建子类；这个 taxonomy 可能经常变化，不要依赖旧的扁平目录名。
- 子类名不要重复父类名：例如在 `LLM & VLM` 下用 `Pretraining & Architecture`，不要写 `VLM Pretraining & Architecture`。
- frontmatter `tags` 必须包含一个层级分类 tag：`paper/<top-slug>/<sub-slug>`，并保留具体技术 tag。
- 迁移后不再使用旧分类 tag：`visual-understanding`、`rl-for-visual-generation`、`world-model-long-video-generation`、`multi-modal-generation`、`diffusion-acceleration`、`rl-for-llm-vlm`、`agent-memory`。

查询实际目录：

```bash
obsidian vault="paper_notes" folders folder="notes"
find "/Users/bytedance/Library/CloudStorage/OneDrive-个人/paper_notes/notes" -maxdepth 2 -type d | sort
```

## paper-to-skill Skill 命名规范

产物路径：`~/ai-skills/skills/<skill-name>/skill.md`

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
ls ~/ai-skills/skills/
```

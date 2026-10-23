# 來源標註

本技能的流程骨架（八階段編劇流程、劇本格式規範、審閱清單結構）改寫自：

**[POUND0423/AI-drama-pound](https://github.com/POUND0423/AI-drama-pound)** — `ai-short-drama-screenwriter`，MIT License，v0.1.0（2026-08-26）。

## 本專案的改動

| 項目 | 原版 | 本版 |
|:---|:---|:---|
| 平台 | OpenAI Codex（`~/.agents/skills/`） | Claude Code（專案內 `.claude/skills/`） |
| 畫面比例 | 豎屏 9:16 | **預設 9:16 直式（Shorts），可指定 16:9** |
| 篇幅結構 | 8–12 集連續短劇 | **單支 1–3 分鐘；系列作每集獨立成篇** |
| 角色 | 每次從零設計 | **固定主角山獅霸**，引用專案 Character Bible |
| 技術限制 | 無 | **本機 MiniMax H3 可行性檢查**（每鏡 ≤12 秒、一鏡最多 3 位說話者（各給參考音）、畫面字由首幀畫好） |
| 階段數 | 8 | **9**（新增〈片段切分與素材備料〉） |
| 新增檔案 | — | `references/segmentation.md`、`references/table-read.md`（生成前試映）、`references/drama-hooks.md`（抓馬上位模式） |
| 新增流程 | — | 主題錨點、觀眾預期曲線、情緒流、因果鏈、人物五面向、階段關卡、生成前試映（2026-10-12） |

原專案的 `agents/openai.yaml` 未沿用（Claude Code 不使用該格式）。

## 原作授權全文

見同資料夾 `LICENSE-AI-drama-pound.txt`（MIT，Copyright (c) 2026 POUND0423）。

# 唱詞歌範本：YuE2「14 版」（本機唱詞歌的主要範本）

> **歌曲（有人聲）生成順序（2026-10-27 實測後定案）**
> 1. **Suno**（例如經 Kie.ai 的 API）：有帳號就用它。編曲最豐富、rap 最有攻擊性，還會有刷碟聲。
> 2. **YuE2 14 版（本範本）**：沒有 Suno 帳號時，**先問使用者**要不要改用本機 YuE2，不要自己換。要變體就從 14 版改。
> 3. **ACE-Step 1.5 XL**（`tools/ace_song.py`）：Plan C。拍速最穩，歌可以用，但人聲帶金屬聲。
>
> 純配樂（不唱詞）仍用 MiniMax Music 3（`tools/gen_music3.py`）。

這個配方是在 RTX 5090、ComfyUI 0.40 上，用一首中文饒舌對決（牛頓 vs 萊布尼茲）試了 13 種以上做法後，製作人聽過選出來的。
同一場試做也記下了失敗的做法：
- 自己寫 ABC 譜：拍速鎖得住，但編曲太平。
- 翻唱參考歌：拍速對，但跟原歌還有一段差距。
- full／off 規劃模式：拍速亂跳。
- 段落之間留空檔，想讓 DJ 刷碟：反而比較差。

## 配方
| 項目 | 設定 |
|:--|:--|
| 模型 | ComfyUI 原生 YuE2，`yue2_3b_int8_convrot.safetensors`（`setup/downloads_yue2.json`）；bf16 沒有明顯較好 |
| 規劃模式 | **melody**：YuE2 只規劃人聲旋律，伴奏自由發揮 |
| 風格 | 英文逗號標籤，**語言放第一個**（越前面影響越大），依序寫：Chinese → rap → boom bap battle rap → **DJ scratching, vinyl record scratches, turntablism** → aggressive rapid-fire rap flow, staccato punchy delivery → 聲音 → 鼓與 808 → 一個招牌取樣樂器 → 氣氛 → BPM。範例 `style_A_deep_raspy.txt`、`style_B_bright_sharp.txt` |
| 歌詞 | 每段 4 句、段落標籤大寫、段落之間空一行：`[Verse]`×2 → `[Pre-Chorus]`（2 句）→ `[Chorus]`（最狠的句子）；有反轉再接 `[Bridge]` → `[Chorus]`。不要放空的 `[Intro]`／`[Interlude]`。範例 `lyrics_example_*.txt` |
| 抽數 | **每首抽 10–12 個 seed**。約一半會掉到 89 BPM 或跳到 152，只留 143.6 的，再用逐句聽寫挑 |

## 指令
```
python tools/yue_song.py <名稱> <角色> --style templates/song_yue2_v14/style_A_deep_raspy.txt --lyrics 我的歌詞.txt --out work/song_A
<Voice venv>/python tools/pick_song.py work/song_A 我的歌詞.txt
```
- 先開 ComfyUI（`tools/start_comfy.cmd`）。在 5090 上每首約 12–30 秒，12 首約 5 分鐘。
- `pick_song.py` 會跳過拍速不對的歌，其餘依逐句聽寫排序，寫進 `pick.json`。
- **不要整首直接聽寫**：rap 會讓聽寫幻覺出「中文字幕志願者」之類的字。
- rap 的聽寫分數天生偏低，人工確認全對的 Suno 歌也只量到 0.63–0.70。**最後一定要人聽。**

## 做變體時改哪裡
- **換曲風**：只換取樣樂器、鼓型（boom bap／trap／drill）和氣氛詞。Chinese、rap、DJ scratching、連珠炮 flow 要留在前段。
- **換聲音**：只改「male rapper, … voice」那一組。兩人對決時，每人用不同聲音描述，**各生一首**。同一首歌裡要求兩種聲音，出來會是同一個人。
- **換速度**：改風格最後的 BPM，`pick_song.py` 加 `--bpm`，填 librosa 實際量到的值。
- **做不到的**：刷碟聲不一定每首都有，因為 ABC 譜寫不進去，需要的話後製補。攻擊性和韻律感仍比 Suno 弱。

## 授權
YuE2 權重是 CC BY-NC 4.0，不能商用。要營利就改用 Suno（看你的方案條款）或 ACE-Step（MIT）。

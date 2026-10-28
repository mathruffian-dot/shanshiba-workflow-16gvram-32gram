# template_battle：饒舌對決範本（兩首歌 → 3–4 分鐘橫式對決影片）

兩位真實人物各唱一整首歌互嗆、DJ 主持、最後留言投票。`battle.json` 寫完整場（人物、歌詞、DJ 口白、擂台、閃回地點、字卡、每一鏡），`make_battle.py` 從兩首歌一路做到成片、手機版和自審。

**先讀編劇技能 `agent/skills/rap-battle/`**：選題、歌詞規則、生歌（Suno 為主、沒有 Suno 用 YuE2）、鏡表寫法、自審表都在那裡。

範例 `battle.json`＝原頻道〈微積分之戰〉牛頓 vs 萊布尼茲（2026-10-28，49 鏡、約 3 分 9 秒）。範本不附歌曲檔（Suno 生成），要跑範例請先用 `songtext` 的文字自己生兩首。

## 用法

1. 把整個 `template_battle/` 複製一份到 `pipeline/` 底下改名（例如 `pipeline/my_battle/`）。放在別的地方的話，把 `battle.json` 的 `repo_dir` 改成本 repo 根目錄（可以寫絕對路徑）。
2. 照技能寫好設計與歌詞，填進 `battle.json`（欄位見下）。
3. 生歌：
   ```
   <Voice venv>\python make_battle.py songtext
   ```
   - **有 Suno**：把 `out/songtext/suno_A_lyrics.txt`、`suno_A_style.txt` 貼到 Suno 網頁的 Custom 模式（B 同理），或用 `python kie_suno.py submit A`（環境變數 `KIE_API_KEY`）。
   - **沒有 Suno**：照 `templates/song_yue2_v14/README.md` 用 `out/songtext/yue_*` 跑 `tools/yue_song.py`＋`tools/pick_song.py`。
   - 挑好的歌放成 `song/A.mp3`、`song/B.mp3`（或改 `rappers.<A|B>.song`）。
4. 在同一個 cmd 視窗：
   ```
   set PYTHONUTF8=1
   call <repo>\configs\profile.cmd
   C:\AI\tools\start_comfy.cmd
   cd <repo>\pipeline\my_battle
   C:\AI\Voice\venv\Scripts\python.exe make_battle.py songs dj audio
   ```
   看 `out/song/songs_report.json`：逐句聽寫低分的句子去聽；`last_word_end`（最後一個字唱完）不對就在 `battle.json` 填秒數重跑。聽 `out/audio/mix.wav` 確認 A→B 的接點和 DJ 口白。
5. `make_battle.py chars scenes frames` → **人工關卡 1**：`out/chars/`（三人分得出來）、`out/scenes/arena.png`（配色、沒有字和旗子）、`out/first/_sheet.jpg`（每鏡首幀）。重畫：刪那張 png，那鏡加 `frame_seed_bump` 或改 `frame`，再跑 `frames`。
6. `make_battle.py specs h3` → **人工關卡 2**：`out/review/clips_*.jpg`（每鏡 4 格：換臉、多出人、旗子、自己切鏡、手糊）。重拍：那鏡加 `seed_bump`（會切鏡的再加 `last_first: true`），再跑 `specs h3`。
7. `make_battle.py cut review srt` → **人工關卡 3**：照技能的 `references/review-checklist.md` 看 `out/review/fc_v1/sheet_*.jpg`，**最後一定要人看完整成片** `out/cut/<片名>_v1_1920x1080.mp4`。改版：`--ver 2`。

不給 stage 就從 `songs` 依序跑到 `srt`。已存在的輸出會跳過，中斷後重跑會接著做。還沒跑 H3 的鏡，`cut` 會用首幀靜態圖代替（沒有首幀就用灰底鏡號），可以先看節奏。

| 環境變數 | 用途 |
|---|---|
| `AI_ROOT`、`AI_TOOLS` | 安裝根目錄（預設 `C:\AI`）、工具目錄（預設 `C:\AI\tools`） |
| `COMFY_DIR` | ComfyUI 資料夾（`gen_image.py` 從它的 `output/` 拿圖） |
| `H3_BACKEND` | `local`｜`colab`｜`both`（同 template_local；不設就看顯卡自動選） |
| `UPSCALE` | `rtxvsr`（Windows 預設）｜`lanczos`（Linux／Colab） |
| `ONLY` | 只做這幾鏡（`frames`、`h3`），例如 `set ONLY=N04 L06` |
| `ALLOW_REVIEW=1` | DJ 口白 8 個候選聽寫都不準、但人聽過沒問題時繼續 |
| `FONT_JHBD`、`FONT_KAI` | 字幕／字卡字型（預設微軟正黑體／標楷體，Linux 用 Noto CJK） |

## battle.json 欄位

| 欄位 | 說明 |
|---|---|
| `title` | 片名（片名卡、成片檔名） |
| `image_backend` | `qwen`（預設，本機 Qwen-Image 2.1／Qwen-Image-Edit 2511，最多 3 張參考圖）或 `img25`（OpenAI Image 2.5，`tools/img25.py`，要金鑰，最多 5 張） |
| `seed0` | H3 seed 的起點（每鏡再依鏡號加） |
| `rappers.A/B` | `name`、`short`、`team`（例：金方）、`tagline`（VS 卡小字）、`color`／`glow`（字幕、特效、字卡的己方顏色 RGB）、`look`（外觀完整描述，每張首幀照抄）、`person`（man／woman）、`pronoun`、`desc`（H3 用的短描述）、`song`、`suno_style`、`suno_negative`、`yue_style`、`lyrics`（見技能 `references/lyrics.md`）、`intro_card`（直排名牌 `[[文字, 字級], …]`）、`last_word_end`（選填） |
| `dj` | `name`、`short`（字幕名）、`color`、`look`、`desc`、`person`、`pronoun`、`voice_design`（Breeze 設計聲音的描述）、`voice_sample`（設計時念的句子）、`lines`（`open`／`switch`／`verdict`（選填）／`end`）、`end_beats`（片尾三拍大字）、`tts`（選填，念錯的句子改寫法）、`intro_card` |
| `arena` | `master`（擂台空景提示詞，左右兩半＝兩人的配色）、`keep`（首幀用的擂台鎖定句，`{ref}`＝參考圖編號）、`light`、`setting`／`style`／`keep_h3`（H3 用） |
| `places.<地點>` | 閃回／插入鏡的地點：`light`（首幀光線）、`setting`（H3）、`era`（`period`／`modern`）、`text`（畫面裡有要保持不變的字） |
| `style_modern`、`style_period`、`film_look`、`no_text` | 插入鏡的 H3 風格句、首幀電影感句、不要字的句子 |
| `audience`、`audience_desc` | 觀眾外觀（首幀）、H3 短描述 |
| `cards.<代號>` | 講白字卡：`lines`（`[[文字, 顏色]]`，顏色 `A`／`B`／`J`／`ink`）、`accent`、`size`；或 `image`（自己畫好的 PNG，例如精準的數學圖） |
| `vote` | 投票卡：`A`、`B`（挺誰打什麼字）、`title`、`sub`、`note` |
| `show_replace` | 歌詞→字幕的替換表（國字數字→阿拉伯數字、同音字→原字） |
| `flash_scenes` | 切進這些地點時閃白（其他插入鏡直接切） |
| `locked` | 鏡頭鎖死不推近的鏡號 |
| `crowd_sfx` | 觀眾歡呼音效資料夾（預設 `sfx/歡呼`） |
| `shots[]` | 每一鏡，見下表 |

每一鏡（`shots[]`）：

| 欄位 | 說明 |
|---|---|
| `id` | 鏡號 |
| `at` | 開始時間：秒數｜`["A", i]`（A 第 i 句開口前 0.12 秒）｜`["dj", "switch", -0.3]`｜`["mark", "a_stop", 0.3]`（`a_first`、`a_stop`、`a_end`、`b_zero`、`b_first`、`b_last`、`music_end`）。結束＝下一鏡的開始 |
| `kind` | `sing`（對嘴；`voice: "dj"`＝對 DJ 口白）或 `silent` |
| `scene` | `arena` 或 `places` 的地點 |
| `subj` | 畫面裡的人：`A`、`B`、`K`（DJ）、`T`（觀眾）。**只放畫面裡要演戲的人**；雙人鏡第一位是唱的人 |
| `dist` | `ECU`／`CU`／`MCU`／`MS`／`WIDE` |
| `frame` | 首幀描述（英文，畫動作開始前的姿勢） |
| `action` | H3 動作（`Starting from <Picture 1>, …`，慢而清楚的手勢） |
| `gfx`、`card` | 這鏡要疊的字卡代號、直排名牌（`A`／`B`／`K`） |
| `still`、`custom` | 首幀靜態慢推、自己做的影片檔 |
| `last_first`、`calm`、`draft`、`cons`、`seed_bump`、`frame_seed_bump` | 尾幀＝首幀（防切鏡）、慢動作、`false`＝14 步、額外限制句、換 H3 seed、換首幀 seed |

## 輸出（`out/`）

`songtext/` 生歌用文字、`song/` 分軌＋對齊＋報告、`voice/` DJ 參考音與口白、`audio/` 全片音軌（`mix.wav`、`vocals.wav`、`dj.wav`、`timeline.json`）、`chars/`、`scenes/`、`first/`（首幀＋提示詞＋接觸表）、`h3/<鏡>/`（spec、clip）、`post/`（放大、片段、字卡、特效事件）、`cut/`（成片、手機版、字幕檔）、`review/`、`timing.json`。

## 驗證紀錄

2026-10-28～29，RTX 5090 32GB，用原頻道〈微積分之戰〉的兩首 Suno 歌（牛頓 vs 萊布尼茲）＋本資料夾的 `battle.json`，從 `songs` 一路跑到 `srt`，首幀用本機 Qwen-Image-Edit 2511（`IMG=qwen`）。

**做出來的東西**：186.3 秒 1920×1080 成片＋27.2 MB 手機版＋srt，49 鏡（43 鏡 H3、其餘字卡／靜態），−16.0 LUFS、AAC 後真峰值 −2.1 dBTP。

| 階段 | 時間 | 備註 |
|---|---|---|
| songs | 27 秒 | 分軌、對齊、逐句聽寫；最後一字的時間跟原片手工挑的差 0.05／0.26 秒 |
| dj | 數分鐘 | BreezyVoice 每句 8 個候選；見下方「DJ 關卡」 |
| audio | 數秒 | A 停在 77.717 秒、B 從 79.179 秒、音樂到 174.784 秒，**跟原片手工剪的完全一致** |
| chars＋scenes | 約 2 分 | |
| frames（43 張） | 每張中位數 48 秒 → 約 35 分 | 實測 3.7 小時是因為同時有別的程式（Breeze TTS）佔顯存，最慢一張 1 小時 53 分。**跑 frames／h3 時不要同時跑別的 GPU 工作** |
| h3（43 鏡，DMAD 4 步） | 49 分（平均約 69 秒／鏡） | |
| cut | 約 11 分 | RTX VSR 放大＋特效逐格疊字（佔大部分時間） |
| review | 44 秒 | |

**實測發現、已修進程式的：**

- 最後一字時間：Suno 會在最後一句後面加觀眾喊聲，用「人聲還有聲音」判斷會多算 14 秒 → 改成對齊的最後一字＋最多延長 0.3 秒。
- 首幀用 Qwen 時，擂台參考圖要放**第一張**，不然雙人鏡會畫在灰色攝影棚。
- 響度：加了觀眾聲以後要再量一次 → 量 → 固定增益 → 限幅迴圈到 −16 LUFS。觀眾音效裡的拍手尖峰可達平均值的 13 倍，限幅器擋得住取樣峰值，但壓成 AAC 後真峰值衝到 +4.2 dBTP → 觀眾音效先軟壓到平均值的 4 倍，修後 −2.1 dBTP。
- 首幀「臉比角色多」自動警告（Qwen 會在單人鏡多畫一個人；這次抓到 N05、L08，另外 F01、F03 是劇情本來就有旁人）。

**本機 Qwen 首幀的已知限制（人工關卡 1 要看）：**

- 雙人對峙鏡（D01–D03）兩人都面向鏡頭並肩站，畫不出側臉互瞪；要對峙感就用 `IMG=img25`，或改成兩個單人鏡對切。
- 偶爾把首幀畫成左右兩格拼圖（L06），H3 會照著演成分割畫面 → 刪掉重畫。
- 場景裡的字（書名、議會橫幅）是亂碼 → 首幀描述別要求寫字，要字就後製字卡。
- 道具會在第一格出現、之後消失（N02 的三角帽）→ 首幀別放這鏡用不到的配件。

**H3 自審**：`review` 的「構圖漂走」清單 21 鏡，大多是唱歌鏡的手勢與走位誤報；真的有問題的是 T03（觀眾鏡中途溶接到另一個舞台約 1 秒）和 L09（側面轉成正面），兩個都在清單裡。硬切（相鄰格差 > 門檻）這次 0 鏡。

**DJ 關卡**：DJ 口白用 BreezyVoice 念，「微積分」被聽寫成「我積分／為積分／危機分」，8 個候選都沒過，`dj` 階段照設計停下來。確認是 ASR 聽錯而不是念錯後，用 `ALLOW_REVIEW=1` 繼續。你自己的片遇到時，先聽那一句；真的念錯就在 `dj.tts` 標注音或換說法。

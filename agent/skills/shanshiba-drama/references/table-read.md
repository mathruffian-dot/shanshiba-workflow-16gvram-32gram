# 生成前試映：16 宮格分鏡草圖＋讀本

> 目的：在首幀與 H3 之前，先讓使用者**看到故事、聽到節奏**，抓出「節奏太快」「轉折沒交代」「片長超標」。
> 試映素材只給使用者內部看聽，不上片。檔案放 `<片資料夾>/preview/`：`storyboard_<k>.png`、`storyboard_<k>_label.png`、`讀本.wav`、`讀本_timeline.json`、`讀本試映.mp4`。
> 原頻道實測：一支 27 鏡的 Shorts，草圖約 3 分鐘、讀本配音約 10 分鐘、組成試映影片 1 分鐘；使用者聽完把 99.7 秒刪到 88.6 秒才進首幀。

## 0. 先把鏡表寫成 `preview/shots.json`

兩支工具共用同一份檔案（欄位說明也在兩支工具的開頭）：

```json
{
  "cast": "Characters (keep consistent across panels): TEACHER = ...; KID = ...",
  "shots": [
    {"id": "S01", "sec": 3, "panel": "extreme close-up: a boy thrusts a phone at the camera",
     "lines": [{"wav": "../vo/bv/AF_S01.wav", "caption": "阿福：老師！颱風轉過來了！"}]},
    {"id": "S02", "sec": 2.5, "panel": "the whole class jumps up cheering",
     "lines": [{"caption": "（全班歡呼）喔——！"}]}
  ],
  "end_card": "你的頻道名"
}
```

- `panel`：給草圖用的一句英文畫面描述（誰、在哪、做什麼、景別）。
- `lines`：有 `wav` 的是台詞音檔；沒有 `wav` 的只當字幕顯示（群眾聲、音效、字卡說明）。
- `sec`：鏡表秒數；有台詞的鏡實際長度＝max(鏡表秒數, 台詞總長＋前 0.25＋句間 0.3 秒)。

## 1. 16 宮格分鏡草圖（`tools/make_storyboard.py`）

```
python tools/make_storyboard.py <片資料夾>/preview/shots.json
```

- 每 16 鏡一張 4×4（27 鏡就是 2 張），多張同時生成。用 `tools/img25.py`（OpenAI Image 2.5，要 `OPENAI_API_KEY`）。沒有金鑰就跳過草圖，第 3 步的試映影片會只有字幕（片長量法不變）。
- 提示詞是「鉛筆草圖＋淡水彩、每格一鏡」，**不叫模型在格子裡寫字**（會寫錯）；畫好後用 PIL 在每格左上角疊鏡號。
- **不附角色參考圖**——只看故事順序與構圖，不驗角色像不像。交給使用者時要說明「這是看節奏用的草圖，不是首幀」。

## 2. 讀本配音

- 每句台詞一個 job，用該角色**定稿參考音**（`ref_audio`＋`ref_text`）。讀本求快，每句 2–3 個 seed 就好。
- 預設 BreezyVoice：`tools/make_breezyvoice.cmd jobs.json`（格式見 `tools/breezyvoice_batch.py` 開頭）。有裝 Breeze TTS 2 也可用 `tools/breeze_batch.py`（**Breeze TTS 2 產出不可營利**，讀本只內部聽沒關係）。
- **念錯的字一定要修**：讀本是使用者第一次聽到台詞，念錯會被當成劇本問題。
  - 例：Breeze 會把「颱風」的「颱」念成四聲（像「泰」），連「台風」也一樣 → 配音輸入寫「**抬**風」（字幕照原字）。「防災」被念成「放發」→ 輸入「防**栽**」。
  - 聽寫（ASR）只驗字、不驗聲調：關鍵字要量音高曲線（`tools/pron_check.py`），二聲要「從低處上揚」，判 unsure 就當不合格。
  - 修過的讀音記進你自己的讀音修正表，下一支片先查。
- 配音工具若用名稱快取（同名候選會跳過），換了輸入文字要**換 job 名稱**，不然拿到的還是舊音檔。

## 3. 組成試映影片（`tools/assemble_read.py`）

```
python tools/assemble_read.py <片資料夾>/preview/shots.json
```

- 照鏡表排時間軸 → `讀本.wav`＋`讀本_timeline.json`（每鏡起訖秒數）＋`讀本試映.mp4`（720×1280，分鏡草圖跟著讀本一格一格切換，下方是台詞字幕）。
- 回報：**實測總長 vs 目標**、最長的三鏡、超出鏡表秒數的鏡、超過 12 秒的鏡（要拆）。

## 4. 給使用者的試映包

- 試映影片＋兩張草圖＋一張表（鏡號／秒數／台詞），標出你自己覺得可能太快、沒講白、念得怪的地方，請使用者聽的時候特別注意。
- 超長就**刪台詞或併鏡**，不要加速。
- 使用者說「通過」才進首幀；改劇本後只重做有改動的鏡（草圖可沿用舊格子，鏡號另外對照）。

# Wolf-man-kill (狼人殺 Discord Bot)

一個基於 `discord.py` 開發的非同步多人狼人殺 Discord 機器人。本專案支援真人玩家與 AI 虛擬玩家（基於 Ollama 大語言模型）混合對局，具備全自動的日夜流程切換、發言佇列控制，並能在遊戲開始時自動透過 Pillow 生成專屬數字頭像私訊玩家。

---

## 核心特色

1. **AI 混合對玩**：
   - 實作與 Discord `Member` 相容的 `AIPlayer`（鴨子型別），無縫支援真人與 AI 玩家同場競技。
   - AI 虛擬玩家可參與夜晚的特殊角色行動、白天的發言階段以及投票決策。
   - 採用 Batch 投票決策機制，減少 API 呼叫次數。

2. **全自動流程管理**：
   - 自動進行日夜切換，控制頻道發言權限（夜晚自動禁言，白天依序解禁）。
   - 白天自動依發言佇列依序開放發言，支援 `/done` 結束發言。
   - 自動結算死亡、亡語（如獵人開槍、狼王技能等）以及判定遊戲勝負。

3. **動態板子配置與快取**：
   - 支援 6 至 12 人的標準板子。
   - 當人數非標準時，自動呼叫 LLM 進行動態平衡板子設計；若失敗則進行降級處理。
   - 具備快取機制，使用安全原子寫入（Atomic Write）更新快取檔案，避免損壞。

4. **圖形化組件**：
   - 遊戲啟動時自動使用 `Pillow` 繪製附有編號的玩家頭像並發送私訊，確保玩家知曉自己的號碼。

---

## 專案結構說明

```text
Wolf-man-kill/
├── src/                      # 核心程式碼目錄
│   ├── bot.py                # Discord Bot 進入點，定義 Slash 指令與日夜遊戲流程
│   ├── game_engine.py        # 遊戲引擎核心，處理遊戲邏輯、死亡結算與勝負判定
│   ├── game_models.py        # 狀態資料結構（GameState）、玩家清單與 AIPlayer 鴨子型別
│   ├── ai_manager.py         # 大語言模型（Ollama）連接層，封裝非同步 API 與快取機制
│   └── utils.py              # Logger 與輔助工具
├── tests/                    # 單元測試目錄
│   ├── conftest.py           # 測試用的 fixtures 配置
│   ├── test_game_engine.py   # 測試遊戲引擎邏輯
│   └── test_game_models.py   # 測試玩家資料模型
├── wolf_man_kill_spec.md     # 專案技術規格書與重建指南
├── requirements.txt          # Python 相依套件
├── .env.example              # 環境變數設定範例
└── README.md                 # 本說明文件
```

---

## 安裝與環境設定

為了確保開發環境的乾淨，建議使用 Python 虛擬環境（Virtual Environment）進行套件安裝。

### 1. 建立並啟動虛擬環境

* **Windows**:
  ```powershell
  # 建立虛擬環境
  python -m venv venv

  # 啟動虛擬環境
  .\venv\Scripts\activate
  ```

* **Linux / macOS**:
  ```bash
  # 建立虛擬環境
  python3 -m venv venv

  # 啟動虛擬環境
  source venv/bin/activate
  ```

### 2. 安裝相依套件

在啟動的虛擬環境中，安裝 `requirements.txt` 中的套件：
```bash
pip install -r requirements.txt
```

### 3. 設定環境變數

將 `.env.example` 複製為 `.env`，並填入您的認證與伺服器資訊：

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS (Terminal)
cp .env.example .env
```

打開 `.env` 檔案並填寫：
```env
DISCORD_TOKEN=your_discord_token_here
OLLAMA_HOST=http://localhost:11434
```

---

## 啟動與執行

1. **啟動 Ollama 服務**：
   確保您的 Ollama 正在運行，並且已經拉取了對應的模型（預設使用 `gemma4:latest`，亦可在 `src/ai_manager.py` 的建構子中修改模型名稱）：
   ```bash
   ollama pull gemma4:latest
   ```

2. **啟動 Discord 機器人**：
   在專案根目錄下，執行以下命令：
   ```bash
   python -m src.bot
   ```

---

## Discord Slash 指令

在 Discord 頻道中，您可以使用以下斜線指令進行遊戲管理與互動：

| 指令 | 權限 | 功能描述 |
|---|---|---|
| `/join` | 所有玩家 | 加入遊戲玩家名單。 |
| `/addbot [數量]` | 所有玩家 | 建立指定數量的 AI 玩家並加入遊戲。 |
| `/god` | 所有玩家 | 將自己轉為天神（旁觀者/主持人）。 |
| `/mode [mode]` | 所有玩家 | 切換模式，可選擇 `online`（Bot 主持）或 `offline`（私訊房主）。 |
| `/start` | 所有玩家 | 分配角色並開始遊戲（自動發送頭像並進入夜晚流程）。 |
| `/done` | 當前發言者 | 白天階段結束自己當前的發言，交由下一位發言。 |
| `/vote [目標]` | 存活玩家 | 白天投票，輸入目標編號或 `no`（投廢票）。 |
| `/die [目標]` | 管理員/房主 | 強制移除指定玩家（淘汰）。 |
| `/reset` | 管理員/房主 | 強制重置遊戲狀態，並解禁頻道發言限制。 |

---

## 執行單元測試

本專案使用 `pytest` 與 `pytest-asyncio` 進行單元測試，您可以透過以下指令執行所有測試以驗證引擎邏輯是否正常：

```bash
# 確保在虛擬環境下
pytest
```

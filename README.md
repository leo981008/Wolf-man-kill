# 狼人殺 Discord Bot (Raspberry Pi 部署版)

這是一個專為 Raspberry Pi 設計的多人狼人殺 Discord Bot，具備 Wiki 標準局式、身分分配與說明、天黑禁言管理與投票功能。

## 安全性增強 (Security Enhancements)

本專案已通過安全性審計，針對以下關鍵領域進行了強化：
- **加密安全性**：核心邏輯全面採用 `random.SystemRandom` (CSPRNG) 取代標準偽隨機數生成器，防止通過狀態預測進行作弊。
- **並發控制**：引入 `asyncio.Lock` 機制，防止多名玩家同時加入或投票時產生的 Race Condition 與數據不一致。
- **存取控制**：嚴格的權限驗證，確保只有房主或管理員能執行敏感指令 (如 `/reset`, `/die`)。
- **輸入驗證**：針對所有使用者輸入進行長度與型別檢查，防止惡意 Payload 攻擊。

## AI 整合功能 (AI Features)

本版本支援多種 AI 模型（Google Gemini 與 Ollama），帶來以下智慧功能：

1.  **動態板子生成**：
    - 當玩家人數不在標準模板 (6, 9, 10, 12人等) 範圍內時（例如 11 人或 14 人），Bot 會自動呼叫 AI，根據現有人數與角色庫生成平衡的板子。
    - 若 AI 生成失敗，則會自動回退到最接近的標準板子縮減模式。

2.  **智慧旁白與場控 (Dual Mode)**：
    - **線上模式 (Online)**：Bot 擔任主持人，在頻道發送由 AI 生成的、富有帶入感的情境旁白（天黑、天亮、死亡通告）。
    - **線下模式 (Offline)**：Bot 擔任「場控助理」，將 AI 生成的台詞透過私訊發送給現場主持人（房主），協助主持人控場。
    - 可透過 `/mode` 指令切換模式。

3.  **AI 玩家 (AI Players)**：
    - 支援加入 AI 電腦玩家填補空缺 (透過 `/addbot`)。
    - **全自動夜間行動**：AI 狼人（殺人）、預言家（查驗）、女巫（救/毒）、守衛（守護）會根據簡易邏輯自動執行。
    - **白天發言與投票**：AI 會在白天發言階段生成符合情境的對話，並參與投票。
    - **上下文感知發言**：AI 在發言時會參考本輪其他玩家的發言紀錄，讓對話更加自然且具邏輯性。

## AI 配置說明

Bot 支援切換 AI 提供者，您可以選擇使用雲端的 **Google Gemini (CLI)** 或本地的 **Ollama**。

### 安裝 Gemini CLI

若使用 Gemini 作為提供者，需先安裝 `gemini-cli` 並完成登入：

```bash
# 安裝 Gemini CLI
npm install -g @google/gemini-cli

# 登入 Google 帳號 (推薦使用此方式以利用免費額度)
gemini login
```

若無法使用瀏覽器登入，也可在 `.env` 中設定 `GEMINI_API_KEY`。

### 環境變數設定

請在 `.env` 檔案中設定以下變數：

| 變數名稱 | 說明 | 預設值 | 範例 |
| :--- | :--- | :--- | :--- |
| `AI_PROVIDER` | 選擇 AI 提供者 (`gemini` 或 `ollama`) | `gemini` | `ollama` |
| `GEMINI_API_KEY` | Google Gemini 的 API Key (選填，若已透過 CLI 登入則免填) | 無 | `AIzaSy...` |
| `OLLAMA_MODEL` | Ollama 使用的模型名稱 | `gpt-oss:20b` | `llama3` |
| `OLLAMA_HOST` | Ollama API 的連線位址 | `http://localhost:11434` | `http://192.168.1.10:11434` |

若要使用 Ollama，請確保您的機器上已安裝並執行 Ollama 服務，且已下載指定的模型（預設為 `gpt-oss:20b`）。

## 功能列表

- **Discord Slash Commands**：全面改用 `/` 斜線指令，操作更直覺。
- **Wiki 標準局式**：支援 6, 7, 8, 9, 10, 12 人局，自動根據人數選擇最接近的 Wiki 模板。
- **最大人數限制**：本遊戲最多支援 20 名玩家。
- **身分機制**：
    - 遊戲開始時，透過私訊 (DM) 發送身分與**角色功能說明**給玩家。
    - 遊戲開始時，會在頻道公開本局所有角色的詳細功能說明。
- **自由切換身分**：
    - 玩家可在遊戲開始前，透過 `/join` (加入遊戲) 或 `/god` (轉為旁觀者) 自由切換狀態。
- **人數溢出處理**：
    - 若玩家人數超過板子上限且 AI 生成失敗，系統會自動隨機抽選玩家進入遊戲。
    - **多餘玩家轉為天神 (God)**：未被選中的玩家將自動轉為旁觀者。
- **日夜循環**：
    - 天黑時 Bot 會自動禁言頻道。
    - **循序夜間行動**：Bot 會依照順序 (守衛 -> 狼人 -> 女巫 -> 預言家) 私訊相關玩家進行行動。
- **依序發言系統**：
    - 天亮時自動進入發言階段，隨機排序存活玩家。
    - 若玩家在語音頻道，輪到發言時會自動解除靜音 (需授權 Mute Members)。
- **投票系統**：支援廢票 (`/vote no`)，全體投票後自動結算，平票時重置投票。

## 指令列表 (Slash Commands)

### 一般指令
- `/join`：加入遊戲 (若原本是天神，會轉為玩家)。
- `/god`：轉為天神 (旁觀者)，不參與遊戲但可接收戰況。
- `/done`：(發言階段專用) 結束自己的發言回合，換下一位玩家。
- `/vote [編號]` 或 `/vote no`：投票給指定編號的玩家或投廢票 (Abstain)。

### 管理員 / 房主指令
- `/start`：開始遊戲。
- `/addbot [數量]`：加入指定數量的 AI 玩家。
- `/mode [online/offline]`：切換線上 (Bot主持) 或線下 (助理) 模式。
- `/reset`：重置遊戲。
    - **注意**：若遊戲正在進行中，僅限天神 (God) 可執行此指令。
- `/day`：(管理員用) 切換至天亮，開啟發言。
- `/night`：(管理員用) 切換至天黑，關閉發言並開始夜間流程。
- `/die [編號]`：(天神用) 強制處決一名玩家 (用於違反規則或斷線等情況)。

## 部署教學 (Raspberry Pi)

### 1. 環境準備
打開終端機，更新系統並安裝 Python 3。

```bash
sudo apt update
sudo apt install python3 python3-venv -y
```

### 2. 專案設定
建立專案資料夾並進入：
```bash
mkdir werewolf-bot
cd werewolf-bot
```
(將本專案檔案放入此資料夾)

### 3. 建立虛擬環境
建立並啟動 Python 虛擬環境：

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. 安裝套件
安裝相依套件：

```bash
pip install -r requirements.txt
```

### 5. 設定 Token 與 API Key
使用範本建立 `.env` 檔案：

```bash
cp .env.example .env
nano .env
```
修改內容範例：
```
DISCORD_TOKEN=你的_Discord_Bot_Token
AI_PROVIDER=gemini  # 或 ollama
GEMINI_API_KEY=你的_Google_Gemini_API_Key
# 若使用 Ollama，請設定以下變數
# OLLAMA_MODEL=gpt-oss:20b
# OLLAMA_HOST=http://localhost:11434
```
*(Gemini API Key 可至 Google AI Studio 免費申請)*

> **注意**：Bot 需開啟 **Server Members Intent** 和 **Message Content Intent**，並給予 **Administrator** 權限以執行禁言操作。

### 6. 測試執行
```bash
python bot.py
```
若看到 `已上線！` 表示成功。

---

## 自動啟動設定 (Systemd)

(請參考原文件，無需變更)

## 檔案結構
- `bot.py`: 主程式 (Slash Commands + AI 整合)。
- `ai_manager.py`: 負責與 AI (Gemini/Ollama) 溝通的模組。
- `.env`: 設定檔。
- `requirements.txt`: 套件清單。
- `tests/`: 測試代碼目錄。

## 資料來源與授權

本專案的遊戲板子配置（局式）資料取自 [狼人殺百科](https://lrs.fandom.com/zh/wiki/%E5%B1%80%E5%BC%8F?variant=zh-tw)。
根據 Fandom 社群規範，內容採用 [CC-BY-SA](https://creativecommons.org/licenses/by-sa/3.0/) 授權。

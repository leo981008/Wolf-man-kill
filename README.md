# 狼人殺 Discord Bot (Raspberry Pi 部署版)

這是一個專為 Raspberry Pi 設計的多人狼人殺 Discord Bot，具備 Wiki 標準局式、身分分配與說明、天黑禁言管理與投票功能。

## 安全性增強 (Security Enhancements)

本專案已通過安全性審計，針對以下關鍵領域進行了強化：
- **加密安全性**：核心邏輯全面採用 `random.SystemRandom` (CSPRNG) 取代標準偽隨機數生成器，防止通過狀態預測進行作弊。
- **並發控制**：引入 `asyncio.Lock` 機制，防止多名玩家同時加入或投票時產生的 Race Condition 與數據不一致。
- **存取控制**：嚴格的權限驗證，確保只有房主或管理員能執行敏感指令 (如 `!reset`, `!die`)。
- **輸入驗證**：針對所有使用者輸入進行長度與型別檢查，防止惡意 Payload 攻擊。

## 功能
- **Wiki 標準局式**：支援 6, 7, 8, 9, 10, 12 人局，自動根據人數選擇最接近的 Wiki 模板（如：預女獵白、狼王守衛、諸神黃昏等）。
- **最大人數限制**：本遊戲最多支援 20 名玩家。
- **身分機制**：
    - 遊戲開始時，透過私訊 (DM) 發送身分與**角色功能說明**給玩家。
    - 遊戲開始時，會在頻道公開本局所有角色的詳細功能說明。
    - 支援角色：狼人、預言家、村民、獵人、守衛、女巫、白痴、狼王、白狼王、騎士、惡靈騎士等。
- **自由切換身分**：
    - 玩家可在遊戲開始前，透過 `!join` (加入遊戲) 或 `!god` (轉為旁觀者) 自由切換狀態。
- **人數溢出處理**：
    - 若玩家人數超過板子上限（例如 11 人玩 10 人局），系統會自動隨機抽選玩家進入遊戲。
    - **多餘玩家轉為天神 (God)**：未被選中的玩家將自動轉為旁觀者（天神），與主持人一樣能收到所有人的身分列表，但不參與遊戲。
- **日夜循環**：
    - 天黑時 Bot 會自動禁言頻道。
    - **循序夜間行動**：Bot 會依照順序 (守衛 -> 狼人 -> 女巫 -> 預言家) 私訊相關玩家進行行動。
    - **編號系統**：遊戲開始時會分配每位玩家一個 ID，行動與投票均使用編號。
- **依序發言系統**：
    - 天亮時自動進入發言階段，隨機排序存活玩家。
    - 若玩家在語音頻道，輪到發言時會自動解除靜音 (需授權 Mute Members)，結束後自動靜音。
    - 必須等待所有玩家發言完畢才開放投票。
- **投票系統**：支援廢票 (`!vote no`)，全體投票後自動結算，平票時重置投票。

## 指令列表

### 一般指令
- `!join`：加入遊戲 (若原本是天神，會轉為玩家)。
- `!god`：轉為天神 (旁觀者)，不參與遊戲但可接收戰況。
- `!done`：(發言階段專用) 結束自己的發言回合，換下一位玩家。
- `!vote [編號]` 或 `!vote no`：投票給指定編號的玩家或投廢票 (Abstain)。

### 管理員 / 天神指令
- `!start`：開始遊戲。分配身分、分配編號、公開角色說明並進入天黑流程。
- `!reset`：重置遊戲。
    - **注意**：若遊戲正在進行中，僅限天神 (God) 可執行此指令。
- `!day`：(管理員用) 切換至天亮，開啟發言。
- `!night`：(管理員用) 切換至天黑，關閉發言並開始夜間流程。
- `!die [編號]`：(天神用) 強制處決一名玩家 (用於違反規則或斷線等情況)。

## 獲勝規則 (屠邊局)

本遊戲採用 **屠邊** 規則判定勝負。系統會於**天亮時**、**投票處決後**、**天神強制處決後**自動檢查是否達成獲勝條件。

- **狼人陣營獲勝條件**：
  - **屠神**：場上所有「神職」玩家死亡。
  - **屠民**：場上所有「平民」玩家死亡。

- **好人陣營獲勝條件**：
  - **屠狼**：場上所有「狼人」玩家死亡。

### 角色分類
為了判定屠邊，各角色分類如下：
- **狼人陣營**：狼人、狼王、白狼王、隱狼、惡靈騎士。
- **神職 (Gods)**：預言家、女巫、獵人、守衛、白痴、騎士。
- **平民 (Villagers)**：平民、老流氓 (算作民)。

## 支援局式 (根據人數自動判斷)

- **3-5 人**：基礎娛樂局 (1 狼 + 1 預言家 + 村民)
- **6 人**：明牌局、暗牌局
- **7 人**：生還者板子
- **8 人**：諸神黃昏、末日狂徒
- **9 人**：暗牌局
- **10 人**：普通局 (預女獵)、白痴局
- **12 人**：預女獵白 標準板、狼王守衛

## 部署教學 (Raspberry Pi)

### 1. 環境準備
打開終端機，更新系統並安裝 Python 3 (Raspberry Pi OS 通常已內建)。

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
建立並啟動 Python 虛擬環境，避免汙染系統套件：

```bash
# 建立名為 venv 的虛擬環境
python3 -m venv venv

# 啟動虛擬環境
source venv/bin/activate
```

### 4. 安裝套件
在虛擬環境中安裝所需套件：

```bash
pip install -r requirements.txt
```

### 5. 設定 Token
使用範本建立 `.env` 檔案，填入你的 Discord Bot Token：

```bash
cp .env.example .env
nano .env
```
修改內容範例：
```
DISCORD_TOKEN=你的_Token_貼在這裡
```
*(按 Ctrl+O 儲存，Ctrl+X 離開)*

> **注意**：請確保 Bot 在 Discord Developer Portal 中開啟了 **Server Members Intent** 和 **Message Content Intent**，並邀請 Bot 進入伺服器時給予 **Administrator** 或 **Manage Channels/Roles** 權限，否則無法禁言。

### 6. 測試執行
```bash
python bot.py
```
若看到 `已上線！` 表示成功。按 `Ctrl+C` 停止。

### 7. 執行測試 (Optional)
若要驗證 Bot 的安全性與邏輯，可執行內建測試：
```bash
python3 -m pytest tests/
```

---

## 自動啟動設定 (Systemd)

為了讓 Bot 在樹莓派開機時自動執行，我們使用 systemd。

1. **檢查 service 檔案**
   開啟 `werewolf.service`，確保 `User` 和路徑 (`WorkingDirectory`, `ExecStart`) 與你的實際路徑相符。
   預設路徑為 `/home/pi/werewolf-bot`，使用者為 `pi`。

2. **複製並啟用服務**
   ```bash
   # 複製設定檔到系統目錄
   sudo cp werewolf.service /etc/systemd/system/

   # 重新載入設定
   sudo systemctl daemon-reload

   # 設定開機自動啟動
   sudo systemctl enable werewolf.service

   # 立即啟動服務
   sudo systemctl start werewolf.service
   ```

3. **檢查狀態**
   ```bash
   sudo systemctl status werewolf.service
   ```
   若顯示 `active (running)` 即代表部署成功！

## 檔案結構
- `bot.py`: 主程式。
- `.env`: 設定檔 (請勿上傳至公開儲存庫)。
- `.env.example`: 設定檔範本。
- `requirements.txt`: 套件清單。
- `werewolf.service`: 自動啟動設定檔。
- `tests/`: 測試代碼目錄。

## 資料來源與授權

本專案的遊戲板子配置（局式）資料取自 [狼人殺百科](https://lrs.fandom.com/zh/wiki/%E5%B1%80%E5%BC%8F?variant=zh-tw)。
根據 Fandom 社群規範，內容採用 [CC-BY-SA](https://creativecommons.org/licenses/by-sa/3.0/) 授權。

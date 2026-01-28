# 狼人殺 Discord Bot (Raspberry Pi 部署版)

這是一個專為 Raspberry Pi 設計的多人狼人殺 Discord Bot，具備 Wiki 標準局式、身分分配與說明、天黑禁言管理與投票功能。

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
- **日夜循環**：自動管理頻道發言權限 (天黑禁言、天亮討論)。
- **投票系統**：支援廢票 (`!vote no`)，全體投票後自動結算，平票時重置投票。

## 指令列表

### 一般指令
- `!join`：加入遊戲 (若原本是天神，會轉為玩家)。
- `!god`：轉為天神 (旁觀者)，不參與遊戲但可接收戰況。
- `!vote @玩家` 或 `!vote no`：投票給指定玩家或投廢票 (Abstain)。

### 管理員 / 天神指令
- `!start`：開始遊戲。分配身分、公開角色說明並進入天黑。
- `!reset`：重置遊戲。
    - **注意**：若遊戲正在進行中，僅限天神 (God) 可執行此指令。
- `!day`：(管理員用) 切換至天亮，開啟發言。
- `!night`：(管理員用) 切換至天黑，關閉發言。
- `!die @玩家`：(天神用) 強制處決一名玩家 (用於違反規則或斷線等情況)。

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
編輯 `.env` 檔案，填入你的 Discord Bot Token：

```bash
nano .env
```
內容範例：
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
- `.env`: 設定檔 (Token)。
- `requirements.txt`: 套件清單。
- `werewolf.service`: 自動啟動設定檔。

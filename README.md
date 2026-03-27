# Vanadium OS

**Open-source music playback OS for Raspberry Pi, by VV Audio Lab**

![License](https://img.shields.io/badge/license-VV%20Audio%20Lab%20v1.0-blue)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%204%2F5-red)
![Status](https://img.shields.io/badge/status-alpha-orange)

---

## 概覽

Vanadium OS 係基於 DietPi 嘅輕量化 Hi-Fi 音樂播放系統，專為發燒友設計。

由 [VV Audio Lab](https://vvaudiolab.com) 開發，原生支援 Oscar 數字網橋硬件。

---

## 功能

- 🎵 **MPD 播放引擎** — 支援本地、NAS 掛載音樂庫
- 🔗 **Roon Bridge** — 作為 Roon 端點使用
- 🎯 **Diretta** — 支援 Diretta Target 模式
- 🖥️ **WebUI** — Neumorphism / Liquid Glass 雙主題
- 📱 **手機控制** — 瀏覽器直接訪問，無需 App
- 🔊 **Hi-Res 支援** — 取決於所接 DAC 模塊（FifoPi Q7 提供低 jitter I2S 時鐘優化）
- ⏰ **FifoPi Q7 支援** — iSabre 驅動預裝
- 🔒 **SSH 內建** — 方便授權及進階設定

---

## 硬件支援

| 硬件 | 支援狀態 |
|------|----------|
| Raspberry Pi 4 | ✅ 完整支援 |
| Raspberry Pi 5 | 🔄 測試中 |
| FifoPi Q7 (iSabre) | ✅ 完整支援 |
| USB DAC | ✅ 即插即用 |
| I2S DAC | ✅ 支援 |
| AES/EBU 輸出 | ✅ 支援 |
| HDMI 觸控屏 | ✅ 支援 |

---

## 快速安裝

### 方法一：一鍵安裝（基於現有 DietPi）

```bash
# SSH 登入你的 Raspberry Pi
ssh dietpi@vanadium-os.local

# 一鍵安裝 Vanadium OS
curl -sSL https://raw.githubusercontent.com/shell9000/vanadium-os/main/install.sh | bash
```

### 方法二：刷入預製 Image

1. 下載最新 Image：[Releases](https://github.com/shell9000/vanadium-os/releases)
2. 用 Raspberry Pi Imager 刷入 SD 卡
3. 開機後 SSH 進行初始設定

```bash
ssh vanadium@vanadium-os.local
# 預設密碼: vvaudio
```

---

## 訪問 WebUI

```
http://vanadium-os.local
```

或者用 IP 直接訪問：

```
http://<your-pi-ip>
```

---

## Oscar 升級到 Oscar-II

Vanadium OS 原生支援 Oscar 數字網橋升級：

```
Oscar（現有）
  └── DietPi + FifoPi Q7

        ↓ 安裝 Vanadium OS
        ↓ 加 HDMI 觸控屏

Oscar-II
  ├── Vanadium OS
  ├── FifoPi Q7（原有）
  ├── 觸控屏 Now Playing 顯示
  └── WebUI 手機控制
```

---

## Diretta 授權

Vanadium OS 支援 Diretta Target。授權方式同原有流程一致：

```bash
ssh vanadium@vanadium-os.local
sudo diretta-license get
```

---

## 項目結構

```
vanadium-os/
├── install.sh          # 一鍵安裝腳本
├── LICENSE             # VV Audio Lab 授權條款
├── README.md
├── assets/
│   └── logo/           # VV Audio Lab / VVAI Logo
├── player/
│   ├── api/            # FastAPI 播放器後端
│   └── ui/
│       └── themes/     # WebUI 主題
│           ├── neuro/  # Neumorphism 深色主題
│           └── glass/  # Liquid Glass 主題
├── os/
│   └── scripts/        # 系統配置腳本
└── docs/
    ├── install.md
    ├── hardware.md
    └── development.md
```

---

## 開發路線圖

- [x] 播放器 WebUI（Neumorphism 主題）
- [x] 播放器 WebUI（Liquid Glass 主題）
- [x] MPD 後端 API
- [ ] 一鍵安裝腳本
- [ ] Roon Bridge 整合
- [ ] Diretta 整合
- [ ] 換膚功能
- [ ] 曲庫瀏覽頁面
- [ ] 樹莓派 Image 構建
- [ ] Oscar-II 觸控屏優化

---

## 授權

Vanadium OS 採用 [VV Audio Lab License v1.0](LICENSE)。

- ✅ 免費個人使用
- ✅ 開放源代碼
- ❌ 不可移除 VV Audio Lab 品牌標識
- ❌ 商業使用需書面授權

---

## 關於 VV Audio Lab

VV Audio Lab 專注於高品質數字音頻硬件與軟件開發。

產品線：
- **Vanadium-II** — 旗艦 Roon Core
- **Vanadium Mini** — 緊湊型 Roon Core + 網絡交換機
- **Oscar** — 數字網橋（Roon Bridge / Diretta）
- **Oscar-II** — Oscar + Vanadium OS + 觸控屏

🌐 [vvaudiolab.com](https://vvaudiolab.com)

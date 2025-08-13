"""
===========================================================================

    中文註解:
    腳本名稱: volume_controller.py
    功能: 音量控制器專案的電腦端主程式。它會在終端機中執行，並使用
          鍵盤輸入來模擬來自 RP2040 硬體的指令，用於在整合硬體前，
          完整地測試與開發軟體控制邏輯。
    
    操作指令:
      - 'w': 音量增加
      - 's': 音量減少
      - 'm': 靜音 / 取消靜音
      - 'n': 切換到下一個目標程式
      - 'r': 重新整理程式列表
      - 'q': 結束程式

    English Comment:
    Script Name: volume_controller.py
    Function: This is the main PC-side application for the volume controller
              project. It runs in the terminal and uses keyboard input to
              simulate commands from the RP2040 hardware. It is intended for
              fully testing and developing the software control logic before
              hardware integration.

    Controls:
      - 'w': Volume Up
      - 's': Volume Down
      - 'm': Mute / Unmute
      - 'n': Switch to the next target application
      - 'r': Refresh the application list
      - 'q': Quit the program

    Author: DIY設計
    Date: 2025-08-12

===========================================================================
"""

# volume_controller.py
import os
import time
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

# --- 核心功能函式 ---

def get_active_sessions():
    """取得所有活躍且有程式名稱的音訊 session"""
    sessions = AudioUtilities.GetAllSessions()
    # 我們只關心那些有 .Process 屬性的 session
    active_sessions = [s for s in sessions if s.Process]
    return active_sessions

def print_status(sessions, current_index):
    """在終端機印出目前的狀態，方便除錯"""
    os.system('cls' if os.name == 'nt' else 'clear') # 清除畫面
    print("--- RP2040 音量控制器模擬 ---")
    print("請用鍵盤模擬硬體操作:")
    print("  'w': 音量增加   's': 音量減少   'm': 靜音/取消靜音")
    print("  'n': 切換下一個目標程式")
    print("  'r': 重新整理程式列表")
    print("  'q': 結束程式\n")
    
    if not sessions:
        print("目前沒有偵測到任何音訊程式。")
        return

    print("目前偵測到的音訊程式:")
    for i, session in enumerate(sessions):
        prefix = ">> " if i == current_index else "   "
        volume_percent = f"{session.SimpleAudioVolume.GetMasterVolume():.0%}"
        mute_status = " [靜音]" if session.SimpleAudioVolume.GetMute() else ""
        print(f"{prefix}[{i}] - {session.Process.name()} @ {volume_percent}{mute_status}")
    print("\n---------------------------------")


# --- 主程式邏輯 ---

def main():
    sessions = get_active_sessions()
    current_index = 0

    while True:
        print_status(sessions, current_index)

        # 如果沒有任何音訊程式，就等待一下再重新偵測
        if not sessions:
            time.sleep(2)
            sessions = get_active_sessions()
            current_index = 0
            continue

        # 取得使用者輸入
        key = input("請輸入指令: ").lower()

        # 取得目前要控制的 session
        target_session = sessions[current_index]
        volume_interface = target_session.SimpleAudioVolume

        # --- 解析指令 ---
        if key == 'q':
            print("程式結束。")
            break
        elif key == 'w': # Volume Up
            current_volume = volume_interface.GetMasterVolume()
            new_volume = min(1.0, current_volume + 0.05) # 每次增加 5%，最多到 100%
            volume_interface.SetMasterVolume(new_volume, None)
        elif key == 's': # Volume Down
            current_volume = volume_interface.GetMasterVolume()
            new_volume = max(0.0, current_volume - 0.05) # 每次減少 5%，最少到 0%
            volume_interface.SetMasterVolume(new_volume, None)
        elif key == 'm': # Mute
            is_muted = volume_interface.GetMute()
            volume_interface.SetMute(not is_muted, None)
        elif key == 'n': # Next app
            # 索引值加一，並用 % 來循環 (例如有3個程式，索引到3時會變回0)
            current_index = (current_index + 1) % len(sessions)
        elif key == 'r': # Refresh list
            sessions = get_active_sessions()
            current_index = 0 # 重設回第一個w
        else:
            print("無效指令...")
            time.sleep(0.5)

if __name__ == "__main__":
    main()
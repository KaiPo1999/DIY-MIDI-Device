# volume_controller.py - 動態加速度版
# 功能：根據旋轉速度，平滑地調整音量變化的幅度

import os
import time
import serial
from pycaw.pycaw import AudioUtilities

# --- 設定 ---
SERIAL_PORT = 'COM8'
BAUD_RATE = 115200

# --- 動態加速度設定 (您可以調整這些數值來改變手感) ---
# 時間間隔的範圍 (秒)
# - 小於此值視為最快速度
MIN_TIMEDIFF = 0.02
# - 大於此值視為最慢速度
MAX_TIMEDIFF = 0.2

# 音量步進的範圍 (%)
# - 最慢速度下的變化量 (精細微調)
MIN_VOLUME_STEP = 0.01  # 1%
# - 最快速度下的變化量 (快速調整)
MAX_VOLUME_STEP = 0.10  # 10%

# (get_active_sessions 和 print_status 函式與之前相同，此處省略以求簡潔)
def get_active_sessions():
    sessions = AudioUtilities.GetAllSessions()
    return [s for s in sessions if s.Process]

def print_status(sessions, current_index, port_name):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("--- RP2040 音量控制器 (動態加速度版) ---")
    print(f"狀態: 正在與 {port_name} 雙向通訊...")
    print("---------------------------------")
    if not sessions:
        print("目前沒有偵測到任何音訊程式。")
        return
    print("目前偵測到的音訊程式:")
    for i, session in enumerate(sessions):
        try:
            prefix = ">> " if i == current_index else "   "
            volume_percent = f"{session.SimpleAudioVolume.GetMasterVolume():.0%}"
            mute_status = " [靜音]" if session.SimpleAudioVolume.GetMute() else ""
            print(f"{prefix}[{i}] - {session.Process.name()} @ {volume_percent}{mute_status}")
        except Exception: continue
    print("\n---------------------------------")
    print(">> 預設模式 <<")
    print("  旋轉: 根據速度調整音量 (1% - 10%)")
    print("  短按: 靜音 / 取消靜音")
    print("\n>> 按住按鈕 + 旋轉可切換模式 <<")
    print("\n(按 Ctrl+C 結束程式)")


def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"成功連接到 {SERIAL_PORT}！")
        time.sleep(2)
    except serial.SerialException as e:
        print(f"錯誤：無法開啟序列埠 {SERIAL_PORT}。詳細錯誤: {e}")
        return

    def send_volume_to_mcu(session):
        if not session: return
        try:
            is_muted = session.SimpleAudioVolume.GetMute()
            level = 0 if is_muted else int(session.SimpleAudioVolume.GetMasterVolume() * 100)
            ser.write(f"V:{level}\n".encode('utf-8'))
        except Exception: pass

    sessions = get_active_sessions()
    current_index = 0
    last_turn_time = 0

    if sessions: send_volume_to_mcu(sessions[current_index])
    
    try:
        while True:
            line = ser.readline()
            if not line:
                new_sessions = get_active_sessions()
                if len(new_sessions) != len(sessions) or not all(s in new_sessions for s in sessions):
                    sessions = new_sessions
                    current_index = min(current_index, len(sessions) - 1 if sessions else 0)
                    if sessions: send_volume_to_mcu(sessions[current_index])
                continue
            
            command = line.decode('utf-8').strip()
            if not sessions: continue
            
            target_session = sessions[current_index]
            vol = target_session.SimpleAudioVolume

            if command == "UP" or command == "DOWN":
                current_time = time.monotonic()
                time_diff = current_time - last_turn_time
                last_turn_time = current_time

                # --- 全新的動態步進計算 ---
                # 1. 將時間差限制在我們定義的範圍內
                clamped_diff = max(MIN_TIMEDIFF, min(time_diff, MAX_TIMEDIFF))
                
                # 2. 計算速度比例 (0.0 代表最慢, 1.0 代表最快)
                #    公式是 (最大時間 - 當前時間) / (最大時間 - 最小時間)
                speed_ratio = (MAX_TIMEDIFF - clamped_diff) / (MAX_TIMEDIFF - MIN_TIMEDIFF)
                
                # 3. 根據速度比例，線性計算出最終的音量步進
                step = MIN_VOLUME_STEP + (MAX_VOLUME_STEP - MIN_VOLUME_STEP) * speed_ratio
                
                if command == "UP":
                    vol.SetMasterVolume(min(1.0, vol.GetMasterVolume() + step), None)
                else: # DOWN
                    vol.SetMasterVolume(max(0.0, vol.GetMasterVolume() - step), None)

            elif command == "MUTE":
                vol.SetMute(not vol.GetMute(), None)
            elif command == "NEXT_APP":
                current_index = (current_index + 1) % len(sessions)
            elif command == "PREV_APP":
                current_index = (current_index - 1 + len(sessions)) % len(sessions)
            
            send_volume_to_mcu(sessions[current_index])
            print_status(sessions, current_index, SERIAL_PORT)

    except serial.SerialException:
        print(f"\n錯誤：與 {SERIAL_PORT} 的連線中斷。")
    except KeyboardInterrupt:
        print("\n程式已由使用者手動結束。")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()
# volume_controller.py - 最終穩定版 (採用Process Name比對)
# 功能: 1. 自動偵測採更可靠的「程式名稱」比對，大幅提高成功率。
#       2. 保留並最佳化所有已有功能（手動鎖定、動態加速度、LED回饋）。

import os
import time
import serial
from pycaw.pycaw import AudioUtilities
import win32gui
import win32process
import psutil

# --- 設定 ---
SERIAL_PORT = 'COM8'
BAUD_RATE = 115200

# --- 動態加速度設定 ---
MIN_TIMEDIFF = 0.02
MAX_TIMEDIFF = 0.2
MIN_VOLUME_STEP = 0.01
MAX_VOLUME_STEP = 0.10

# --- 核心函式 ---
def get_all_sessions():
    sessions = AudioUtilities.GetAllSessions()
    return [s for s in sessions if s.Process]

def send_volume_to_mcu(ser, session):
    if not ser or not ser.is_open or not session:
        return
    try:
        is_muted = session.SimpleAudioVolume.GetMute()
        level = 0 if is_muted else int(session.SimpleAudioVolume.GetMasterVolume() * 100)
        ser.write(f"V:{level}\n".encode('utf-8'))
    except Exception:
        pass

def print_status(sessions, current_index, port_name, is_locked, debug_info):
    os.system('cls' if os.name == 'nt' else 'clear')
    mode = "鎖定目標" if is_locked else "自動偵測前景"
    print(f"--- RP2040 音量控制器 (模式: {mode}) ---")
    print(f"狀態: 正在與 {port_name} 雙向通訊...")
    
    target_name = "無 (等待指令或前景程式...)"
    if current_index is not None and sessions and current_index < len(sessions):
        try:
            target_name = sessions[current_index].Process.name()
        except Exception:
             target_name = "目標已失效"
    print(f"當前目標: {target_name}")
    print("---------------------------------")

    if sessions:
        for i, session in enumerate(sessions):
            try:
                prefix = ">> " if i == current_index else "   "
                volume_percent = f"{session.SimpleAudioVolume.GetMasterVolume():.0%}"
                mute_status = " [靜音]" if session.SimpleAudioVolume.GetMute() else ""
                print(f"{prefix}[{i}] {session.Process.name()} (PID: {session.Process.id}) @ {volume_percent}{mute_status}")
            except Exception: continue

    print("\n--- 除錯資訊 ---")
    print(f"前景程式名稱: {debug_info.get('name', 'N/A')}")
    print("--------------------")

def main():
    ser = None
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.2)
        print(f"成功連接到 {SERIAL_PORT}！")
        time.sleep(1)
    except serial.SerialException as e:
        print(f"錯誤：無法開啟序列埠 {SERIAL_PORT}。詳細錯誤: {e}")
        return

    sessions = get_all_sessions()
    current_index = None
    is_locked = False
    debug_info = {}
    last_turn_time = 0

    try:
        while True:
            # 1. 自動偵測邏輯 (採Process Name比對)
            if not is_locked:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    proc_name = proc.name()
                    debug_info = {'name': proc_name, 'pid': pid}
                    
                    found_match = False
                    for i, session in enumerate(sessions):
                        if session.Process and session.Process.name() == proc_name:
                            current_index = i
                            found_match = True
                            break
                    if not found_match:
                        current_index = None
                except (psutil.NoSuchProcess, psutil.AccessDenied, win32process.error):
                    current_index = None
                    debug_info = {'name': '錯誤或無權限', 'pid': 'N/A'}
            
            print_status(sessions, current_index, SERIAL_PORT, is_locked, debug_info)
            
            # 2. 讀取指令
            line = ser.readline()
            if not line:
                sessions = get_all_sessions()
                continue
            
            command = line.decode('utf-8').strip()

            # 3. 指令解析
            if command == "UNLOCK":
                is_locked = False
                current_index = None
                continue

            if command in ["NEXT_APP", "PREV_APP"]:
                is_locked = True
                if not sessions: continue
                if current_index is None: current_index = -1 if command == "NEXT_APP" else 0
                
                if command == "NEXT_APP": current_index = (current_index + 1) % len(sessions)
                else: current_index = (current_index - 1 + len(sessions)) % len(sessions)

            # 4. 執行動作
            if current_index is not None and sessions and current_index < len(sessions):
                try:
                    target_session = sessions[current_index]
                    vol = target_session.SimpleAudioVolume

                    if command == "UP" or command == "DOWN":
                        current_time = time.monotonic()
                        time_diff = current_time - last_turn_time
                        last_turn_time = current_time
                        
                        clamped_diff = max(MIN_TIMEDIFF, min(time_diff, MAX_TIMEDIFF))
                        speed_ratio = (MAX_TIMEDIFF - clamped_diff) / (MAX_TIMEDIFF - MIN_TIMEDIFF)
                        step = MIN_VOLUME_STEP + (MAX_VOLUME_STEP - MIN_VOLUME_STEP) * speed_ratio
                        
                        if command == "UP": vol.SetMasterVolume(min(1.0, vol.GetMasterVolume() + step), None)
                        else: vol.SetMasterVolume(max(0.0, vol.GetMasterVolume() - step), None)

                    elif command == "MUTE":
                        vol.SetMute(not vol.GetMute(), None)
                    
                    send_volume_to_mcu(ser, target_session)
                except IndexError:
                    current_index = None

    except Exception as e:
        print(f"\n程式發生未預期錯誤: {e}")
    finally:
        if ser and ser.is_open: ser.close()
        print("程式已結束。")

if __name__ == "__main__":
    main()
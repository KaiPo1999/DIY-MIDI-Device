# gui_volume_controller.py - 主動輪詢同步版
# 功能: 新增主動輪詢機制，定期將準確的音量同步到LED，解決狀態不同步問題。

import tkinter as tk
from tkinter import ttk, scrolledtext
import serial
import serial.tools.list_ports
import threading
import time
import queue

# --- 核心控制邏輯 ---
def controller_thread_logic(com_port, status_queue, stop_event):
    from pycaw.pycaw import AudioUtilities
    import win32gui
    import win32process
    import psutil

    # --- 設定 ---
    POLL_INTERVAL = 0.5  # 每0.5秒主動查詢一次音量
    MIN_TIMEDIFF, MAX_TIMEDIFF = 0.02, 0.2
    MIN_VOLUME_STEP, MAX_VOLUME_STEP = 0.01, 0.10

    # (核心函式 get_all_sessions, send_volume_to_mcu, log_message 不變)
    def get_all_sessions():
        try:
            sessions = AudioUtilities.GetAllSessions()
            return [s for s in sessions if s.Process]
        except Exception as e:
            log_message(f"獲取音訊Session時出錯: {e}")
            return []

    def send_volume_to_mcu(ser, session):
        if not ser or not ser.is_open or not session: return
        try:
            is_muted = session.SimpleAudioVolume.GetMute()
            level = 0 if is_muted else int(session.SimpleAudioVolume.GetMasterVolume() * 100)
            ser.write(f"V:{level}\n".encode('utf-8'))
        except Exception: pass
    
    def log_message(message):
        status_queue.put(message)

    ser = None
    try:
        ser = serial.Serial(com_port, 115200, timeout=0.1)
        log_message(f"成功連接到 {com_port}！")
    except serial.SerialException as e:
        log_message(f"錯誤：無法開啟序列埠 {com_port}。\n詳細錯誤: {e}")
        return

    sessions = get_all_sessions()
    current_index = None
    is_locked = False
    last_turn_time = 0
    last_poll_time = 0 # 新增變數：記錄上次輪詢的時間

    log_message("控制器邏輯已啟動...")

    while not stop_event.is_set():
        current_time_loop = time.time()
        
        # === 新增：主動輪詢同步機制 ===
        if current_time_loop - last_poll_time > POLL_INTERVAL:
            if current_index is not None and sessions and current_index < len(sessions):
                try:
                    # 主動發送當前目標的最新音量狀態
                    send_volume_to_mcu(ser, sessions[current_index])
                except IndexError:
                    current_index = None # 如果目標已消失，重置
            last_poll_time = current_time_loop
        
        # (自動偵測邏輯不變)
        if not is_locked:
            try:
                hwnd = win32gui.GetForegroundWindow()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = psutil.Process(pid).name()
                
                found_match = False
                for i, s in enumerate(sessions):
                    if s.Process and s.Process.name() == proc_name:
                        current_index = i
                        found_match = True
                        break
                if not found_match:
                    current_index = None
            except Exception:
                current_index = None
        
        # (讀取與解析指令邏輯不變)
        line = ""
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
        except Exception:
            log_message("讀取序列埠時發生錯誤，連線可能中斷。")
            break

        if not line:
            time.sleep(0.01)
            continue
        
        command = line
        log_message(f"收到指令: {command}")

        # (指令執行邏輯不變)
        if command == "UNLOCK":
            is_locked = False
            current_index = None
            log_message("模式切換: 自動偵測前景")
            continue

        if command in ["NEXT_APP", "PREV_APP"]:
            is_locked = True
            log_message("模式切換: 手動鎖定目標")
            if not sessions: continue
            if current_index is None: current_index = -1 if command == "NEXT_APP" else 0
            
            if command == "NEXT_APP": current_index = (current_index + 1) % len(sessions)
            else: current_index = (current_index - 1 + len(sessions)) % len(sessions)
            sessions = get_all_sessions() # 手動切換後刷新一次列表
            send_volume_to_mcu(ser, sessions[current_index]) # 切換後立即同步燈光
        
        elif current_index is not None and sessions and current_index < len(sessions):
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
            except (IndexError, AttributeError):
                current_index = None

    if ser and ser.is_open:
        ser.close()
    log_message("控制器連線已中斷。")

# --- GUI 應用程式類別 (完全不變) ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DIY音量控制器")
        self.geometry("500x400")
        
        self.thread = None
        self.stop_event = threading.Event()
        self.status_queue = queue.Queue()

        self.controls_frame = ttk.Frame(self, padding="10")
        self.controls_frame.pack(fill=tk.X)

        ttk.Label(self.controls_frame, text="選擇COM Port:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.port_var = tk.StringVar()
        self.port_selector = ttk.Combobox(self.controls_frame, textvariable=self.port_var, state="readonly")
        self.port_selector.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        self.refresh_button = ttk.Button(self.controls_frame, text="刷新", command=self.update_com_ports)
        self.refresh_button.pack(side=tk.LEFT, padx=5)

        self.connect_button = ttk.Button(self.controls_frame, text="連接", command=self.start_controller)
        self.connect_button.pack(side=tk.LEFT, padx=5)

        self.disconnect_button = ttk.Button(self.controls_frame, text="中斷", command=self.stop_controller, state="disabled")
        self.disconnect_button.pack(side=tk.LEFT, padx=5)

        self.status_frame = ttk.Frame(self, padding="10")
        self.status_frame.pack(expand=True, fill=tk.BOTH)

        self.status_box = scrolledtext.ScrolledText(self.status_frame, wrap=tk.WORD, state="disabled")
        self.status_box.pack(expand=True, fill=tk.BOTH)

        self.update_com_ports()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process_queue()

    def update_com_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_selector['values'] = ports
        if ports:
            self.port_var.set(ports[0])

    def start_controller(self):
        selected_port = self.port_var.get()
        if not selected_port:
            self.log_to_status_box("錯誤: 請先選擇一個COM Port！")
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=controller_thread_logic, 
            args=(selected_port, self.status_queue, self.stop_event),
            daemon=True
        )
        self.thread.start()
        
        self.connect_button.config(state="disabled")
        self.disconnect_button.config(state="normal")
        self.port_selector.config(state="disabled")
        self.refresh_button.config(state="disabled")

    def stop_controller(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
        
        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self.port_selector.config(state="readonly")
        self.refresh_button.config(state="normal")

    def log_to_status_box(self, message):
        self.status_box.config(state="normal")
        self.status_box.insert(tk.END, f"{message}\n")
        self.status_box.see(tk.END)
        self.status_box.config(state="disabled")
        
    def process_queue(self):
        try:
            while True:
                message = self.status_queue.get_nowait()
                self.log_to_status_box(message)
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def on_closing(self):
        self.stop_controller()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
# gui_volume_controller.py - 最終完美修正版
# 功能: 修正了GUI解析麥克風狀態的邏輯，確保介面能正確即時更新。

import tkinter as tk
from tkinter import ttk
import serial
import serial.tools.list_ports
import threading
import time
import queue
import comtypes

# --- 核心控制邏輯 (與前一版完全相同) ---
def controller_thread_logic(port_list, status_queue, stop_event):
    # ... (此處所有後端邏輯都與前一版相同，為節省篇幅省略) ...
    comtypes.CoInitialize()
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        import win32gui, win32process, psutil

        def log_message(message): status_queue.put(message)

        mic_volume_control = None
        try:
            mic_device = AudioUtilities.GetMicrophone()
            interface = mic_device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            mic_volume_control = cast(interface, POINTER(IAudioEndpointVolume))
            log_message("CMD:已成功獲取麥克風裝置。")
        except Exception as e:
            log_message(f"CMD:警告：找不到麥克風裝置。({e})")

        ser = None
        for port_to_try in port_list:
            if stop_event.is_set(): return
            log_message(f"CMD:正在嘗試連接到 {port_to_try}...")
            try:
                ser = serial.Serial(port_to_try, 115200, timeout=0.1)
                log_message(f"CMD:成功連接到 {port_to_try}！")
                status_queue.put(f"STATUS:已連接到 {port_to_try}")
                break
            except serial.SerialException:
                log_message(f"CMD:{port_to_try} 連接失敗...")
                ser = None
        
        if not ser:
            log_message("CMD:錯誤：無法連接任何COM Port。")
            status_queue.put("STATUS:錯誤: 找不到控制器")
            return

        POLL_INTERVAL, MIN_TIMEDIFF, MAX_TIMEDIFF, MIN_VOLUME_STEP, MAX_VOLUME_STEP = 0.2, 0.02, 0.2, 0.01, 0.10
        
        def get_all_sessions():
            try: return [s for s in AudioUtilities.GetAllSessions() if s.Process]
            except Exception: return []
        def send_volume_to_mcu(ser, session):
            if not ser or not ser.is_open or not session: return
            try:
                is_muted = session.SimpleAudioVolume.GetMute()
                level = 0 if is_muted else int(session.SimpleAudioVolume.GetMasterVolume() * 100)
                ser.write(f"V:{level}\n".encode('utf-8'))
                log_message(f"GUI_LED_UPDATE:{level}")
            except Exception: pass

        sessions, current_index, is_locked, last_turn_time, last_poll_time = get_all_sessions(), None, False, 0, 0
        log_message("CMD:控制器邏輯已啟動...")

        while not stop_event.is_set():
            target_name = "無"
            if current_index is not None and sessions and current_index < len(sessions):
                try: target_name = sessions[current_index].Process.name()
                except Exception: target_name = "已失效"
            log_message(f"TARGET:{target_name}")
            
            if mic_volume_control:
                try: log_message(f"MIC_STATUS:{mic_volume_control.GetMute()}")
                except Exception: pass

            if time.time() - last_poll_time > POLL_INTERVAL:
                if current_index is not None and sessions and current_index < len(sessions):
                    try: send_volume_to_mcu(ser, sessions[current_index])
                    except IndexError: current_index = None
                last_poll_time = time.time()
            if not is_locked:
                try:
                    hwnd, _, pid = win32gui.GetForegroundWindow(), *win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
                    proc_name = psutil.Process(pid).name()
                    found_match = False
                    for i, s in enumerate(sessions):
                        if s.Process and s.Process.name() == proc_name:
                            if current_index != i:
                               current_index = i
                               send_volume_to_mcu(ser, s)
                            found_match = True; break
                    if not found_match: current_index = None
                except Exception: current_index = None
            
            line = ""
            try:
                if ser.in_waiting > 0: line = ser.readline().decode('utf-8').strip()
            except (serial.SerialException, OSError):
                log_message("CMD:讀取序列埠時發生錯誤，連線已中斷。")
                break
            if not line:
                time.sleep(0.01)
                continue
            
            command = line
            
            if command == "MUTE": pass
            else: log_message(f"CMD:{command}")
            
            if command == "MIC_MUTE":
                if mic_volume_control:
                    try:
                        is_mic_muted = mic_volume_control.GetMute()
                        mic_volume_control.SetMute(not is_mic_muted, None)
                        log_message("CMD:Microphone " + ("Unmuted" if is_mic_muted else "Muted"))
                    except Exception as e:
                        log_message(f"CMD:控制麥克風失敗: {e}")
                else:
                    log_message("CMD:錯誤: 無法執行MIC_MUTE (未找到麥克風)")

            elif command == "UNLOCK": is_locked, current_index = False, None; log_message("CMD:模式切換: 自動偵測前景")
            elif command in ["NEXT_APP", "PREV_APP"]:
                is_locked = True
                log_message("CMD:模式切換: 手動鎖定目標")
                if not sessions: continue
                if current_index is None: current_index = -1 if command == "NEXT_APP" else 0
                if command == "NEXT_APP": current_index = (current_index + 1) % len(sessions)
                else: current_index = (current_index - 1 + len(sessions)) % len(sessions)
                sessions = get_all_sessions()
                if sessions and current_index < len(sessions): send_volume_to_mcu(ser, sessions[current_index])
            elif current_index is not None and sessions and current_index < len(sessions):
                try:
                    target_session, vol = sessions[current_index], sessions[current_index].SimpleAudioVolume
                    if command == "UP" or command == "DOWN":
                        current_time, time_diff = time.monotonic(), time.monotonic() - last_turn_time
                        last_turn_time = current_time
                        clamped_diff = max(MIN_TIMEDIFF, min(time_diff, MAX_TIMEDIFF))
                        speed_ratio = (MAX_TIMEDIFF - clamped_diff) / (MAX_TIMEDIFF - MIN_TIMEDIFF)
                        step = MIN_VOLUME_STEP + (MAX_VOLUME_STEP - MIN_VOLUME_STEP) * speed_ratio
                        if command == "UP": vol.SetMasterVolume(min(1.0, vol.GetMasterVolume() + step), None)
                        else: vol.SetMasterVolume(max(0.0, vol.GetMasterVolume() - step), None)
                    elif command == "MUTE":
                        is_currently_muted = vol.GetMute()
                        vol.SetMute(not is_currently_muted, None)
                        log_message("CMD:Unmuted" if is_currently_muted else "CMD:Muted")
                    send_volume_to_mcu(ser, target_session)
                except (IndexError, AttributeError): current_index = None
    finally:
        comtypes.CoUninitialize()

# --- GUI 應用程式類別 (修正Bug) ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DIY音量控制器")
        self.geometry("550x150")
        self.minsize(450, 150)
        self.attributes('-topmost', True)
        self.thread, self.stop_event, self.status_queue = None, threading.Event(), queue.Queue()
        self.is_intentionally_stopped = False
        
        self.main_frame = ttk.Frame(self, padding="15")
        self.main_frame.pack(expand=True, fill=tk.BOTH)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(3, weight=1)

        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.status_label_var = tk.StringVar(value="狀態: 正在初始化...")
        ttk.Label(self.status_frame, textvariable=self.status_label_var).pack(side=tk.LEFT)
        
        self.mic_status_var = tk.StringVar(value="MIC: N/A")
        self.mic_status_label = ttk.Label(self.status_frame, textvariable=self.mic_status_var, font=("Microsoft JhengHei UI", 10, "bold"))
        self.mic_status_label.pack(side=tk.RIGHT)

        self.info_frame = ttk.Frame(self.main_frame)
        self.info_frame.grid(row=1, column=0, sticky="ew", pady=(0,10))
        self.info_frame.columnconfigure(3, weight=1)
        ttk.Label(self.info_frame, text="最後指令:").grid(row=0, column=0, sticky="w")
        self.last_command_var = tk.StringVar(value="N/A")
        ttk.Label(self.info_frame, textvariable=self.last_command_var, font=("Consolas", 11, "bold"), foreground="blue").grid(row=0, column=1, sticky="w", padx=(5, 15))
        ttk.Label(self.info_frame, text="目前目標:").grid(row=0, column=2, sticky="w")
        self.target_var = tk.StringVar(value="N/A")
        ttk.Label(self.info_frame, textvariable=self.target_var, font=("Microsoft JhengHei UI", 11, "bold"), foreground="green").grid(row=0, column=3, sticky="w", padx=5)
        self.volume_var = tk.StringVar(value="")
        ttk.Label(self.info_frame, textvariable=self.volume_var, font=("Consolas", 11, "bold")).grid(row=0, column=4, sticky="w", padx=5)
        ttk.Frame(self.main_frame).grid(row=2, column=0, sticky="nsew")
        self.led_canvas = tk.Canvas(self.main_frame, height=45, bg="#2E2E2E", highlightthickness=0)
        self.led_canvas.grid(row=3, column=0, sticky="ew")
        self.led_rects = []
        for i in range(15):
            self.led_rects.append(self.led_canvas.create_rectangle(0,0,0,0, fill="#404040", outline="#505050"))
        self.led_canvas.bind("<Configure>", self.redraw_leds)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.process_queue()
        self.after(500, self.auto_connect_all_ports)
        self.after(5000, self.monitor_connection)

    def process_queue(self):
        try:
            while True:
                message = self.status_queue.get_nowait()
                if message.startswith("GUI_LED_UPDATE:"): self.update_gui_leds(int(message.split(":")[1]))
                elif message.startswith("CMD:"): self.last_command_var.set(message[4:])
                elif message.startswith("TARGET:"):
                    target_name = message[7:]
                    self.target_var.set(target_name)
                    if target_name in ["無", "已失效"]: self.volume_var.set("")
                elif message.startswith("STATUS:"): self.status_label_var.set(f"狀態: {message[7:]}")
                elif message.startswith("MIC_STATUS:"):
                    # --- 最終修正：將收到的字串"1"或"0"轉換成數字來判斷 ---
                    is_muted = int(message.split(":")[1]) == 1
                    if is_muted:
                        self.mic_status_var.set("MIC: 靜音")
                        self.mic_status_label.config(foreground="red")
                    else:
                        self.mic_status_var.set("MIC: 開啟")
                        self.mic_status_label.config(foreground="green")

        except queue.Empty:
            pass
        except Exception as e:
             self.last_command_var.set(f"GUI錯誤: {e}")
        
        self.after(100, self.process_queue)

    # (其他函式 redraw_leds, update_gui_leds, auto_connect, monitor, on_closing ... 與前一版相同，故省略)
    def redraw_leds(self, event=None):
        canvas_width, canvas_height = self.led_canvas.winfo_width(), self.led_canvas.winfo_height()
        num_pixels, padding, gap = 15, 5, max(2, int(canvas_width / 80))
        led_width = (canvas_width - (padding * 2) - (gap * (num_pixels - 1))) / num_pixels
        led_height = canvas_height - (padding * 2)
        for i, rect_id in enumerate(self.led_rects):
            x0, x1, y0, y1 = padding + i * (led_width + gap), padding + i * (led_width + gap) + led_width, padding, padding + led_height
            self.led_canvas.coords(rect_id, x0, y0, x1, y1)
    def update_gui_leds(self, level):
        self.volume_var.set(f"音量: {level}%")
        num_pixels, leds_to_light = 15, round(level / 100 * 15)
        for i, rect_id in enumerate(self.led_rects):
            color = "#404040"
            if i < leds_to_light:
                if i < num_pixels * 0.5: color = "#20E020"
                elif i < num_pixels * 0.8: color = "#E0E020"
                else: color = "#E02020"
            self.led_canvas.itemconfig(rect_id, fill=color)
    def auto_connect_all_ports(self):
        if self.thread and self.thread.is_alive(): return
        ports_info = serial.tools.list_ports.comports()
        if not ports_info: self.status_label_var.set("狀態: 錯誤！找不到任何COM Port！"); return
        keywords = ["RP2040", "CircuitPython", "Feather", "Pico", "USB Serial"]
        ports_with_keyword = [p.device for p in ports_info if any(k.lower() in p.description.lower() or k.lower() in p.manufacturer.lower() for k in keywords)]
        other_ports = [p.device for p in ports_info if p.device not in ports_with_keyword]
        self.status_label_var.set("狀態: 開始自動掃描連接...")
        self.start_controller_thread(ports_with_keyword + other_ports)
    def start_controller_thread(self, port_list):
        self.stop_event.clear()
        self.thread = threading.Thread(target=controller_thread_logic, args=(port_list, self.status_queue, self.stop_event), daemon=True)
        self.thread.start()
    def monitor_connection(self):
        if not self.is_intentionally_stopped and (not self.thread or not self.thread.is_alive()):
            self.last_command_var.set("連線中斷，正在嘗試重連...")
            self.target_var.set("N/A"); self.volume_var.set(""); self.update_gui_leds(0)
            self.auto_connect_all_ports()
        self.after(5000, self.monitor_connection)
    def on_closing(self):
        self.is_intentionally_stopped = True
        if self.thread and self.thread.is_alive(): self.stop_event.set()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
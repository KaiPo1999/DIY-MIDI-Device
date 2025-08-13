# code.py - 麥克風控制版
# 功能: 新增長按後放開(無旋轉)來觸發系統麥克風靜音的功能

import time
import board
import rotaryio
import keypad
import usb_cdc
import neopixel

# --- 設定 (不變) ---
NEOPIXEL_PIN = board.GP0
NUM_PIXELS = 15
LONG_PRESS_S = 0.5
UNLOCK_PRESS_S = 3.0

# --- 初始化 (不變) ---
encoder = rotaryio.IncrementalEncoder(board.GP2, board.GP3)
keys = keypad.Keys(pins=(board.GP4,), value_when_pressed=False, pull=True)
serial = usb_cdc.console
pixels = neopixel.NeoPixel(NEOPIXEL_PIN, NUM_PIXELS, brightness=0.3, auto_write=False)

# --- 狀態變數 ---
last_position = encoder.position
button_down_time = None
is_in_switch_mode = False
unlock_triggered = False
rotation_during_press = False # 新增：記錄長按期間是否有旋轉

# (update_volume_leds 函式不變)
def update_volume_leds(level):
    leds_to_light = round(level / 100 * NUM_PIXELS)
    for i in range(NUM_PIXELS):
        if i < leds_to_light:
            if i < NUM_PIXELS * 0.5: pixels[i] = (0, 255, 0)
            elif i < NUM_PIXELS * 0.8: pixels[i] = (255, 255, 0)
            else: pixels[i] = (255, 0, 0)
        else: pixels[i] = (0, 0, 0)
    pixels.show()

print("--- RP2040 韌體已啟動 (麥克風控制版) ---")
update_volume_leds(0)
incoming_buffer = ""

# --- 主迴圈 (邏輯更新) ---
while True:
    # (接收電腦指令的邏輯不變)
    if serial.in_waiting > 0:
        incoming_buffer += serial.read(serial.in_waiting).decode()
        if "\n" in incoming_buffer:
            line, incoming_buffer = incoming_buffer.split("\n", 1)
            if line.startswith("V:"):
                try: update_volume_leds(int(line[2:]))
                except (ValueError, IndexError): pass

    # --- 旋轉邏輯更新 ---
    current_position = encoder.position
    if current_position != last_position:
        if is_in_switch_mode:
            # 新增：標記長按期間發生了旋轉
            rotation_during_press = True
            serial.write(b"NEXT_APP\n" if current_position > last_position else b"PREV_APP\n")
        else:
            serial.write(b"UP\n" if current_position > last_position else b"DOWN\n")
        last_position = current_position

    # --- 按鈕事件邏輯更新 ---
    event = keys.events.get()
    if event:
        if event.pressed:
            button_down_time = time.monotonic()
            is_in_switch_mode = False
            unlock_triggered = False
            rotation_during_press = False # 每次按下時重置旋轉標記
        elif event.released:
            # 如果是長按後放開
            if is_in_switch_mode:
                # 並且期間沒有旋轉過，就觸發麥克風靜音
                if not rotation_during_press and not unlock_triggered:
                    serial.write(b"MIC_MUTE\n")
            # 否則，就是短按 (且非解鎖操作)
            elif not unlock_triggered:
                 serial.write(b"MUTE\n")
            
            button_down_time = None
            is_in_switch_mode = False

    # (模式判斷邏輯不變)
    if button_down_time is not None:
        press_duration = time.monotonic() - button_down_time
        if not is_in_switch_mode and press_duration >= LONG_PRESS_S:
            is_in_switch_mode = True
        if is_in_switch_mode and not unlock_triggered and press_duration >= UNLOCK_PRESS_S:
            serial.write(b"UNLOCK\n")
            unlock_triggered = True
            for _ in range(3):
                pixels.fill((255, 255, 255)); pixels.show(); time.sleep(0.05)
                pixels.fill((0, 0, 0)); pixels.show(); time.sleep(0.05)
    
    time.sleep(0.001)
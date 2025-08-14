# code.py - 亮度控制版
# 功能: 1. 新增雙擊進入/退出「亮度調節模式」。
#       2. 在亮度模式下，旋轉可調節LED亮度。

import time
import board
import rotaryio
import keypad
import usb_cdc
import neopixel

# --- 設定 ---
NEOPIXEL_PIN = board.GP0
NUM_PIXELS = 15
LONG_PRESS_S = 0.5
UNLOCK_PRESS_S = 3.0
DOUBLE_CLICK_S = 0.4 # 雙擊的有效時間間隔 (秒)

# --- 初始化 ---
encoder = rotaryio.IncrementalEncoder(board.GP2, board.GP3)
keys = keypad.Keys(pins=(board.GP4,), value_when_pressed=False, pull=True)
serial = usb_cdc.console
pixels = neopixel.NeoPixel(NEOPIXEL_PIN, NUM_PIXELS, brightness=0.3, auto_write=False)

# --- 狀態變數 ---
last_position = encoder.position
button_down_time = None
is_in_switch_mode = False
unlock_triggered = False
rotation_during_press = False

# 新增：控制模式與亮度相關變數
control_mode = "VOLUME"  # "VOLUME" 或 "BRIGHTNESS"
current_brightness = 0.3 # 初始亮度
last_click_time = 0      # 用於判斷雙擊

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

print("--- RP2040 韌體已啟動 (亮度控制版) ---")
update_volume_leds(0)
incoming_buffer = ""

# --- 主迴圈 (邏輯重大更新) ---
while True:
    # (接收電腦指令的邏輯不變)
    if serial.in_waiting > 0:
        incoming_buffer += serial.read(serial.in_waiting).decode()
        if "\n" in incoming_buffer:
            line, incoming_buffer = incoming_buffer.split("\n", 1)
            if line.startswith("V:"):
                try: update_volume_leds(int(line[2:]))
                except (ValueError, IndexError): pass

    # --- 旋轉邏輯更新：根據模式決定行為 ---
    current_position = encoder.position
    if current_position != last_position:
        # 如果在亮度模式
        if control_mode == "BRIGHTNESS":
            if current_position > last_position: # 順時針增加亮度
                current_brightness = min(1.0, current_brightness + 0.01)
            else: # 逆時針減少亮度
                current_brightness = max(0.01, current_brightness - 0.01)
            pixels.brightness = current_brightness
            pixels.show() # 立刻應用亮度
        # 如果在音量模式 (且長按切換App中)
        elif is_in_switch_mode:
            rotation_during_press = True
            serial.write(b"NEXT_APP\n" if current_position > last_position else b"PREV_APP\n")
        # 預設的音量模式
        else:
            serial.write(b"UP\n" if current_position > last_position else b"DOWN\n")
        last_position = current_position

    # --- 按鈕事件邏輯更新：加入雙擊判斷 ---
    event = keys.events.get()
    if event:
        if event.pressed:
            # 判斷雙擊
            time_since_last_click = time.monotonic() - last_click_time
            if time_since_last_click < DOUBLE_CLICK_S:
                # --- 觸發雙擊 ---
                if control_mode == "VOLUME":
                    control_mode = "BRIGHTNESS"
                    # 提示進入亮度模式：閃爍白色
                    pixels.fill((255, 255, 255)); pixels.show(); time.sleep(0.1)
                    pixels.show() # 恢復原樣
                else:
                    control_mode = "VOLUME"
                    # 提示回到音量模式：閃爍藍色
                    pixels.fill((0, 0, 255)); pixels.show(); time.sleep(0.1)
                    pixels.show() # 恢復原樣
                
                last_click_time = 0 # 重置雙擊計時，防止三擊
                button_down_time = None # 雙擊後不觸發長按或短按
            else:
                # --- 記錄單擊 ---
                button_down_time = time.monotonic()
                is_in_switch_mode = False
                unlock_triggered = False
                rotation_during_press = False
                last_click_time = time.monotonic()

        elif event.released:
            # 只有在非雙擊的情況下，才處理長短按
            if button_down_time is not None:
                if is_in_switch_mode:
                    if not rotation_during_press and not unlock_triggered:
                        serial.write(b"MIC_MUTE\n")
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
            # ... 解鎖提示燈光 ...
            for _ in range(3):
                pixels.fill((255, 255, 255)); pixels.show(); time.sleep(0.05)
                pixels.fill((0, 0, 0)); pixels.show(); time.sleep(0.05)
                
    time.sleep(0.001)
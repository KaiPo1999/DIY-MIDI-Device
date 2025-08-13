# code.py - 自動偵測版
# 功能：新增超長按(3秒)來發送 "UNLOCK" 指令，以返回自動模式

import time
import board
import rotaryio
import keypad
import usb_cdc
import neopixel

# --- NeoPixel 設定 ---
NEOPIXEL_PIN = board.GP0
NUM_PIXELS = 15

# --- 常數設定 ---
LONG_PRESS_S = 0.5      # 進入程式切換模式的延遲
UNLOCK_PRESS_S = 3.0    # 觸發解鎖的按壓時間

# --- 初始化 ---
encoder = rotaryio.IncrementalEncoder(board.GP2, board.GP3)
keys = keypad.Keys(pins=(board.GP4,), value_when_pressed=False, pull=True)
serial = usb_cdc.console
pixels = neopixel.NeoPixel(NEOPIXEL_PIN, NUM_PIXELS, brightness=0.3, auto_write=False)

# --- 狀態變數 ---
last_position = encoder.position
button_down_time = None
is_in_switch_mode = False
unlock_triggered = False  # 新增變數：記錄解鎖是否已觸發

# (此處省略 update_volume_leds 函式，與前一版相同)
def update_volume_leds(level):
    leds_to_light = round(level / 100 * NUM_PIXELS)
    for i in range(NUM_PIXELS):
        if i < leds_to_light:
            if i < NUM_PIXELS * 0.5: pixels[i] = (0, 255, 0)
            elif i < NUM_PIXELS * 0.8: pixels[i] = (255, 255, 0)
            else: pixels[i] = (255, 0, 0)
        else: pixels[i] = (0, 0, 0)
    pixels.show()

# --- 程式啟動 ---
print("--- RP2040 韌體已啟動 (自動偵測版) ---")
update_volume_leds(0)
incoming_buffer = ""

# --- 主迴圈 ---
while True:
    # (接收電腦指令的邏輯不變)
    if serial.in_waiting > 0:
        incoming_buffer += serial.read(serial.in_waiting).decode()
        if "\n" in incoming_buffer:
            line, incoming_buffer = incoming_buffer.split("\n", 1)
            if line.startswith("V:"):
                try: update_volume_leds(int(line[2:]))
                except (ValueError, IndexError): pass

    # (旋轉指令邏輯不變)
    current_position = encoder.position
    if current_position != last_position:
        if is_in_switch_mode:
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
            unlock_triggered = False # 每次按下都重置解鎖旗標
        elif event.released:
            if not is_in_switch_mode and not unlock_triggered:
                serial.write(b"MUTE\n")
            button_down_time = None
            is_in_switch_mode = False

    # --- 模式判斷邏輯更新 ---
    if button_down_time is not None:
        press_duration = time.monotonic() - button_down_time
        # 判斷是否進入程式切換模式
        if not is_in_switch_mode and press_duration >= LONG_PRESS_S:
            is_in_switch_mode = True
        
        # 新增：判斷是否觸發解鎖
        if is_in_switch_mode and not unlock_triggered and press_duration >= UNLOCK_PRESS_S:
            serial.write(b"UNLOCK\n")
            unlock_triggered = True
            # 可以加上燈光或震動提示，例如讓LED閃爍一下
            for _ in range(3):
                pixels.fill((255, 255, 255)); pixels.show(); time.sleep(0.05)
                pixels.fill((0, 0, 0)); pixels.show(); time.sleep(0.05)
    
    time.sleep(0.01)
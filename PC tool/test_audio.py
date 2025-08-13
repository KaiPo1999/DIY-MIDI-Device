# =========================================================================
#
#   中文註解:
#   腳本名稱: test_audio.py
#   功能: 這是一個初始測試腳本，用於驗證 `pycaw` 函式庫是否能在此 Windows
#         環境中正常運作。它會列出所有目前正在播放音訊的應用程式及其音量
#         和靜音狀態，是整個專案的第一步。
#
#   English Comment:
#   Script Name: test_audio.py
#   Function: This is an initial test script to verify that the `pycaw`
#             library is working correctly in this Windows environment. It
#             lists all applications currently playing audio, along with
#             their volume and mute status. It's the first step of the project.
#
#   Author: DIY設計
#   Date: 2025-08-12
#
# =========================================================================


# test_audio.py
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

def list_audio_sessions():
    """列出所有正在播放聲音的應用程式"""
    sessions = AudioUtilities.GetAllSessions()
    if not sessions:
        print("找不到任何正在播放音訊的應用程式。")
        return

    print("偵測到的音訊程式:")
    for i, session in enumerate(sessions):
        if session.Process:
            print(f"  [{i}] - 程式: {session.Process.name()}")
        # 取得音量控制器介面
        volume = session.SimpleAudioVolume
        print(f"      音量: {volume.GetMasterVolume():.0%}, 靜音: {bool(volume.GetMute())}")

if __name__ == "__main__":
    print("--- 開始偵測 Windows 音訊 ---")
    # 為了看到效果，請先在背景播放一些音樂或影片 (例如 YouTube, Spotify)
    input("請先播放一些聲音，然後按 Enter 繼續...")
    list_audio_sessions()
    print("--- 偵測結束 ---")
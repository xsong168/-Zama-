#!/usr/bin/env python3
"""
V26.0 Zeabur Keepalive - 云端守护进程
功能：监控母机进程，一旦被杀掉立即自动拉起
"""
import os
import sys
import time
import subprocess
import signal

PROCESS_NAME = "bot.py"
CHECK_INTERVAL = 10  # 每10秒检查一次
MAX_RESTARTS = 100  # 最大重启次数（防止无限循环）

restart_count = 0

def is_process_running(process_name: str) -> bool:
    """检查进程是否运行"""
    try:
        # Linux 环境使用 ps
        if os.path.exists("/tmp"):
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return process_name in result.stdout
        else:
            # Windows 环境使用 tasklist
            result = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "python" in result.stdout.lower()
    except Exception as e:
        print(f"[守护进程] 检查进程失败: {e}")
        return True  # 检查失败则假定进程在运行

def start_bot_process():
    """启动 bot.py 进程"""
    global restart_count
    restart_count += 1
    
    print(f"\n[守护进程] 启动母机进程 (重启次数: {restart_count})")
    
    try:
        # 后台启动 bot.py
        subprocess.Popen(
            [sys.executable, "bot.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        print("[守护进程] 母机进程已启动")
        return True
    except Exception as e:
        print(f"[守护进程] 启动失败: {e}")
        return False

def signal_handler(signum, frame):
    """信号处理器（优雅退出）"""
    print("\n[守护进程] 收到退出信号，停止监控")
    sys.exit(0)

def main():
    """守护进程主循环"""
    print("="*60)
    print("V26.0 Zeabur Keepalive - 云端守护进程已启动")
    print(f"监控进程: {PROCESS_NAME}")
    print(f"检查间隔: {CHECK_INTERVAL}秒")
    print(f"最大重启: {MAX_RESTARTS}次")
    print("="*60)
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 首次启动
    if not is_process_running(PROCESS_NAME):
        print("[守护进程] 母机进程未运行，正在启动...")
        start_bot_process()
        time.sleep(5)  # 等待进程启动
    else:
        print("[守护进程] 母机进程已在运行")
    
    # 监控循环
    while restart_count < MAX_RESTARTS:
        time.sleep(CHECK_INTERVAL)
        
        if not is_process_running(PROCESS_NAME):
            print(f"\n[守护进程] 检测到母机进程已停止！")
            print(f"[守护进程] 正在自动拉起...")
            
            if start_bot_process():
                time.sleep(5)  # 等待进程启动
                print("[守护进程] 母机进程已恢复")
            else:
                print("[守护进程] 母机进程拉起失败，5秒后重试")
                time.sleep(5)
        else:
            # 静默运行，不输出日志（避免刷屏）
            pass
    
    print(f"\n[守护进程] 已达最大重启次数 ({MAX_RESTARTS})，停止监控")
    print("[守护进程] 请检查母机进程是否存在严重错误")

if __name__ == "__main__":
    # 检查是否在云端环境
    if os.getenv("ZEABUR") == "1" or os.path.exists("/tmp"):
        main()
    else:
        print("[守护进程] 非云端环境，守护进程已禁用")
        print("[提示] 本地环境请直接运行 bot.py")

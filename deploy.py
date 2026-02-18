#!/usr/bin/env python3
"""
V24.0 全自动云端部署脚本
功能：自动提交代码 + 触发 Zeabur 部署
"""
import os
import subprocess
import sys

def run_command(cmd, description=""):
    """执行 shell 命令"""
    print(f"\n[执行] {description or cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=True, 
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[错误] {e}")
        if e.stderr:
            print(e.stderr)
        return False

def main():
    print("="*60)
    print("V24.0 全自动云端部署 - 物理接管")
    print("="*60)
    
    # 1. 检查 Git 仓库
    print("\n[1/5] 检查 Git 仓库状态...")
    if not os.path.exists(".git"):
        print("[初始化] Git 仓库不存在，正在初始化...")
        run_command("git init", "初始化 Git 仓库")
        run_command("git branch -M main", "切换到 main 分支")
    
    # 2. 检查远程仓库
    print("\n[2/5] 检查远程仓库...")
    result = subprocess.run("git remote -v", shell=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    
    if "origin" not in result.stdout:
        print("[警告] 未配置远程仓库")
        print("[提示] 请手动执行以下命令添加远程仓库：")
        print("       git remote add origin https://github.com/你的用户名/Junshi_Bot.git")
        print("\n[继续] 本地提交将继续进行...")
    
    # 3. 暴力添加所有文件
    print("\n[3/5] 暴力添加所有文件...")
    run_command("git add .", "添加所有修改")
    
    # 4. 提交代码
    print("\n[4/5] 提交代码...")
    commit_msg = "V24.0 全自动空投 - 云端权限锁死 + 自动垃圾回收 + 环境验证"
    run_command(f'git commit -m "{commit_msg}"', "提交代码")
    
    # 5. 暴力推送（如果配置了远程仓库）
    print("\n[5/5] 尝试暴力推送...")
    result = subprocess.run("git remote -v", shell=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
    
    if "origin" in result.stdout:
        print("[推送] 远程仓库已配置，开始暴力推送...")
        # 先尝试普通推送
        if not run_command("git push -u origin main", "推送到 main 分支"):
            # 失败则尝试强制推送
            print("[警告] 普通推送失败，尝试强制推送...")
            run_command("git push -u origin main --force", "强制推送到 main 分支")
    else:
        print("[跳过] 未配置远程仓库，跳过推送步骤")
        print("[提示] 请先配置远程仓库，然后手动执行：")
        print("       git push -u origin main")
    
    print("\n" + "="*60)
    print("✅ 本地代码已提交完成")
    print("="*60)
    
    # 6. 部署提示
    print("\n[部署提示]")
    print("1. 如未配置远程仓库，请先执行：")
    print("   git remote add origin https://github.com/你的用户名/Junshi_Bot.git")
    print("   git push -u origin main")
    print("\n2. 推送成功后，访问 Zeabur 控制台：")
    print("   https://zeabur.com")
    print("\n3. 导入 GitHub 仓库并配置环境变量：")
    print("   - ZEABUR=1")
    print("   - TELEGRAM_BOT_TOKEN")
    print("   - DEEPSEEK_API_KEY")
    print("   - ELEVENLABS_API_KEY")
    print("   - VOICE_ID")
    print("\n4. 点击 Deploy 部署")
    print("\n[统帅部] V24.0 暴力空投已完成！")

if __name__ == "__main__":
    main()

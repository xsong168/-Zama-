#!/usr/bin/env python3
"""
Telegram Group ID Sniffer
坐标嗅探器：暴力抓取 Telegram 群组 ID
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def sniff_group_id():
    """
    坐标嗅探器：暴力抓取群组 ID
    """
    print("="*60)
    print("[SNIFFER] Telegram Group ID Sniffer - 坐标嗅探器")
    print("="*60)
    
    if not TELEGRAM_BOT_TOKEN:
        print("\n[ERROR] TELEGRAM_BOT_TOKEN is missing in .env")
        print("[ACTION] Please add TELEGRAM_BOT_TOKEN to .env file")
        return
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("\n[SNIFFER] Fetching updates from Telegram Bot API...")
            
            # 暴力抓取：获取最近的所有消息
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            response = await client.get(url)
            
            if response.status_code != 200:
                print(f"\n[ERROR] Failed to fetch updates: {response.status_code}")
                print(f"[ERROR] Response: {response.text}")
                return
            
            data = response.json()
            
            if not data.get("ok"):
                print(f"\n[ERROR] API returned error: {data}")
                return
            
            updates = data.get("result", [])
            
            if not updates:
                print("\n[WARNING] No updates found!")
                print("\n[ACTION REQUIRED]")
                print("  1. Add your bot to the target group")
                print("  2. Send a message in the group containing: 军师点火")
                print("  3. Run this sniffer again: python sniffer.py")
                return
            
            print(f"\n[SNIFFER] Found {len(updates)} updates")
            print("\n" + "="*60)
            print("[ANALYSIS] Searching for keyword: 军师点火")
            print("="*60 + "\n")
            
            found_groups = []
            all_chats = []
            
            # 遍历所有更新
            for update in updates:
                message = update.get("message", {})
                if not message:
                    continue
                
                text = message.get("text", "")
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                chat_type = chat.get("type")
                chat_title = chat.get("title", "Private Chat")
                from_user = message.get("from", {})
                username = from_user.get("username", "Unknown")
                first_name = from_user.get("first_name", "Unknown")
                
                # 记录所有群组/频道
                if chat_type in ["group", "supergroup", "channel"]:
                    all_chats.append({
                        "chat_id": chat_id,
                        "chat_type": chat_type,
                        "chat_title": chat_title,
                        "has_keyword": "军师" in text
                    })
                
                # 检查是否包含关键词
                if "军师点火" in text or "军师" in text:
                    found_groups.append({
                        "chat_id": chat_id,
                        "chat_type": chat_type,
                        "chat_title": chat_title,
                        "username": username,
                        "first_name": first_name,
                        "text": text
                    })
                    
                    print(f"[MATCH FOUND] OK")
                    print(f"  Chat ID: {chat_id}")
                    print(f"  Chat Type: {chat_type}")
                    print(f"  Chat Title: {chat_title}")
                    print(f"  From: {first_name} (@{username})")
                    print(f"  Message: {text}")
                    print("-" * 60)
            
            # 显示结果
            if found_groups:
                print("\n" + "="*60)
                print("[SUCCESS] Group IDs Found with Keyword '军师':")
                print("="*60)
                
                for match in found_groups:
                    if match["chat_type"] in ["group", "supergroup"]:
                        print(f"\n[OK] GROUP CHAT ID: {match['chat_id']}")
                        print(f"  Title: {match['chat_title']}")
                        print(f"  Type: {match['chat_type']}")
                        print(f"\n  [COPY THIS TO .env FILE]")
                        print(f"  TELEGRAM_CHAT_ID={match['chat_id']}")
                        print("-" * 60)
            
            elif all_chats:
                print("\n[WARNING] No messages with keyword '军师点火' found")
                print("\n[INFO] But found these groups where bot is present:")
                print("="*60)
                
                for chat in all_chats:
                    print(f"\n  Chat ID: {chat['chat_id']}")
                    print(f"  Title: {chat['chat_title']}")
                    print(f"  Type: {chat['chat_type']}")
                    
                print("\n[ACTION] Please send '军师点火' in your target group and run again")
            
            else:
                print("\n[WARNING] No group chats found in recent updates")
                print("\n[INFO] Showing all recent messages:")
                print("="*60)
                
                for i, update in enumerate(updates[-10:], 1):
                    message = update.get("message", {})
                    if not message:
                        continue
                    
                    text = message.get("text", "")
                    chat = message.get("chat", {})
                    chat_id = chat.get("id")
                    chat_type = chat.get("type")
                    chat_title = chat.get("title", "Private")
                    
                    print(f"\n  [{i}] Chat ID: {chat_id}")
                    print(f"      Type: {chat_type}")
                    print(f"      Title: {chat_title}")
                    print(f"      Message: {text[:100]}...")
                
                print("\n[ACTION REQUIRED]")
                print("  1. Make sure bot is added to your group")
                print("  2. Send message '军师点火' in the group")
                print("  3. Run this sniffer again: python sniffer.py")
            
            print("\n" + "="*60)
            print("[SNIFFER] Analysis complete")
            print("="*60)
            
    except Exception as e:
        print(f"\n[ERROR] Sniffer exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n[SNIFFER] 坐标嗅探器已就绪，请在群内发送触发词！")
    print("[TRIGGER] 触发词: 军师点火")
    print()
    asyncio.run(sniff_group_id())

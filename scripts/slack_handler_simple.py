#!/usr/bin/env python3
"""
Simple Slack Handler — Pure Python, no external dependencies except requests.

Polls Slack API for direct messages and routes to correct tier agent.

Usage:
    python3 slack_handler_simple.py
"""

import os
import sys
import json
import time
import requests
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model-routing'))
from model_router import route

class SimpleSlackHandler:
    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.nikhil_id = "U04H3EB2PTN"
        
        if not self.bot_token:
            print("❌ SLACK_BOT_TOKEN not set")
            sys.exit(1)
        
        self.base_url = "https://slack.com/api"
        self.last_ts = None
        print("[SlackHandler] Initialized and listening for DMs...")
    
    def log(self, msg):
        """Log with timestamp"""
        print(f"[{datetime.now().isoformat()}] {msg}")
    
    def classify_message(self, text: str) -> str:
        """Classify to agent tier"""
        try:
            result = route(text)
            tier = result.level.split("_")[0] if "_" in result.level else result.level
            agent_id = f"nova-{tier}"
            return agent_id
        except Exception as e:
            self.log(f"⚠️ Classification error: {e}. Defaulting to nova-l2")
            return "nova-l2"
    
    def get_direct_messages(self):
        """Fetch recent DMs"""
        try:
            headers = {"Authorization": f"Bearer {self.bot_token}"}
            
            # Get list of DM channels
            params = {"limit": 10}
            resp = requests.get(
                f"{self.base_url}/conversations.list",
                headers=headers,
                params=params,
                timeout=5
            )
            
            if not resp.ok:
                self.log(f"⚠️ API error: {resp.status_code}")
                return []
            
            data = resp.json()
            if not data.get("ok"):
                self.log(f"⚠️ Slack error: {data.get('error')}")
                return []
            
            messages = []
            for channel in data.get("channels", []):
                # Only process DMs with Nikhil
                if channel.get("is_dm") and channel.get("user") == self.nikhil_id:
                    channel_id = channel["id"]
                    
                    # Get messages from this channel
                    msg_params = {"channel": channel_id, "limit": 5}
                    if self.last_ts:
                        msg_params["oldest"] = self.last_ts
                    
                    msg_resp = requests.get(
                        f"{self.base_url}/conversations.history",
                        headers=headers,
                        params=msg_params,
                        timeout=5
                    )
                    
                    if msg_resp.ok:
                        msg_data = msg_resp.json()
                        for msg in reversed(msg_data.get("messages", [])):
                            # Only process messages from Nikhil
                            if msg.get("user") == self.nikhil_id and msg.get("type") == "message":
                                messages.append({
                                    "channel": channel_id,
                                    "text": msg.get("text", ""),
                                    "ts": msg.get("ts"),
                                    "user": msg.get("user")
                                })
            
            return messages
        except requests.exceptions.RequestException as e:
            self.log(f"⚠️ Request error: {e}")
            return []
    
    def spawn_agent(self, agent_id: str, message: str) -> bool:
        """Spawn OpenClaw session with routed agent"""
        try:
            cmd = [
                "openclaw",
                "sessions",
                "spawn",
                "--agent-id", agent_id,
                "--message", message,
                "--timeout-seconds", "60"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=65)
            
            if result.returncode != 0:
                self.log(f"❌ Session spawn failed: {result.stderr}")
                return False
            
            self.log(f"✅ Spawned {agent_id.upper()} session")
            return True
        except Exception as e:
            self.log(f"❌ Failed to spawn session: {e}")
            return False
    
    def send_response(self, channel_id: str, text: str) -> bool:
        """Send response back to Slack"""
        try:
            headers = {"Authorization": f"Bearer {self.bot_token}"}
            payload = {"channel": channel_id, "text": text}
            
            resp = requests.post(
                f"{self.base_url}/chat.postMessage",
                headers=headers,
                json=payload,
                timeout=5
            )
            
            if not resp.ok or not resp.json().get("ok"):
                self.log(f"⚠️ Failed to send response")
                return False
            
            return True
        except Exception as e:
            self.log(f"⚠️ Response send error: {e}")
            return False
    
    def process_message(self, msg: dict) -> None:
        """Process a single message"""
        text = msg.get("text", "").strip()
        channel_id = msg.get("channel")
        ts = msg.get("ts")
        
        if not text or not channel_id:
            return
        
        self.log(f"📨 DM from Nikhil: '{text[:50]}...'")
        
        # Classify and route
        agent_id = self.classify_message(text)
        self.log(f"🎯 Classified → {agent_id.upper()}")
        
        # Spawn session
        spawned = self.spawn_agent(agent_id, text)
        
        # Send response
        if spawned:
            response = f"✅ Processing with {agent_id.upper()}"
        else:
            response = f"❌ Failed to spawn {agent_id.upper()} (using fallback)"
        
        self.send_response(channel_id, response)
        
        # Update last_ts
        self.last_ts = ts
    
    def run(self) -> None:
        """Main loop"""
        self.log("🚀 Starting Slack DM router...")
        poll_interval = 5
        
        try:
            while True:
                messages = self.get_direct_messages()
                
                for msg in messages:
                    self.process_message(msg)
                
                time.sleep(poll_interval)
        
        except KeyboardInterrupt:
            self.log("🛑 Handler stopped")
            sys.exit(0)
        except Exception as e:
            self.log(f"❌ Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    handler = SimpleSlackHandler()
    handler.run()

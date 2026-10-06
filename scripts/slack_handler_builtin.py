#!/usr/bin/env python3
"""
Slack Handler (Pure Python Built-ins) — No external dependencies.

Uses urllib instead of requests. Polls Slack API for DMs and routes to agents.

Usage:
    python3 slack_handler_builtin.py
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model-routing'))
from model_router import route

class SlackHandler:
    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.peter_id = "PETER_SLACK_USER_ID_TODO"
        
        if not self.bot_token:
            print("❌ SLACK_BOT_TOKEN not set")
            sys.exit(1)
        
        self.base_url = "https://slack.com/api"
        self.last_ts = None
        self.dm_channel = None
        self.log("✅ Initialized and listening for DMs from Peter...")
    
    def log(self, msg):
        """Log with timestamp"""
        print(f"[{datetime.now().isoformat()}] {msg}", flush=True)
    
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
    
    def api_call(self, method: str, **kwargs) -> dict:
        """Make Slack API call"""
        try:
            params = "&".join(f"{k}={v}" for k, v in kwargs.items())
            url = f"{self.base_url}/{method}?{params}"
            
            headers = {"Authorization": f"Bearer {self.bot_token}"}
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            self.log(f"⚠️ HTTP {e.code}: {e.reason}")
            return {"ok": False}
        except Exception as e:
            self.log(f"⚠️ API error: {e}")
            return {"ok": False}
    
    def get_dm_channel(self):
        """Get or find DM channel with Peter"""
        if self.dm_channel:
            return self.dm_channel
        
        try:
            # List all conversations
            data = self.api_call("conversations.list", limit="50")
            
            if not data.get("ok"):
                return None
            
            for channel in data.get("channels", []):
                # Find DM with Peter
                if channel.get("is_dm") and channel.get("user") == self.peter_id:
                    self.dm_channel = channel["id"]
                    self.log(f"Found DM channel: {self.dm_channel}")
                    return self.dm_channel
            
            return None
        except Exception as e:
            self.log(f"⚠️ Error finding DM channel: {e}")
            return None
    
    def get_messages(self) -> list:
        """Get recent messages from DM channel"""
        channel = self.get_dm_channel()
        if not channel:
            return []
        
        try:
            params = {"channel": channel, "limit": "5"}
            if self.last_ts:
                params["oldest"] = self.last_ts
            
            data = self.api_call("conversations.history", **params)
            
            if not data.get("ok"):
                return []
            
            messages = []
            for msg in reversed(data.get("messages", [])):
                # Only process messages from Peter
                if msg.get("user") == self.peter_id and msg.get("type") == "message":
                    messages.append({
                        "channel": channel,
                        "text": msg.get("text", ""),
                        "ts": msg.get("ts"),
                        "user": msg.get("user")
                    })
            
            return messages
        except Exception as e:
            self.log(f"⚠️ Error getting messages: {e}")
            return []
    
    def spawn_agent(self, agent_id: str, message: str) -> bool:
        """Spawn OpenClaw session"""
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
                self.log(f"❌ Spawn failed: {result.stderr[:100]}")
                return False
            
            self.log(f"✅ Spawned {agent_id.upper()}")
            return True
        except Exception as e:
            self.log(f"❌ Spawn error: {e}")
            return False
    
    def send_response(self, channel_id: str, text: str) -> bool:
        """Send response to Slack"""
        try:
            # Use JSON POST for chat.postMessage
            url = f"{self.base_url}/chat.postMessage"
            payload = json.dumps({"channel": channel_id, "text": text}).encode()
            headers = {
                "Authorization": f"Bearer {self.bot_token}",
                "Content-Type": "application/json"
            }
            
            req = urllib.request.Request(url, data=payload, headers=headers)
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("ok", False)
        except Exception as e:
            self.log(f"⚠️ Send error: {e}")
            return False
    
    def process_message(self, msg: dict) -> None:
        """Process a single message"""
        text = msg.get("text", "").strip()
        channel = msg.get("channel")
        ts = msg.get("ts")
        
        if not text:
            return
        
        self.log(f"📨 DM: '{text[:60]}...'")
        
        # Classify
        agent_id = self.classify_message(text)
        self.log(f"🎯 → {agent_id.upper()}")
        
        # Spawn
        spawned = self.spawn_agent(agent_id, text)
        
        # Respond
        response = f"✅ {agent_id.upper()}" if spawned else f"⚠️ {agent_id.upper()} (fallback)"
        self.send_response(channel, response)
        
        # Update timestamp
        self.last_ts = ts
    
    def run(self) -> None:
        """Main loop"""
        self.log("🚀 Handler starting...")
        
        try:
            while True:
                messages = self.get_messages()
                
                for msg in messages:
                    self.process_message(msg)
                
                time.sleep(5)  # Poll every 5 seconds
        
        except KeyboardInterrupt:
            self.log("🛑 Handler stopped")
        except Exception as e:
            self.log(f"❌ Fatal error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    handler = SlackHandler()
    handler.run()

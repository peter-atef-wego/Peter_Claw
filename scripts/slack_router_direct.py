#!/usr/bin/env python3
"""
Direct Slack Router — Responds immediately to @mentions and DMs.

Simpler approach: Don't poll, let Slack send events directly.
Use Slack app Event Subscriptions → Route DMs to this endpoint.

For now: Manual polling with better debugging.
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

class DirectSlackRouter:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.peter_id = "PETER_SLACK_USER_ID_TODO"
        self.base_url = "https://slack.com/api"
        
        if not self.token:
            print("❌ SLACK_BOT_TOKEN not set")
            sys.exit(1)
        
        print("✅ Initialized", flush=True)
    
    def api_call(self, method, **params):
        """Make API call with detailed error logging"""
        try:
            param_str = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{self.base_url}/{method}?{param_str}"
            
            headers = {"Authorization": f"Bearer {self.token}"}
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return data
        except Exception as e:
            print(f"❌ API {method} error: {e}", flush=True)
            return {"ok": False, "error": str(e)}
    
    def classify(self, text):
        """Classify message"""
        try:
            result = route(text)
            tier = result.level.split("_")[0] if "_" in result.level else result.level
            return f"nova-{tier}"
        except:
            return "nova-l2"
    
    def spawn_agent(self, agent_id, msg):
        """Spawn agent with message"""
        try:
            cmd = ["openclaw", "sessions", "spawn", "--agent-id", agent_id, "--message", msg, "--timeout-seconds", "30"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            return result.returncode == 0
        except:
            return False
    
    def send_msg(self, channel, text):
        """Send message to channel"""
        data = self.api_call("chat.postMessage", channel=channel, text=text)
        return data.get("ok", False)
    
    def get_channels(self):
        """Get all DM channels"""
        data = self.api_call("conversations.list", types="im", limit="100")
        if not data.get("ok"):
            return []
        return data.get("channels", [])
    
    def get_messages(self, channel, oldest=None):
        """Get messages from channel"""
        params = {"channel": channel, "limit": "10"}
        if oldest:
            params["oldest"] = oldest
        
        data = self.api_call("conversations.history", **params)
        if not data.get("ok"):
            return []
        
        return data.get("messages", [])
    
    def run(self):
        """Main loop"""
        print("🚀 Starting Direct Slack Router", flush=True)
        last_seen = {}  # Track last seen ts per channel
        
        while True:
            try:
                channels = self.get_channels()
                print(f"📡 Found {len(channels)} DM channels", flush=True)
                
                for channel in channels:
                    ch_id = channel["id"]
                    user = channel.get("user")
                    
                    # Only process Peter's DMs
                    if user != self.peter_id:
                        continue
                    
                    print(f"📨 Checking Peter's DM channel: {ch_id}", flush=True)
                    
                    # Get messages
                    oldest = last_seen.get(ch_id)
                    msgs = self.get_messages(ch_id, oldest)
                    
                    if not msgs:
                        print(f"   No new messages", flush=True)
                        continue
                    
                    print(f"   Found {len(msgs)} messages", flush=True)
                    
                    for msg in reversed(msgs):
                        # Only process user messages
                        if msg.get("user") != self.peter_id or msg.get("type") != "message":
                            continue
                        
                        text = msg.get("text", "").strip()
                        ts = msg.get("ts")
                        
                        if not text:
                            continue
                        
                        print(f"   💬 Message: '{text[:50]}...'", flush=True)
                        
                        # Classify
                        agent = self.classify(text)
                        print(f"   🎯 Routed to: {agent.upper()}", flush=True)
                        
                        # Spawn
                        spawned = self.spawn_agent(agent, text)
                        print(f"   {'✅' if spawned else '❌'} Agent spawned", flush=True)
                        
                        # Respond
                        resp = f"✅ {agent.upper()}" if spawned else f"⚠️ {agent.upper()}"
                        self.send_msg(ch_id, resp)
                        
                        # Update last seen
                        last_seen[ch_id] = ts
                
                print("⏳ Waiting 5s...", flush=True)
                time.sleep(5)
            
            except KeyboardInterrupt:
                print("🛑 Stopped", flush=True)
                break
            except Exception as e:
                print(f"❌ Error: {e}", flush=True)
                time.sleep(5)

if __name__ == "__main__":
    import urllib.parse
    router = DirectSlackRouter()
    router.run()

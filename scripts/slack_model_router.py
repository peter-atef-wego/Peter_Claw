#!/usr/bin/env python3
"""
Slack Model Router — Routes DMs to correct tier and shows classification.

RULE: Show tier ONLY in personal DMs to Peter. NEVER in Slack channels.
This is a classification-only router — actual response generation happens in the main NOVA session.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model-routing'))
from model_router import route

class SlackModelRouter:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.peter_id = "U0A05CNQQ07"
        self.base_url = "https://slack.com/api"
        
        if not self.token:
            print("❌ SLACK_BOT_TOKEN not set", flush=True)
            sys.exit(1)
        
        self.models = {
            "l1": "anthropic/claude-sonnet-4.6",
            "l2": "openai/gpt-4o-mini",
            "l3": "anthropic/claude-sonnet-4.6",
            "l4": "anthropic/claude-opus-4.8"
        }
        
        print("✅ Initialized", flush=True)
    
    def api_call(self, method, **params):
        """Make Slack API call"""
        try:
            param_str = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
            url = f"{self.base_url}/{method}?{param_str}"
            headers = {"Authorization": f"Bearer {self.token}"}
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"❌ API error: {e}", flush=True)
            return {"ok": False}
    
    def classify(self, text):
        """Classify to tier and return model"""
        try:
            result = route(text)
            tier = result.level.split("_")[0] if "_" in result.level else result.level
            model = self.models.get(tier, self.models["l2"])
            return tier, model
        except:
            return "l2", self.models["l2"]
    
    def get_peter_dm_channel(self):
        """Get Peter's DM channel ID"""
        try:
            data = self.api_call("conversations.list", types="im", limit="100")
            if not data.get("ok"):
                return None
            
            for channel in data.get("channels", []):
                if channel.get("user") == self.peter_id:
                    return channel["id"]
            
            return None
        except:
            return None
    
    def get_new_messages(self, channel, oldest=None):
        """Get new messages from channel"""
        try:
            params = {"channel": channel, "limit": "10"}
            if oldest:
                params["oldest"] = oldest
            
            data = self.api_call("conversations.history", **params)
            if not data.get("ok"):
                return []
            
            messages = []
            for msg in reversed(data.get("messages", [])):
                if msg.get("user") == self.peter_id and msg.get("type") == "message":
                    text = msg.get("text", "").strip()
                    if text:
                        messages.append({
                            "text": text,
                            "ts": msg.get("ts"),
                            "channel": channel
                        })
            
            return messages
        except Exception as e:
            print(f"❌ Get messages error: {e}", flush=True)
            return []
    
    def run(self):
        """Main loop — classify DMs and show tier"""
        print("🚀 Starting Slack Model Router", flush=True)
        
        channel = self.get_peter_dm_channel()
        if not channel:
            print("❌ Could not find Peter's DM channel", flush=True)
            return
        
        print(f"✅ Found DM channel: {channel}", flush=True)
        last_ts = None
        
        while True:
            try:
                messages = self.get_new_messages(channel, last_ts)
                
                for msg in messages:
                    text = msg["text"]
                    ts = msg["ts"]
                    
                    print(f"📨 Message: '{text[:50]}...'", flush=True)
                    
                    # Classify
                    tier, model = self.classify(text)
                    print(f"🎯 Tier: {tier.upper()} → Model: {model}", flush=True)
                    
                    # RULE: Show tier ONLY in personal DMs (not in channels)
                    response = f"🎯 **{tier.upper()}**"
                    self.api_call("chat.postMessage", channel=channel, text=response)
                    
                    # Note: Actual response generation happens in the main session
                    # This router is classification-only
                    
                    last_ts = ts
                
                time.sleep(5)
            
            except KeyboardInterrupt:
                print("🛑 Stopped", flush=True)
                break
            except Exception as e:
                print(f"❌ Error: {e}", flush=True)
                time.sleep(5)

if __name__ == "__main__":
    import urllib.parse
    router = SlackModelRouter()
    router.run()

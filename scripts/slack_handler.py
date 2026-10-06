#!/usr/bin/env python3
"""
Custom Slack Handler — Intercepts DMs and auto-routes to correct tier agent.

This handler:
1. Listens for incoming DMs from Peter
2. Classifies message to tier (L1-L4)
3. Spawns correct agent session (nova-l1/l2/l3/l4)
4. Executes with routed model

Setup:
1. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables
2. Run: python3 slack_handler.py
3. Handler runs continuously, intercepting DMs
"""

import os
import sys
import json
import subprocess
import logging
from typing import Optional

# Add model-routing to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'model-routing'))

from model_router import route

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger('SlackHandler')

# Peter's user ID (authorized only)
PETER_USER_ID = "PETER_SLACK_USER_ID_TODO"

class SlackDMRouter:
    """Routes Slack DMs to correct tier agent."""
    
    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.app_token = os.getenv("SLACK_APP_TOKEN")
        
        if not self.bot_token or not self.app_token:
            logger.error("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN")
            sys.exit(1)
        
        logger.info("Slack DM Router initialized")
    
    def classify_message(self, message_text: str) -> str:
        """
        Classify message to tier and return agent ID.
        
        Returns: "nova-l1", "nova-l2", "nova-l3", or "nova-l4"
        """
        try:
            result = route(message_text)
            
            # Extract tier from result.level (e.g., "l2_fast" → "l2")
            if "_" in result.level:
                tier = result.level.split("_")[0]
            else:
                tier = result.level
            
            agent_id = f"nova-{tier}"
            logger.info(f"Classified: '{message_text[:40]}...' → {agent_id}")
            
            return agent_id
        except Exception as e:
            logger.error(f"Classification error: {e}. Defaulting to nova-l2")
            return "nova-l2"
    
    def spawn_agent_session(self, agent_id: str, message_text: str, user_id: str) -> Optional[str]:
        """
        Spawn an OpenClaw session with the routed agent.
        
        Returns: session ID if successful, None otherwise
        """
        try:
            cmd = [
                "openclaw",
                "sessions",
                "spawn",
                "--agent-id", agent_id,
                "--message", message_text,
                "--timeout-seconds", "60"
            ]
            
            logger.info(f"Spawning agent session: {agent_id}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=65)
            
            if result.returncode != 0:
                logger.error(f"Session spawn failed: {result.stderr}")
                return None
            
            logger.info(f"Session spawned successfully with {agent_id}")
            return result.stdout.strip()
        
        except Exception as e:
            logger.error(f"Failed to spawn session: {e}")
            return None
    
    def send_slack_response(self, channel_id: str, thread_ts: str, response_text: str) -> bool:
        """
        Send response back to Slack DM.
        """
        try:
            import slack_sdk
            
            client = slack_sdk.WebClient(token=self.bot_token)
            client.chat_postMessage(
                channel=channel_id,
                text=response_text,
                thread_ts=thread_ts
            )
            logger.info(f"Response sent to {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack response: {e}")
            return False
    
    def handle_dm(self, event: dict) -> None:
        """
        Handle incoming DM event.
        """
        # Verify sender is Peter
        user_id = event.get("user")
        if user_id != PETER_USER_ID:
            logger.warning(f"DM from unauthorized user: {user_id}")
            return
        
        message_text = event.get("text", "")
        channel_id = event.get("channel")
        thread_ts = event.get("ts")
        
        if not message_text or not channel_id:
            logger.warning("Invalid DM event structure")
            return
        
        logger.info(f"DM from Peter: '{message_text[:50]}...'")
        
        # Classify and get agent
        agent_id = self.classify_message(message_text)
        
        # Spawn session with routed agent
        session_id = self.spawn_agent_session(agent_id, message_text, user_id)
        
        if session_id:
            response = f"✅ Processing with {agent_id.upper()} — Session: {session_id}"
        else:
            response = f"❌ Failed to spawn {agent_id} session. Using default."
            agent_id = "nova-l2"
            self.spawn_agent_session(agent_id, message_text, user_id)
        
        # Send Slack response
        self.send_slack_response(channel_id, thread_ts, response)

def main():
    """
    Main entry point — sets up Slack listener.
    """
    logger.info("Starting Slack DM Router...")
    
    router = SlackDMRouter()
    
    # Try to use slack_bolt for socket mode listener
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
        
        app = App(token=router.bot_token)
        
        @app.message()
        def handle_message(body, logger_):
            """Handle any message event."""
            event = body.get("event", {})
            
            # Only process DMs (channel type = D)
            if event.get("channel_type") == "D":
                router.handle_dm(event)
        
        logger.info("Slack handler ready. Listening for DMs...")
        
        # Connect via Socket Mode
        handler = SocketModeHandler(app, router.app_token)
        handler.start()
    
    except ImportError:
        logger.error("slack_bolt not installed. Install with: pip install slack-bolt")
        logger.info("Alternatively, manually relay DMs to: python3 slack_dm_router.py '<message>'")
        sys.exit(1)

if __name__ == "__main__":
    main()

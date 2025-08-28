#!/usr/bin/env python3

import subprocess
import time
import json
import sys
from datetime import datetime

def colored(text, color):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'purple': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

def parse_log_line(line):
    try:
        if line.strip().startswith('{') and '"timestamp"' in line:
            return json.loads(line.strip())
    except:
        pass
    return None

def monitor_logs():
    print(colored("🔍 Live Auth Monitoring Started", 'green'))
    print(colored("Watching for authentication events...", 'cyan'))
    print(colored("=" * 80, 'blue'))
    
    # Start tailing the backend logs
    try:
        process = subprocess.Popen(
            ['tail', '-f', 'logs/backend.log'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        print(colored("📊 Monitoring backend logs for auth events...", 'yellow'))
        print(colored("Try logging in to your frontend now!", 'green'))
        print("")
        
        for line in process.stdout:
            if not line.strip():
                continue
                
            # Parse JSON log lines
            log_data = parse_log_line(line)
            if log_data:
                component = log_data.get('component', '')
                msg = log_data.get('msg', '')
                timestamp = log_data.get('timestamp', '')
                
                # Filter for auth-related events
                auth_keywords = ['auth', 'whoami', 'login', 'token', 'cookie', 'spotify', 'orchestrator']
                if any(keyword in msg.lower() or keyword in component.lower() for keyword in auth_keywords):
                    
                    # Color code by event type
                    if 'whoami' in msg.lower():
                        color = 'cyan'
                        icon = '🔍'
                    elif 'login' in msg.lower():
                        color = 'green'
                        icon = '📝'
                    elif 'token' in msg.lower():
                        color = 'purple'
                        icon = '🔐'
                    elif 'spotify' in msg.lower():
                        color = 'yellow'
                        icon = '🎵'
                    elif 'cookie' in msg.lower():
                        color = 'blue'
                        icon = '🍪'
                    else:
                        color = 'white'
                        icon = '📊'
                    
                    # Format timestamp
                    time_str = timestamp.split('T')[1][:8] if 'T' in timestamp else timestamp[:8]
                    
                    print(colored(f"{icon} [{time_str}] {component}: {msg}", color))
                    
                    # Show metadata for important events
                    meta = log_data.get('meta', {})
                    if meta and ('user_id' in meta or 'token_source' in meta or 'has_token' in meta):
                        relevant_meta = {}
                        for key in ['user_id', 'token_source', 'has_token', 'token_length', 'all_cookies', 'auth_header', 'origin']:
                            if key in meta:
                                relevant_meta[key] = meta[key]
                        if relevant_meta:
                            print(colored(f"   └─ {relevant_meta}", 'white'))
                    
                    print()  # Empty line for readability
            else:
                # Non-JSON lines (like INFO/WARNING from uvicorn)
                if any(keyword in line.lower() for keyword in ['auth', 'whoami', 'login', 'spotify']):
                    print(colored(f"📄 {line.strip()}", 'white'))
                    
    except KeyboardInterrupt:
        print(colored("\n🛑 Monitoring stopped", 'red'))
        process.terminate()
    except Exception as e:
        print(colored(f"❌ Error: {e}", 'red'))

if __name__ == "__main__":
    monitor_logs()

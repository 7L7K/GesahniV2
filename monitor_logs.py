#!/usr/bin/env python3
"""
Monitor server logs in real-time by capturing stdout from the running server.
"""

import subprocess
import sys
import time
import signal

def monitor_server_logs():
    """Monitor the running server logs in real-time."""
    try:
        # Kill any existing uvicorn processes
        subprocess.run(["pkill", "-f", "uvicorn"], check=False)

        print("🚀 Starting server with verbose logging...")
        print("📊 You should see detailed logs below:")
        print("=" * 80)

        # Start the server with logging enabled
        cmd = [
            "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--reload"
        ]

        env = {
            **dict(os.environ),
            "LOG_TO_STDOUT": "true",
            "DEBUG_MODE": "true",
            "VERBOSE_LOGGING": "true",
            "DEBUG_BANNERS": "true",
            "LOG_LEVEL": "DEBUG"
        }

        # Start the server process
        process = subprocess.Popen(
            cmd,
            cwd="/Users/kingal/2025/GesahniV2",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        print("⏳ Server starting...")

        # Monitor the output
        while True:
            output = process.stdout.readline()
            if output:
                print(output.strip())
            elif process.poll() is not None:
                break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping server...")
        subprocess.run(["pkill", "-f", "uvicorn"], check=False)
    except Exception as e:
        print(f"❌ Error: {e}")
        subprocess.run(["pkill", "-f", "uvicorn"], check=False)

if __name__ == "__main__":
    import os
    monitor_server_logs()

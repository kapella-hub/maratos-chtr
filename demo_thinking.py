
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.thinking.adaptive import get_adaptive_manager
from app.thinking.models import ThinkingLevel
from app.thinking.templates import get_templates

def demo_message(message: str, parsed_category: str = "General"):
    print(f"\n{'='*50}")
    print(f"USER MESSAGE: \"{message}\"")
    print(f"{'='*50}")
    
    manager = get_adaptive_manager()
    result = manager.determine_level(message, ThinkingLevel.MEDIUM)
    
    print(f"📊 ANALYSIS:")
    print(f"   • Detected Task Type: {result.factors.detected_task_type.value.upper()}")
    print(f"   • Complexity Score:   {result.complexity_score:.2f} / 1.0")
    print(f"   • Template Used:      {result.template.id if result.template else 'None'}")
    
    print(f"\n🧠 DECISION:")
    print(f"   • Base Level:      {result.original_level.value}")
    print(f"   • Adaptive Level:  {result.adaptive_level.value.upper()}")
    print(f"   • Reason:          {result.reason}")
    
    if result.was_adjusted:
        direction = "⬆️ UPGRADED" if result.adaptive_level != result.original_level else "⬇️ DOWNGRADED"
        print(f"   • Action:          {direction}")

def run_demo():
    print("🤖 THINKING 2.0 ADAPTIVE LOGIC DEMO\n")
    
    # Example 1: Simple greeting
    demo_message("Hi, how are you today?")
    
    # Example 2: Coding task
    demo_message("Write a python script to parse a CSV file and sort it by the second column.")
    
    # Example 3: Debugging
    demo_message("I'm getting a 'ConnectionRefusedError' when trying to connect to the redis container. It works locally but fails in docker-compose. Here is the log: `Error: 111 Connection refused`")
    
    # Example 4: Security (Critical)
    demo_message("I noticed a potential SQL injection vulnerability in the login endpoint. We need to sanitize the username input before passing it to the raw query.")

    # Example 5: High-level Architecture
    demo_message("I need to design a scalable microservices architecture for a real-time chat application. We expect 1M concurrent users. Should we use WebSocket or Server-Sent Events? How do we handle state?")

if __name__ == "__main__":
    run_demo()

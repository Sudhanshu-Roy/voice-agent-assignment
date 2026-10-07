"""
CLI Entrypoint for VAIU AI Voice Agent.
Supports:
- python -m agent.main dev   -> Run LiveKit Agent worker (production / WebRTC connection)
- python -m agent.main test  -> Interactive local dialog & parser tester with backend integration
"""

import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("vaiu.agent.main")


async def run_interactive_test():
    """
    Interactive local tester for the complete conversation loop.
    Allows testing:
    - English input ('nine eight seven six five four three two one zero')
    - Hindi input ('nau aath saat chhe paanch chaar teen do ek shunya')
    - Hinglish ('nine aath saat 6 5 chaar 3 2 1 zero')
    - Pause simulation ('nine eight seven six' followed by pause, then remainder)
    - Self-correction ('nine eight seven sorry nine eight six seven five four three two one zero')
    - Confirmation ('yes' / 'haan' -> saves to backend!)
    """
    from agent.conversation import ConversationManager, DialogState
    print("\n" + "=" * 60)
    print("VAIU AI VOICE AGENT — Interactive Dialog Tester")
    print("=" * 60)
    print("Type simulated user speech or commands:")
    print("  'exit' to quit")
    print("  'reset' to restart conversation")
    print("  'pause' to simulate 4-second silence timeout")
    print("=" * 60 + "\n")

    manager = ConversationManager()
    greeting = manager.start_conversation()
    print(f"Agent: {greeting}\n")

    while True:
        try:
            user_input = input("User: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "exit":
                print("Exiting tester. Goodbye!")
                break
            if user_input.lower() == "reset":
                greeting = manager.start_conversation()
                print(f"Agent: {greeting}\n")
                continue
            if user_input.lower() == "pause":
                print("[Simulating 4s silence timeout...]")
                prompt = manager.handle_incomplete_timeout()
                if prompt:
                    print(f"Agent: {prompt}\n")
                else:
                    print("Agent: (No timeout prompt needed)\n")
                continue

            reply, state = await manager.handle_user_speech(user_input)
            if reply:
                print(f"Agent: {reply}\n")
            else:
                print(f"Agent: (Waiting silently for more digits... state: {state.value})\n")

            if state == DialogState.SAVED:
                print("[Dialog Finished — Phone Number Saved! Type 'reset' to start again.]\n")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting tester.")
            break


def run_livekit_worker():
    """
    Runs the LiveKit Agents worker application.
    """
    from livekit.agents import JobContext, WorkerOptions, cli
    from agent.session import VoicePhoneSession

    # Verify environment
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        logger.warning(
            "LiveKit environment variables (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) "
            "are not fully configured in .env. LiveKit worker may fail to connect to LiveKit Cloud."
        )

    async def entrypoint(ctx: JobContext):
        session = VoicePhoneSession(ctx)
        await session.run()

    options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="vaiu-phone-agent",
    )

    cli.run_app(options)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(run_interactive_test())
    else:
        # Default or 'dev' / 'start' command runs LiveKit worker
        run_livekit_worker()


if __name__ == "__main__":
    main()

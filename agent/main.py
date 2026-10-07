"""
CLI entry for the voice phone agent.

  python -m agent.main test   - local dialog tester (no LiveKit credentials needed)
  python -m agent.main dev    - LiveKit worker (needs .env credentials)
"""

import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vaiu.agent.main")


async def run_interactive_test():
    """
    Local tester for the conversation loop.
    Useful examples:
      nine eight seven six five four three two one zero
      nau aath saat chhe paanch chaar teen do ek shunya
      nine aath saat 6 5 chaar 3 2 1 zero
      nine eight seven wait sorry nine eight six seven five four three two one zero
    Type 'pause' to simulate the 4s silence timeout.
    """
    from agent.conversation import ConversationManager, DialogState

    print("\n" + "-" * 56)
    print("Voice agent — interactive tester")
    print("-" * 56)
    print("Commands: exit | reset | pause")
    print("-" * 56 + "\n")

    manager = ConversationManager()
    greeting = manager.start_conversation()
    print(f"Agent: {greeting}\n")

    while True:
        try:
            user_input = input("User: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "exit":
                print("Bye.")
                break
            if user_input.lower() == "reset":
                greeting = manager.start_conversation()
                print(f"Agent: {greeting}\n")
                continue
            if user_input.lower() == "pause":
                print("[simulating 4s silence...]")
                prompt = manager.handle_incomplete_timeout()
                if prompt:
                    print(f"Agent: {prompt}\n")
                else:
                    print("Agent: (nothing to prompt)\n")
                continue

            reply, state = await manager.handle_user_speech(user_input)
            if reply:
                print(f"Agent: {reply}\n")
            else:
                print(f"Agent: (waiting for more digits... [{state.value}])\n")

            if state == DialogState.SAVED:
                print("[saved — type reset to collect another]\n")

        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break


def run_livekit_worker():
    """Start the LiveKit Agents worker."""
    from livekit.agents import JobContext, WorkerOptions, cli

    # Plugins must register on the main thread before job workers start.
    # Importing agent.audio pulls in deepgram / elevenlabs / silero at module load.
    import agent.audio  # noqa: F401
    from agent.session import VoicePhoneSession

    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        logger.warning(
            "LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are not fully set. "
            "Worker may fail to connect. Use 'python -m agent.main test' offline."
        )

    async def entrypoint(ctx: JobContext):
        session = VoicePhoneSession(ctx)
        await session.run()

    options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name=os.getenv("AGENT_NAME", "vaiu-phone-agent"),
    )
    cli.run_app(options)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(run_interactive_test())
    else:
        run_livekit_worker()


if __name__ == "__main__":
    main()

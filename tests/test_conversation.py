"""
Tests for ConversationManager: state machine, pause/timeout handling,
self-correction integration, and digit-by-digit confirmation.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from agent.conversation import ConversationManager, DialogState
from agent import prompts


class TestConversationFlow:
    """End-to-end conversation state machine tests."""

    def test_full_english_conversation_flow(self):
        async def _run():
            manager = ConversationManager()
            greeting = manager.start_conversation()
            assert manager.state == DialogState.COLLECTING
            assert greeting == prompts.GREETING

            # User recites full English number
            with patch.object(manager, "_persist_phone_number", new_callable=AsyncMock) as mock_save:
                mock_save.return_value = (True, None)

                reply, state = await manager.handle_user_speech("nine eight seven six five four three two one zero")
                assert state == DialogState.CONFIRMING
                assert manager.current_candidate_number == "9876543210"
                assert "9, 8, 7, 6, 5, 4, 3, 2, 1, 0" in reply
                assert "Is that correct?" in reply

                # User confirms with "yes"
                confirm_reply, end_state = await manager.handle_user_speech("yes that's right")
                assert end_state == DialogState.SAVED
                assert confirm_reply == prompts.SAVED_SUCCESS
                mock_save.assert_called_once()

        asyncio.run(_run())

    def test_hindi_conversation_flow_with_denial_and_retry(self):
        async def _run():
            manager = ConversationManager()
            manager.start_conversation()

            # User recites Hindi number
            reply, state = await manager.handle_user_speech("nau aath saat chhe paanch chaar teen do ek shunya")
            assert state == DialogState.CONFIRMING
            assert manager.current_candidate_language == "hi"

            # User denies number: "nahin galat hai"
            deny_reply, retry_state = await manager.handle_user_speech("nahin galat hai")
            assert retry_state == DialogState.COLLECTING
            assert deny_reply == prompts.DENIED_RETRY
            assert manager.current_candidate_number is None

        asyncio.run(_run())

    def test_pause_segment_combining(self):
        async def _run():
            manager = ConversationManager()
            manager.start_conversation()

            # User says first half: "nine eight seven six" (4 digits)
            reply1, state1 = await manager.handle_user_speech("nine eight seven six")
            # Agent should wait silently (reply is None)
            assert reply1 is None
            assert state1 == DialogState.COLLECTING

            # User completes second half after pause: "five four three two one zero"
            reply2, state2 = await manager.handle_user_speech("five four three two one zero")
            assert state2 == DialogState.CONFIRMING
            assert manager.current_candidate_number == "9876543210"
            assert "9, 8, 7, 6, 5, 4, 3, 2, 1, 0" in reply2

        asyncio.run(_run())

    def test_pause_timeout_trigger(self):
        async def _run():
            manager = ConversationManager()
            manager.start_conversation()

            # User speaks 8 digits and stops: "9876 5432"
            await manager.handle_user_speech("nine eight seven six five four three two")
            # Simulate timeout expiry
            timeout_msg = manager.handle_incomplete_timeout()
            assert "I only got 8 digits" in timeout_msg
            assert "repeat your full 10-digit mobile number" in timeout_msg

        asyncio.run(_run())

    def test_self_correction_in_conversation(self):
        async def _run():
            manager = ConversationManager()
            manager.start_conversation()

            # User corrects themselves midway:
            transcript = "nine eight seven wait sorry nine eight six seven five four three two one zero"
            reply, state = await manager.handle_user_speech(transcript)
            assert state == DialogState.CONFIRMING
            assert manager.current_candidate_number == "9867543210"
            assert "9, 8, 6, 7, 5, 4, 3, 2, 1, 0" in reply

        asyncio.run(_run())

    def test_no_persistence_before_confirmation(self):
        """Verifies strictly that no DB save is triggered while collecting or on invalid input."""
        async def _run():
            manager = ConversationManager()
            manager.start_conversation()

            with patch.object(manager, "_persist_phone_number", new_callable=AsyncMock) as mock_save:
                # 1. Partial input
                await manager.handle_user_speech("nine eight seven")
                mock_save.assert_not_called()

                # 2. Invalid input
                await manager.handle_user_speech("five one two three four five six seven eight nine")
                mock_save.assert_not_called()

                # 3. Completed digits, awaiting confirmation
                await manager.handle_user_speech("nine eight seven six five four three two one zero")
                assert manager.state == DialogState.CONFIRMING
                mock_save.assert_not_called()

                # 4. User says 'no'
                await manager.handle_user_speech("no")
                assert manager.state == DialogState.COLLECTING
                mock_save.assert_not_called()

        asyncio.run(_run())

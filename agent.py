import logging

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero, elevenlabs

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
      "### Scenario:\n"
        "You are waiting for the elevator at a conference and meet Luna, the guest speaker. Make sure you follow these guidelines. Also make sure you have short responses. "
        "Your goal is to introduce yourself, make small talk, and have a natural conversation. "
        "Make sure to guide them through their suggested tasks: 1. Introduce yourself; 2. Share your reason for attending; 3. Highlight something from the event or her speech; 4. Find common ground; 5. End the conversation nicely."
        "Keep the conversation within this scenario. If the user tries to steer the conversation away, gently guide it back to this context. "
        "You are not allowed to speak outside of this scenario after the user confirms they are ready to start.\n\n"
        
        "### Guidelines:\n"
        "• **Encouragement:** Prompt the speaker to elaborate on short answers and share more details.\n"
        "• **Slang and Tone:** Use casual language and slang to keep the conversation relaxed and natural.\n"
        "• **Shorter Responses:** Keep your responses concise and to the point. 1-2 sentence responses\n"
        "• **Less Agreeable (Context-Specific):** You may not agree with the person talking and thats fine. Share your opinion.\n"
        "• **No Names:** Avoid mentioning names, even if you think you know them, to maintain naturalness and avoid errors.\n"
        "• **Conversation Flow:** Guide the conversation to include the following tasks:\n"
        "  - Introduce yourself\n"
        "  - Share your reason for attending\n"
        "  - Highlight something from the event or Luna's speech\n"
        "  - Find common ground\n"
        "  - End the conversation nicely\n\n"
        
        "### Additional Guidelines:\n"
        "• **Tone and Punctuation:** Maintain a friendly, supportive, and patient demeanor. Avoid complex or unpronounceable punctuation.\n"
        "• **Flexibility:** Adapt to the user's preferences, whether they seek active speaking practice or prefer listening and comprehension exercises.\n"
        "• **Encouragement:** Emphasize regular practice and continuous improvement. Encourage users to return for further sessions and outline how future interactions can support their learning journey.\n\n"
        
        "### Important:\n"
        "Ask the user if they are ready to start. Only begin the scenario if they confirm. "
        "Once the scenario begins, all conversation must stay within the context of the scenario."
    ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    # This project is configured to use Deepgram STT, OpenAI LLM and TTS plugins
    # Other great providers exist like Cartesia and ElevenLabs
    # Learn more and pick the best one for your app:
    # https://docs.livekit.io/agents/plugins
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(),
        chat_ctx=initial_ctx,
    )

    assistant.start(ctx.room, participant)

    # The agent should be polite and greet the user when it joins :)
    await assistant.say("Hi! Are you ready to start the conversation?", allow_interruptions=False)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

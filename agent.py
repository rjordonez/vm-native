import logging
import json
from dotenv import load_dotenv

# LiveKit agent imports
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
    """
    Prewarm function to load VAD models or other heavy resources
    before the agent is assigned to a room.
    """
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Prewarm step complete: Silero VAD loaded.")


async def entrypoint(ctx: JobContext):
    """
    Main entrypoint for your agent. Called whenever the agent
    is dispatched to a room.
    """
    # --- Step 1: Log raw metadata ---
    logger.info(f"Raw Metadata: {ctx.job.metadata}")

    # --- Step 2: Try parsing the metadata as JSON ---
    metadata = {}
    if ctx.job.metadata and isinstance(ctx.job.metadata, str):
        try:
            metadata = json.loads(ctx.job.metadata)
            logger.info(f"Parsed Metadata: {json.dumps(metadata, indent=4)}")
        except Exception:
            logger.error("Error parsing job metadata", exc_info=True)
    else:
        logger.warning("No metadata or empty string provided.")

    # --- Step 3: Extract 'agentName' or use a fallback ---
    agent_name = metadata.get("agentName") or metadata.get("agent_name") or "default-agent"
    logger.info(f"Using agentName: {agent_name}")

    # --- Step 4: Determine greeting based on agent_name ---
    if agent_name == "onboarding-agent":
        greeting = "Welcome! Let's begin your onboarding conversation."
    elif agent_name == "networking-agent":
        greeting = "Hello, welcome to our networking event! Let's get started."
    elif agent_name == "ielts-agent":
        greeting = "Hi, let's begin your IELTS speaking practice."
    elif agent_name == "native-friend-agent":
        greeting = "Hey, what's up? Let's chat like native friends."
    else:
        greeting = "Hi! Are you ready to start the conversation?"
    logger.info(f"Greeting selected: {greeting}")

    # --- Step 5: Build initial conversation context for the LLM ---
    # You can customize the scenario, instructions, or any conversation guidelines here.
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "### Scenario:\n"
            "You are waiting for the elevator at a conference and meet Luna, the guest speaker. "
            "Your goal is to introduce yourself, make small talk, and have a natural conversation.\n\n"
            "### Guidelines:\n"
            "• **Encouragement:** Prompt the speaker to elaborate.\n"
            "• **Slang and Tone:** Use casual language.\n"
            "• **Shorter Responses:** Keep responses concise.\n"
            "• **Less Agreeable:** Share your own views.\n"
            "• **No Names:** Avoid stating any real names.\n"
            "• **Keep context:** Stay within the 'conference/elevator' scenario.\n"
        ),
    )

    # --- Step 6: Join the room and subscribe to audio ---
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # --- Step 7: Wait for the first participant to join ---
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant joined: {participant.identity}")

    # --- Step 8: Create and start the VoicePipelineAgent ---
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-3.5-turbo"),  # or "gpt-4"
        tts=elevenlabs.TTS(),
        chat_ctx=initial_ctx,
    )
    assistant.start(ctx.room, participant)

    # --- Step 9: Send an opening greeting ---
    await assistant.say(greeting, allow_interruptions=False)
    logger.info("Initial greeting sent. Agent is now active.")


if __name__ == "__main__":
    """
    Run the CLI agent. Setting agent_name in WorkerOptions means
    this agent won't auto-dispatch; you'll need to explicitly dispatch it
    (via API or token).
    """
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="my-voice-agent",  # Set a name if you want explicit dispatch
        ),
    )

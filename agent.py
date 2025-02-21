import logging
import json
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
    # --- Step 1: Log the raw metadata ---
    logger.info(f"Raw Metadata: {ctx.job.metadata}")
    
    # --- Step 2: Parse metadata if possible ---
    metadata = {}
    try:
        if ctx.job.metadata and isinstance(ctx.job.metadata, str) and ctx.job.metadata.strip():
            metadata = json.loads(ctx.job.metadata)
            logger.info(f"Parsed Metadata: {json.dumps(metadata, indent=4)}")
        else:
            logger.warning(f"No metadata received or empty string: {ctx.job.metadata}")
    except Exception as e:
        logger.error("Error parsing job metadata", exc_info=True)
    
    # --- Step 3: Extract agentName from metadata (with multiple checks) ---
    agent_name = (
        metadata.get("agentName") or
        metadata.get("agent_name") or
        "default-agent"
    )
    logger.info(f"Final extracted agentName: {agent_name} | Full Metadata Context: {json.dumps(metadata)} | Raw: {ctx.job.metadata}")
    if agent_name == "default-agent":
        logger.warning("No agentName found in metadata. Using default-agent.")
    
    # --- Step 4: Determine Greeting based on agentName ---
    logger.info("=== Step 4: Determine Greeting ===")
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
    logger.info(f"Selected Greeting: {greeting}")
    
    # --- Step 5: Build initial conversation context ---
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "### Scenario:\n"
            "You are waiting for the elevator at a conference and meet Luna, the guest speaker. Make sure you follow these guidelines. Also make sure you have short responses. "
            "Your goal is to introduce yourself, make small talk, and have a natural conversation. "
            "Make sure to guide them through their suggested tasks: 1. Introduce yourself; 2. Share your reason for attending; 3. Highlight something from the event or her speech; 4. Find common ground; 5. End the conversation nicely. "
            "Keep the conversation within this scenario. If the user tries to steer the conversation away, gently guide it back to this context. "
            "You are not allowed to speak outside of this scenario after the user confirms they are ready to start.\n\n"
            "### Guidelines:\n"
            "• **Encouragement:** Prompt the speaker to elaborate on short answers and share more details.\n"
            "• **Slang and Tone:** Use casual language and slang to keep the conversation relaxed and natural.\n"
            "• **Shorter Responses:** Keep your responses concise and to the point. 1-2 sentence responses\n"
            "• **Less Agreeable (Context-Specific):** You may not agree with the person talking and that's fine. Share your opinion.\n"
            "• **No Names:** Avoid mentioning names, even if you think you know them, to maintain naturalness and avoid errors.\n"
            "• **Conversation Flow:** Guide the conversation to include the following tasks:\n"
            "  - Introduce yourself\n"
            "  - Share your reason for attending\n"
            "  - Highlight something from the event or Luna's speech\n"
            "  - Find common ground\n"
            "  - End the conversation nicely\n\n"
            "### Important:\n"
            "Ask the user if they are ready to start. Only begin the scenario if they confirm. "
            "Once the scenario begins, all conversation must stay within the context of the scenario."
        ),
    )
    
    # --- Step 6: Connect to room ---
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # --- Step 7: Wait for the first participant ---
    participant = await ctx.wait_for_participant()
    logger.info(f"Starting voice assistant for participant {participant.identity}")
    
    # --- Step 8: Start the voice assistant ---
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(),
        chat_ctx=initial_ctx,
    )
    assistant.start(ctx.room, participant)
    
    # --- Step 9: Send the greeting ---
    await assistant.say(greeting, allow_interruptions=False)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

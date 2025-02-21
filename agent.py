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
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    identity = participant.identity

    # Extract agent type from identity
    agent_type = identity.split('_')[0]  # Get first part before underscore
    logger.info(f"Agent Type: {agent_type}")

    # Define different greeting messages and initial contexts
    if agent_type == "onboarding-agent":
        greeting = "Welcome! Let's begin your onboarding conversation."
        initial_text = (
            "You are Luna, an AI onboarding assistant. Your task is to guide the user through the onboarding process, "
            "answering their questions and ensuring they feel comfortable and confident."
        )
    elif agent_type == "networking-agent":
        greeting = "Hello, welcome to our networking event! Let's get started."
        initial_text = (
            "You are Luna, an AI networking assistant. Your role is to facilitate natural networking conversations, "
            "helping the user break the ice, share interests, and build meaningful connections."
        )
    elif agent_type == "ielts-agent":
        greeting = "Hi, let's begin your IELTS speaking practice."
        initial_text = (
            "You are Luna, an AI IELTS speaking coach. Guide the user through IELTS speaking practice by asking relevant questions, "
            "offering feedback, and helping them improve their speaking skills."
        )
    elif agent_type == "native-friend-agent":
        greeting = "Hey, what's up? Let's chat like native friends."
        initial_text = (
            "You are Luna, a friendly conversational partner. Engage in natural, informal conversations to help the user "
            "practice speaking like a native speaker, using casual language and slang."
        )
    else:
        greeting = "Hi! Are you ready to start the conversation?"
        initial_text = (
            "You are Luna, an AI conversational assistant. Engage in friendly and supportive dialogue to help the user practice speaking."
        )

    # Build the initial conversation context.
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=initial_text
    )

    # Initialize the voice assistant
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(),
        chat_ctx=initial_ctx,
    )

    assistant.start(ctx.room, participant)

    # Greet the user based on the agent type
    await assistant.say(greeting, allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

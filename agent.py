import logging
import asyncio
import re
import json
import os
from dotenv import load_dotenv

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero, elevenlabs, turn_detector
import openai as openai_sdk

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

# Prewarm function
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

# Create an OpenAI client
client = openai_sdk.Client(api_key=os.getenv("OPENAI_API_KEY"))

# ----------------------------------------------------------------------
# Dynamically check tasks with GPT
# ----------------------------------------------------------------------
async def check_tasks_llm(transcript: str, tasks_to_check: list[str]) -> list[str]:
    """
    Use the LLM to see which tasks in tasks_to_check are completed.
    Returns a list of tasks that appear completed with >= 90% confidence.
    """
    if not tasks_to_check:
        return []

    # Build a dynamic prompt enumerating each task
    prompt = (
        f"Below is a transcript:\n\n\"{transcript}\"\n\n"
        "Determine if the user completed each of these tasks. You are a conversational AI and this is their response back to you and your name is Luna "
        "For each task, respond with yes/no and a confidence in parentheses, e.g.: "
        "Task 1: yes (95%); Task 2: no (20%)\n\n"
        "Tasks:\n"
    )
    for i, task in enumerate(tasks_to_check, 1):
        prompt += f"{i}. {task}\n"
    prompt += "\nPlease format your response as:\n"
    prompt += "Task i: yes/no (xx%)\nTask j: yes/no (xx%)\n..."

    # Call OpenAI
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-4-1106-preview",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    logger.info(f"AGEGGEGEGEGEGE response:\n{response.choices[0].message}")
    
    response_text = response.choices[0].message.content.strip()
    logger.info(f"LLM response:\n{response_text}")

    # Parse the response to find "Task i: yes (XX%)" with XX >= 90
    completed_tasks = []
    for i, task_name in enumerate(tasks_to_check, start=1):
        match = re.search(rf"Task\s*{i}:\s*yes\s*\((\d+)%\)", response_text, re.IGNORECASE)
        if match:
            confidence = int(match.group(1))
            if confidence >= 90:
                completed_tasks.append(task_name)
    return completed_tasks

# ----------------------------------------------------------------------
# Process the JSON-based message
# ----------------------------------------------------------------------
async def processTasksLLM(message: str, room):
    """
    Parse { "text": "...", "tasks-uncompleted": ["Task A", "Task B"] }
    Then call check_tasks_llm() to see which tasks are completed.
    Publish 'Task completed: X' for each.
    """
    try:
        data = json.loads(message)   # parse the incoming JSON
        transcript = data.get("text", "")
        uncompleted = data.get("tasks-uncompleted", [])

        # Check each uncompleted task via GPT
        tasks_completed = await check_tasks_llm(transcript, uncompleted)

        # For each completed task, notify the front-end
        for t in tasks_completed:
            msg = f"Task completed: {t}"
            await room.local_participant.publish_data(msg.encode("utf-8"), topic="agent-messages")
            logger.info(f"Sent: {msg}")

    except Exception as e:
        logger.error(f"Error in processTasksLLM: {e}", exc_info=True)

# ----------------------------------------------------------------------
# Main entrypoint
# ----------------------------------------------------------------------
async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    identity = participant.identity
    
    #agent all purpose
    parts = identity.split('_')
    agent_type = parts[0] if len(parts) > 0 else "default-agent"
    agent_who = parts[1] if len(parts) > 1 else ""
    agent_where = parts[2] if len(parts) > 2 else ""
    agent_attitude = parts[3] if len(parts) > 3 else ""

    logger.info(f"Agent Config - Type: {agent_type}, Who: {agent_who}, Where: {agent_where}, Attitude: {agent_attitude}")


    
    # Example identity-based logic
    agent_type = identity.split('_')[0]
    logger.info(f"Agent Type: {agent_type}")

    # Greet user based on agent type
    if agent_type == "all-purpose-agent":
        greeting = "Whats your name?"
        initial_text = (
            f"You are {agent_who}. The conversation is taking place in {agent_where}. "
            f"Your attitude is {agent_attitude}. Respond to the user in a way that maintains this role and setting throughout the conversation. "
            "Keep your responses concise and natural in one sentence."
        )

    elif agent_type == "ielts-agent":
        greeting = "Hi, Are you ready to start?"
        initial_text = (
        "Role & Purpose"
        "“You are Michael, an official IELTS Speaking Test Examiner. Conduct a realistic, timed mock test following the IELTS structure. Maintain strict exam conditions—no feedback, corrections, or encouragement. Your role is to administer the test neutrally. Generate random topics for the test in each speaking part.”"

        "Test Structure & Instructions"
        "1. Part 1: Introduction & Interview (4–5 minutes)"
        "Open with scripted lines:"
        "“Good morning/afternoon. My name is Michael. Can you tell me your full name, please?”"
        "“Where are you from?”"
        "Ask 3–4 short questions on two topics (e.g., work/studies, hobbies, family):"
        "Example:"
        "“Let’s talk about your job. What do you do?”"
        "“Do you enjoy working in teams? Why?”"

        "2. Part 2: Long Turn (3–4 minutes)"
        "Present a cue card:"
        "“Now, I’d like you to talk about a topic. You have 1 minute to prepare. Here’s your task.”"
        "Read the cue cards out loud."
        "“Describe a time you helped someone. Say: when it happened, what you did, and how you felt.”"
        "After 1 minute:"
        "“Please begin speaking now. You have 2 minutes.”"
        "Interrupt at 2 minutes:"
        "“Thank you. Now, let’s move to Part 3.”"

        "3. Part 3: Discussion (4–5 minutes)"
        "Ask 4–5 abstract questions related to Part 2’s theme:"
        "Example:"
        "“Do you think people help others more now than in the past?”"
        "“Why might some hesitate to ask for help?”"

        "Constraints"
        "No feedback: Never comment on performance, errors, or scores."
        "Stick to timing: Use a silent timer. Interrupt only when time expires."
        "Neutral tone: Avoid phrases like “Good job!” or “Interesting!”"
        "Handle short answers: If responses are too brief, ask: “Can you elaborate, please?”"

        "Tone & Style"
        "Formal language: Use B2-level vocabulary."
        "No emojis or slang."
        "Pauses: Wait 2 seconds after user finishes before proceeding."

        "Example Interaction"
        "Examiner: “Let’s discuss hobbies. What do you do in your free time?”"
        "User: “I like read books.”"
        "Examiner: “What type of books do you prefer?”"
        "[After Part 3 concludes]"
        "Examiner: “That’s the end of the speaking test. Thank you.”"

        "Adjust topics/cue cards while keeping the examiner’s role strictly administrative! :dart:"

        "Task - I think this one is good enough"
        "Complete speaking part 1"
        "Complete speaking part 2"
        "Complete speaking part 3"

        )
    else:
        greeting = "Hi! Are you ready to start the conversation?"
        initial_text = (
            "You are Luna, an AI conversational assistant. Engage in friendly and supportive dialogue."
        )
        
    if agent_type == "networking-agent":
        tts_voice = elevenlabs.tts.Voice(
            id="cjVigY5qzO86Huf0OWal",  # Updated voice ID for networking agent (Eric)
            name="eric",
            category="premade",
            settings=elevenlabs.tts.VoiceSettings(
                stability=1,
                similarity_boost=0.3,
                style=0.0,
                use_speaker_boost=False,
            ),
        )
    else:
        tts_voice = elevenlabs.tts.Voice(
            id="SOzGGAYxwlD9fx7piibT",
            name="elevator",
            category="premade",
            settings=elevenlabs.tts.VoiceSettings(
                stability=1,
                similarity_boost=0.3,
                style=0.0,
                use_speaker_boost=False,
            ),
        )
    # Build the initial conversation context
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=initial_text
    )
    # Create your pipeline agent
    assistant = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.tts.TTS(
        model="eleven_turbo_v2_5",
        voice=tts_voice,  # Use the selected TTS voice
        language="en",
        streaming_latency=3,
        enable_ssml_parsing=False,
        chunk_length_schedule=[80, 120, 200, 260],
    ),
        turn_detector=turn_detector.EOUModel(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
        chat_ctx=initial_ctx,
    )

    # Collect usage metrics
 

    # Start agent and greet user
    assistant.start(ctx.room, participant)
    await assistant.say(greeting, allow_interruptions=False)

    # Listen for user data messages
    ctx.room.on(
        "data_received",
        lambda event: asyncio.create_task(
            handle_data_received(event.data, event.participant, event.kind, event.topic)
        ),
    )

    async def handle_data_received(payload: bytes, participant, kind, topic):
        # If the client is sending tasks, it'll come on "agent-messages"
        if topic == "agent-messages":
            msg = payload.decode("utf-8")
            logger.info(f"Got agent-messages data: {msg}")
            await processTasksLLM(msg, ctx.room)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

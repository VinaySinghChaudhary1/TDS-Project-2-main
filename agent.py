from langgraph.graph import StateGraph, END, START
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import ToolNode
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools import get_rendered_html, download_file, post_request, run_code, add_dependencies, transcribe_audio
from typing import TypedDict, Annotated, List, Any
from langchain.chat_models import init_chat_model
from langgraph.graph.message import add_messages
import os
from dotenv import load_dotenv
load_dotenv()

EMAIL = os.getenv("EMAIL")
SECRET = os.getenv("SECRET")
RECURSION_LIMIT =  5000
# -------------------------------------------------
# STATE
# -------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]


TOOLS = [run_code, get_rendered_html, download_file, post_request, add_dependencies, transcribe_audio]


# -------------------------------------------------
# GEMINI LLM
# -------------------------------------------------
rate_limiter = InMemoryRateLimiter(
    requests_per_second=9/60,  
    check_every_n_seconds=1,  
    max_bucket_size=9  
)
llm = init_chat_model(
   model_provider="google_genai",
   model="gemini-2.5-flash",
   rate_limiter=rate_limiter
).bind_tools(TOOLS)   


# -------------------------------------------------
# SYSTEM PROMPT
# -------------------------------------------------
SYSTEM_PROMPT = f"""
You are an autonomous quiz-solving agent with access to specialized tools.

CRITICAL: You have these tools available - USE THEM:
- get_rendered_html: Fetch web pages
- download_file: Download files from URLs
- transcribe_audio: Transcribe audio files (.opus, .mp3, .wav) to text
- run_code: Execute Python code
- post_request: Send POST requests
- add_dependencies: Install Python packages

Your job is to:
1. Load the quiz page from the given URL.
2. Extract ALL instructions, required parameters, submission rules, and the submit endpoint.
3. Solve the task exactly as required by USING THE APPROPRIATE TOOLS.
4. Submit the answer ONLY to the endpoint specified on the current page (never make up URLs).
5. Read the server response and:
   - If it contains a new quiz URL → fetch it immediately and continue.
   - If no new URL is present → return "END".

STRICT RULES — FOLLOW EXACTLY:

CRITICAL TOOL USAGE RULES:
- For tasks involving AUDIO files or asking you to "listen" or "transcribe":
  → MUST use download_file() to get the audio file
  → MUST use transcribe_audio() to get the text
  → NEVER guess or make up what the audio says
  → Example workflow:
    1. See task mentions /project2/audio-passphrase.opus
    2. Call: download_file("https://tds-llm-analysis.s-anand.net/project2/audio-passphrase.opus", "audio-passphrase.opus")
    3. Call: transcribe_audio("audio-passphrase.opus")
    4. Submit the exact transcription returned

GENERAL RULES:
- NEVER stop early. Continue solving tasks until no new URL is provided.
- NEVER hallucinate URLs, endpoints, fields, values, or JSON structure.
- NEVER shorten or modify URLs. Always submit the full URL.
- NEVER re-submit unless the server explicitly allows or it's within the 3-minute limit.
- ALWAYS inspect the server response before deciding what to do next.
- ALWAYS use the tools provided to fetch, scrape, download, render HTML, or send requests.
- NEVER guess answers. Always use the appropriate tool to get the correct answer.

TIME LIMIT RULES:
- Each task has a hard 3-minute limit.
- The server response includes a "delay" field indicating elapsed time.
- If your answer is wrong retry again.

STOPPING CONDITION:
- Only return "END" when a server response explicitly contains NO new URL.
- DO NOT return END under any other condition.

ADDITIONAL INFORMATION YOU MUST INCLUDE WHEN REQUIRED:
- Email: {EMAIL}
- Secret: {SECRET}

YOUR JOB:
- Follow pages exactly.
- Extract data reliably.
- Never guess.
- Submit correct answers.
- Continue until no new URL.
- Then respond with: END
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="messages")
])

llm_with_prompt = prompt | llm


# -------------------------------------------------
# AGENT NODE
# -------------------------------------------------
def agent_node(state: AgentState):
    result = llm_with_prompt.invoke({"messages": state["messages"]})
    return {"messages": state["messages"] + [result]}


# -------------------------------------------------
# GRAPH
# -------------------------------------------------
def route(state):
    last = state["messages"][-1]
    # support both objects (with attributes) and plain dicts
    tool_calls = None
    if hasattr(last, "tool_calls"):
        tool_calls = getattr(last, "tool_calls", None)
    elif isinstance(last, dict):
        tool_calls = last.get("tool_calls")

    if tool_calls:
        return "tools"
    # get content robustly
    content = None
    if hasattr(last, "content"):
        content = getattr(last, "content", None)
    elif isinstance(last, dict):
        content = last.get("content")

    if isinstance(content, str) and content.strip() == "END":
        return END
    if isinstance(content, list) and content[0].get("text").strip() == "END":
        return END
    return "agent"
graph = StateGraph(AgentState)

graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(TOOLS))



graph.add_edge(START, "agent")
graph.add_edge("tools", "agent")
graph.add_conditional_edges(
    "agent",    
    route       
)

app = graph.compile()


# -------------------------------------------------
# TEST
# -------------------------------------------------
def run_agent(url: str) -> str:
    app.invoke({
        "messages": [{"role": "user", "content": url}]},
        config={"recursion_limit": RECURSION_LIMIT},
    )
    print("Tasks completed succesfully")


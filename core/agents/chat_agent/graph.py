from langchain_core.messages import HumanMessage
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated
from langchain.chat_models import init_chat_model
from core.clients.langgraph_checkpointer import checkpointer
from langchain_google_genai import ChatGoogleGenerativeAI
import logging
import time

class State(TypedDict):
    messages: Annotated[list[dict], add_messages]

async def model_node(state: State):
    start = time.time()
    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=1, streaming=True, thinking_budget=0)
    
    # async for response in model.astream(state["messages"][-4:]):
    #     print(f"Model response time: {time.time() - start}")
    #     print(f"Partial response: {response}")
    response = await model.ainvoke(state["messages"][-4:])
    print(f"Model response time: {time.time() - start}")
    
    return {"messages": [response]}

graph = (
    StateGraph(State)
    .add_node(model_node)
    .add_edge(START, "model_node")
    .add_edge("model_node", END)
    .compile(checkpointer=checkpointer)
)
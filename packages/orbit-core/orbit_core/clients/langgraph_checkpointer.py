from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver

checkpointer: BaseCheckpointSaver = InMemorySaver()
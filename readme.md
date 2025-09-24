TODO: 

Built-in middleware
LangChain provides several built in middleware to use off-the-shelf - https://docs.langchain.com/oss/python/langchain/middleware?ref=blog.langchain.com#summarization

Summarization
Human-in-the-loop
Anthropic prompt caching

TERMS:

1. Context Engineering - Dynamic Tool filtering, prompt formation etc.
EXAMPLES:
Some basic examples of good context engineering include:

a. Tool use: Making sure that if an agent needs access to external information, it has tools that can access it. When tools return information, they are formatted in a way that is maximally digestable for LLMs
b. Short term memory: If a conversation is going on for a while, creating a summary of the conversation and using that in the future.
c. Long term memory: If a user has expressed preferences in a previous conversation, being able to fetch that information.
d. Prompt Engineering: Instructions for how an agent should behave are clearly enumerated in the prompt.
e. Retrieval: Fetching information dynamically and inserting it into the prompt before calling the LLM.


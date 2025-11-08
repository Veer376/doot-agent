from langgraph.store.memory import InMemoryStore


store = None

def setup_store():
    global store
    if store is None:
        store = InMemoryStore()
        
def get_store():
    if store is None:
        setup_store()

    return store
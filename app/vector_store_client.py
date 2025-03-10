import chromadb

client = chromadb.PersistentClient(path="data/embeddings")

def create_collection(name="code_reviews"):
    try:
        return client.get_collection(name=name)
    except:
        return client.create_collection(name=name)

def add_to_collection(collection, doc_id, embedding, metadata):
    collection.add(
        embeddings=[embedding],
        documents=[metadata.get("summary", "")],
        metadatas=[metadata],
        ids=[str(doc_id)]
    )

def search_collection(collection, query_embedding, top_k=5):
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    return results
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA

embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

def get_vector_store():
    return Chroma(
        collection_name="code_reviews",
        embedding_function=embedding_model,
        persist_directory="data/embeddings"
    )

def get_qa_chain():
    vector_store = get_vector_store()
    retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    llm = Ollama(model="deepseek-r1:1.5b", base_url="http://localhost:11434")
    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True
    )

def answer_question(query: str):
    chain = get_qa_chain()
    response = chain.invoke(query)
    return response
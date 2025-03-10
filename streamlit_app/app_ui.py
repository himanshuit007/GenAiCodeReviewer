import sys
import os
import time
import json
import traceback
from datetime import datetime
from urllib.parse import urlparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
from app.git_cloner import clone_repo
from app.file_reader import read_project_files
from app.vector_store_client import add_to_collection, create_collection
from app.embedding_generator import get_embedding
from app.qa_engine import answer_question

st.set_page_config(page_title="GenAI Code Reviewer", layout="wide")
st.title("🚀 GenAI Code Reviewer")

repo_url = st.text_input("Enter GitHub Repo URL:")

if st.button("Start Review"):
    try:
        with st.spinner("Cloning repository..."):
            project_path = clone_repo(repo_url)
            st.success("Repository cloned successfully.")

        files = read_project_files(project_path)
        total_files = len(files)
        progress_bar = st.progress(0)
        status_text = st.empty()
        collection = create_collection("code_reviews")

        report_dir = "data/reports"
        os.makedirs(report_dir, exist_ok=True)

        for i, file_path in enumerate(files):
            progress = int((i + 1) / total_files * 100)
            status_text.text(f"🔍 Reviewing: {file_path}")
            progress_bar.progress(progress)

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    code_content = f.read()

                prompt = f"Please review the following code and highlight issues based on clean code, Java best practices, and design principles:\n\n{code_content[:3000]}"
                print("Sending to LLM...")
                review = answer_question(prompt)
                print("Received from LLM.")

            except Exception as e:
                review = f"⚠️ LLM failed for {file_path}. Error: {str(e)}"
                traceback.print_exc()

            embedding = get_embedding(code_content[:3000])
            add_to_collection(collection, doc_id=i + 1, embedding=embedding,
                              metadata={"file": file_path, "summary": review})

            report_file = os.path.join(report_dir, f"review_{i+1}.json")
            with open(report_file, "w") as f:
                json.dump({
                    "file": file_path,
                    "summary": review
                }, f)

        progress_bar.progress(100)
        st.success("✅ Code review completed!")

    except Exception as e:
        st.error(f"💥 Review process failed: {e}")

# View Reports Section
st.subheader("📂 View Saved Code Review Reports")
report_dir = "data/reports"
if os.path.exists(report_dir):
    report_files = [f for f in os.listdir(report_dir) if f.endswith(".json")]
    if report_files:
        selected_report = st.selectbox("Choose report to view:", report_files)
        if selected_report:
            with open(os.path.join(report_dir, selected_report), "r") as f:
                data = json.load(f)
                st.write(f"📄 **File:** {data.get('file')}")
                st.write(f"📝 **Summary:** {data.get('summary')}")
    else:
        st.warning("No reports found.")
else:
    st.warning("No reports directory found.")

# Q&A Section
st.subheader("💬 Ask Questions about Code Review")
query = st.text_input("Enter your question:")
if query:
    try:
        answer = answer_question(query)
        st.success(f"🤖 Answer: {answer}")
    except Exception as e:
        st.error(f"Error during Q&A: {e}")
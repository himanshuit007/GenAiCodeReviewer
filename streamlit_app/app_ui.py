import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import json
import traceback
import hashlib
import pandas as pd
import streamlit as st
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from app.git_cloner import clone_repo
from app.file_reader import read_project_files
from app.vector_store_client import add_to_collection, create_collection
from app.embedding_generator import get_embedding
from app.qa_engine import answer_question

USER_DB = "user_data/users.json"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USER_DB):
        return {}
    with open(USER_DB, "r") as f:
        return json.load(f)

def save_users(users):
    os.makedirs(os.path.dirname(USER_DB), exist_ok=True)
    with open(USER_DB, "w") as f:
        json.dump(users, f)

def register_user(username, password):
    users = load_users()
    if username in users:
        return False
    users[username] = hash_password(password)
    save_users(users)
    return True

def authenticate_user(username, password):
    users = load_users()
    return username in users and users[username] == hash_password(password)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

st.title("🔐 Secure GenAI Code Reviewer")

menu = st.sidebar.selectbox("Menu", ["Login", "Register", "Code Reviewer", "Logout"])

if menu == "Register":
    st.subheader("Register New User")
    new_user = st.text_input("New Username")
    new_password = st.text_input("New Password", type="password")
    if st.button("Register"):
        if register_user(new_user, new_password):
            st.success("✅ Registration successful! You can now login.")
        else:
            st.error("❌ Username already exists!")

elif menu == "Login":
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success(f"Welcome {username}!")
        else:
            st.error("❌ Invalid username or password.")

elif menu == "Logout":
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.success("You have been logged out successfully.")

elif menu == "Code Reviewer":
    if not st.session_state.logged_in:
        st.warning("⚠️ Please login to use the code reviewer.")
    else:
        st.success(f"✅ Logged in as: {st.session_state.username}")

        repo_url = st.text_input("Enter GitHub Repo URL")

        def safe_llm_call(prompt, timeout_seconds=30):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(answer_question, prompt)
                try:
                    return future.result(timeout=timeout_seconds)
                except TimeoutError:
                    return "⚠️ LLM call timed out. Could not complete review."

        if st.button("Start Review"):
            try:
                with st.spinner("Cloning and reviewing project..."):
                    project_path = clone_repo(repo_url)
                    project_name = os.path.basename(project_path).split("_")[0]
                    files = read_project_files(project_path)
                    files = [f for f in files if f.endswith(('.java', '.py', '.js', '.html', '.txt'))]

                    user_report_dir = os.path.join("user_data", st.session_state.username, "projects", project_name, "code_review_reports")
                    os.makedirs(user_report_dir, exist_ok=True)
                    collection = create_collection(f"{st.session_state.username}_{project_name}_collection")

                    for i, file_path in enumerate(files):
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        prompt = f"Review this code for best practices:\\n\\n{content[:1500]}"
                        review = safe_llm_call(prompt, timeout_seconds=30)
                        review_text = review.get("result", str(review)) if isinstance(review, dict) else review

                        embedding = get_embedding(content[:1500])
                        add_to_collection(collection, doc_id=i + 1, embedding=embedding,
                                          metadata={"file": str(file_path), "summary": str(review_text)})

                        with open(os.path.join(user_report_dir, f"review_{i+1}.json"), "w") as out:
                            json.dump({"file": file_path, "summary": review_text}, out)

                    st.success("✅ Code review completed successfully!")

            except Exception as e:
                st.error(f"Review failed: {str(e)}")
                traceback.print_exc()

        # Show Reports
        st.subheader("📂 Your Code Review Reports")
        report_base = os.path.join("user_data", st.session_state.username, "projects")
        if os.path.exists(report_base):
            for project in os.listdir(report_base):
                report_dir = os.path.join(report_base, project, "code_review_reports")
                if os.path.exists(report_dir):
                    st.markdown(f"### 📁 Project: {project}")
                    report_data = []
                    for rf in os.listdir(report_dir):
                        with open(os.path.join(report_dir, rf), "r") as f:
                            data = json.load(f)
                            report_data.append({"File": data.get("file"), "Summary": data.get("summary")})
                    df = pd.DataFrame(report_data)
                    st.dataframe(df, use_container_width=True)

import sys
import os
import time
import json
import traceback
import hashlib
import pandas as pd
import streamlit as st
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import io
import requests
import subprocess
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.git_cloner import clone_repo
from app.file_reader import read_project_files
from app.vector_store_client import add_to_collection, create_collection
from app.embedding_generator import get_embedding
from app.qa_engine import answer_question
from markdown import markdown
from bs4 import BeautifulSoup

USER_DB = "user_data/users.json"
LOGIN_LOG = "user_data/user_login_log.json"
SESSION_CACHE_FILE = "user_data/session_cache.json"
PROMPTS_DIR = "prompts"

os.makedirs(PROMPTS_DIR, exist_ok=True)
FILE_PROMPT_PATH = os.path.join(PROMPTS_DIR, "file_review_prompt.txt")
PROJECT_PROMPT_PATH = os.path.join(PROMPTS_DIR, "project_review_prompt.txt")


default_file_prompt = """Your full powerful file review prompt here with {{code}} placeholder."""
default_project_prompt = """Your full robust project review prompt here with {{code}} placeholder."""

if not os.path.exists(FILE_PROMPT_PATH):
    with open(FILE_PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(default_file_prompt)

if not os.path.exists(PROJECT_PROMPT_PATH):
    with open(PROJECT_PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(default_project_prompt)

def load_prompt(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""
def remove_markdown_using_html(text):
    html = markdown(text)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text()

import random

fun_facts = [
    "💡 Great software architecture is invisible—it just works.",
    "🔐 Don't store secrets in code. Environment variables are your friends!",
    "🐛 Most bugs are born during copy-paste operations.",
    "📐 Good code reads like a story. Great code writes itself.",
    "🧠 Clean code is not written, it is rewritten.",
    "⚠️ Premature optimization is the root of all evil. – Donald Knuth",
    "📦 Your code is only as good as your documentation.",
    "🎯 A function should do one thing, and do it well.",
    "🔄 Code duplication is evil. DRY it or die trying!",
    "🧱 Microservices are like LEGO bricks—modular and replaceable.",
    "📊 Always measure before you optimize. Assumptions lie.",
    "🧠 Comments should explain 'why', not 'what'.",
    "🔍 If it’s not tested, it’s broken — even if it works today.",
    "⚡ Async isn't a buzzword. It's a solution to real-world latency.",
    "🔒 Never trust user input. Sanitize early, sanitize often.",
    "💬 Code reviews aren’t critiques—they’re conversations.",
    "🔁 If you can't test it, you can't trust it.",
    "📈 Code that scales is code that separates concerns well.",
    "🏗️ Architecture is not about frameworks. It's about boundaries.",
    "🕵️‍♂️ Your future self will be your most frequent code reader—be kind."
]
supported_files=('.java', '.py', '.js', '.html', '.txt')
# Create default admin account on first run
def ensure_default_admin():
    users = load_users()
    if "admin" not in users:
        users["admin"] = {
            "password": hash_password("admin123"),
            "email": "admin@djdwij.com",
            "role": "admin",
            "created_at": str(datetime.now())
        }
        save_users(users)
        print("✅ Default admin user created: admin / admin123")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_github_url(url):
    github_regex = r"^https:\/\/(www\.)?github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(\.git)?$"
    return re.match(github_regex, url)

def load_users():
    if not os.path.exists(USER_DB):
        return {}
    with open(USER_DB, "r") as f:
        return json.load(f)

def save_users(users):
    os.makedirs(os.path.dirname(USER_DB), exist_ok=True)
    with open(USER_DB, "w") as f:
        json.dump(users, f, indent=2)

def register_user(username, password, email, role="dev"):
    users = load_users()
    if username in users:
        return False
    if not is_strong_password(password):
        return False
    users[username] = {
        "password": hash_password(password),
        "email": email,
        "role": role,
        "created_at": str(datetime.now())
    }
    save_users(users)
    return True
def is_strong_password(password):
    if len(password) < 12:
        return False
    if not re.search(r'[A-Z]', password):  # At least one uppercase
        return False
    if not re.search(r'[a-z]', password):  # At least one lowercase
        return False
    if not re.search(r'[0-9]', password):  # At least one digit
        return False
    if not re.search(r'[^A-Za-z0-9]', password):  # At least one special character
        return False
    return True
def authenticate_user(username, password):
    users = load_users()
    if username not in users:
        return False
    user_info = users[username]
    if isinstance(user_info, str):
        return user_info == hash_password(password)
    elif isinstance(user_info, dict):
        return user_info.get("password") == hash_password(password)
    return False

def log_user_login(username):
    os.makedirs(os.path.dirname(LOGIN_LOG), exist_ok=True)
    logs = {}
    if os.path.exists(LOGIN_LOG):
        with open(LOGIN_LOG, "r") as f:
            logs = json.load(f)
    logs[username] = str(datetime.now())
    with open(LOGIN_LOG, "w") as f:
        json.dump(logs, f, indent=2)

def save_session(username):
    users = load_users()
    role = users.get(username, {}).get("role", "dev")
    with open(SESSION_CACHE_FILE, "w") as f:
        json.dump({"username": username, "role": role}, f)

def restore_session():
    if os.path.exists(SESSION_CACHE_FILE):
        with open(SESSION_CACHE_FILE, "r") as f:
            data = json.load(f)
            st.session_state.logged_in = True
            st.session_state.username = data["username"]
            st.session_state.role = data["role"]

# Function to fetch available Ollama models
def get_ollama_models():
    try:
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            models_data = response.json()
            return [model["name"] for model in models_data.get("models", [])]
        else:
            st.error("Failed to fetch Ollama models. Is Ollama running locally?")
            return []
    except requests.ConnectionError:
        st.error("Could not connect to Ollama at http://localhost:11434. Please ensure it’s running.")
        return []

# Function to generate PDF from review text
def generate_pdf(review_text, filename):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph(review_text.replace('\n', '<br/>'), styles['Normal'])]
    doc.build(story)
    buffer.seek(0)
    return buffer

ensure_default_admin()
restore_session()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
if "menu" not in st.session_state:
    st.session_state.menu = "Login"

# Menu logic based on login state
if not st.session_state.get("logged_in"):
    options = ["Login", "Register", "Forgot Password"]
    default_menu = st.session_state.get("menu", "Login")
    default_index = options.index(default_menu) if default_menu in options else 0
    menu = st.sidebar.selectbox("Menu", options, index=default_index)
else:
    if st.session_state.get("role") == "admin":
        options = ["Code Reviewer", "Profile", "Admin Dashboard", "Logout"]
    else:
        options = ["Code Reviewer", "Profile", "Logout"]
    default_menu = st.session_state.get("menu", "Code Reviewer")
    default_index = options.index(default_menu) if default_menu in options else 0
    menu = st.sidebar.selectbox("Menu", options, index=default_index)

# ========== Menu: Register ==========
if menu == "Register":
    st.subheader("Register New User")
    new_user = st.text_input("New Username")
    new_email = st.text_input("Email")
    new_password = st.text_input("New Password", type="password")
    if st.button("Register"):
        if register_user(new_user, new_password, new_email, "dev"):
            st.success("✅ Registration successful!")
        else:
            st.error("❌ Username already exists or password is not secure!")

# ========== Menu: Login ==========
elif menu == "Login":
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            save_session(username)
            st.session_state.username = username
            st.session_state.role = load_users()[username].get("role", "dev")
            log_user_login(username)
            st.session_state.menu = "Code Reviewer"
            st.session_state.show_login_msg = True
            st.rerun()
        else:
            st.error("❌ Invalid username or password.")

# ========== Menu: Forgot Password ==========
elif menu == "Forgot Password":
    st.subheader("🔐 Reset Password")
    username = st.text_input("Your Username")
    email = st.text_input("Your Registered Email")
    new_pass = st.text_input("New Password", type="password")
    if st.button("Reset Password"):
        users = load_users()
        if username in users and users[username]["email"] == email:
            users[username]["password"] = hash_password(new_pass)
            save_users(users)
            st.success("✅ Password updated successfully.")
        else:
            st.error("❌ Invalid username/email combination.")

# ========== Menu: Profile ==========
elif menu == "Profile":
    if st.session_state.logged_in:
        users = load_users()
        user = users[st.session_state.username]
        st.subheader("👤 User Profile")
        st.write(f"**Username:** {st.session_state.username}")
        st.write(f"**Email:** {user.get('email', '')}")
        st.write(f"**Role:** {user.get('role', '')}")
        st.write(f"**Created On:** {user.get('created_at', '')}")
    else:
        st.warning("Please login to view profile.")

# ========== Menu: Admin Dashboard ==========
elif menu == "Admin Dashboard":
    st.subheader("📊 Admin Dashboard")
    users = load_users()
    login_logs = {}
    if os.path.exists(LOGIN_LOG):
        with open(LOGIN_LOG, "r") as f:
            login_logs = json.load(f)
    admin_data = []
    for user, info in users.items():
        email = info.get("email", "-") if isinstance(info, dict) else "-"
        created = info.get("created_at", "-") if isinstance(info, dict) else "-"
        role = info.get("role", "-") if isinstance(info, dict) else "-"
        project_dir = os.path.join("user_data", user, "projects")
        num_projects = len(os.listdir(project_dir)) if os.path.exists(project_dir) else 0
        admin_data.append({
            "Username": user,
            "Email": email,
            "Role": role,
            "Registered On": created,
            "Last Login": login_logs.get(user, "Never"),
            "Projects Reviewed": num_projects
        })
    st.dataframe(pd.DataFrame(admin_data))

    st.subheader("🗑️ Remove User and Projects")
    user_to_remove = st.selectbox("Select User", [u for u in users if u != st.session_state.username])
    if st.button("Delete User"):
        if user_to_remove in users:
            del users[user_to_remove]
            save_users(users)
            user_dir = os.path.join("user_data", user_to_remove)
            if os.path.exists(user_dir):
                import shutil
                shutil.rmtree(user_dir)
            st.success(f"✅ Removed {user_to_remove} and their projects.")

# ========== Menu: Logout ==========
elif menu == "Logout":
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.success("Logged out successfully.")
    if os.path.exists(SESSION_CACHE_FILE):
        os.remove(SESSION_CACHE_FILE)

# ========== Menu: Code Reviewer ==========
elif menu == "Code Reviewer":
    if "show_prev_projects" not in st.session_state:
        st.session_state.show_prev_projects = False
    if "show_new_review" not in st.session_state:
        st.session_state.show_new_review = False

    if not st.session_state.logged_in:
        st.warning("Please login to use the reviewer.")
    else:
        if st.session_state.get("show_login_msg", False):
            st.success(f"Welcome {st.session_state.username}!")
            st.session_state.show_login_msg = False
            st.info(random.choice(fun_facts))
        st.subheader("🧭 What would you like to do?")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🚀 Start a New Review"):
                st.session_state.show_new_review = True
                st.session_state.show_prev_projects = False
        with col2:
            if st.button("📂 View Previous Projects"):
                st.session_state.show_prev_projects = True
                st.session_state.show_new_review = False

        # ---------------------------------------------
        # 🟢 View Previous Projects Block
        if st.session_state.show_prev_projects:
            st.subheader("📂 Previously Reviewed Projects")

            project_base_dir = os.path.join("user_data", st.session_state.username, "projects")
            if os.path.exists(project_base_dir):
                project_names = sorted(os.listdir(project_base_dir))

                for project in project_names:
                    with st.expander(f"📁 {project}"):
                        report_dir = os.path.join(project_base_dir, project, "code_review_reports")
                        if not os.path.exists(report_dir):
                            st.info("No reports found.")
                            continue

                        # Project-Level Review Summary
                        project_md = os.path.join(report_dir, "project_overall_review.md")
                        if os.path.exists(project_md):
                            with open(project_md, "r", encoding="utf-8", errors='replace') as f:
                                summary_text = f.read()
                            st.markdown("**🧠 Project-Level Review (Preview)**")
                            st.markdown(summary_text + "..." if len(summary_text) > 1000 else summary_text)
                            with open(project_md, "rb") as f:
                                st.download_button("📥 Download Project-Level Summary", f, file_name=f"{project}_overall_review.md")

                        # File-Level Review Table
                        file_review_data = []
                        report_files = [f for f in os.listdir(report_dir) if f.endswith(".json")]
                        for rf in sorted(report_files):
                            file_path = os.path.join(report_dir, rf)
                            with open(file_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            file_review_data.append({
                                "File": os.path.basename(data.get("file", "-")),
                                "Summary": data.get("summary", "") + "..."
                            })

                        if file_review_data:
                            st.markdown("**📄 File-Level Reviews (Summary Preview Table)**")
                            st.dataframe(pd.DataFrame(file_review_data), use_container_width=True)

        # ---------------------------------------------
        # 🟢 Start New Review Block
        elif st.session_state.show_new_review:
            st.subheader("⚙️ Review Prompt Configuration")
            file_prompt_template = st.text_area("📄 File Review Prompt Template", load_prompt(FILE_PROMPT_PATH), height=68)
            project_prompt_template = st.text_area("📂 Project Review Prompt Template", load_prompt(PROJECT_PROMPT_PATH), height=68)
            if st.button("💾 Save Prompts"):
                with open(FILE_PROMPT_PATH, "w", encoding="utf-8") as f:
                    f.write(file_prompt_template)
                with open(PROJECT_PROMPT_PATH, "w", encoding="utf-8") as f:
                    f.write(project_prompt_template)
                st.success("Prompts saved successfully!")

            repo_url = st.text_input("Enter GitHub Repo URL")
            
            # Fetch and display Ollama models
            ollama_models = get_ollama_models()
            selected_model = st.selectbox("Select Ollama Model", ollama_models) if ollama_models else st.error("No Ollama models available.")

            def safe_llm_call(prompt, model, timeout_seconds=60):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(answer_question, prompt, model=model)  # Pass model to answer_question
                    try:
                        return future.result(timeout=timeout_seconds)
                    except TimeoutError:
                        return "⚠️ LLM timeout."

            if st.button("Start Review"):
                if not is_valid_github_url(repo_url):
                    st.error("❌ Invalid GitHub repository URL. It should be in format: https://github.com/username/repository")
                elif not selected_model:
                    st.error("❌ Please select an Ollama model.")
                else:
                    try:
                        fact = random.choice(fun_facts)
                        with st.spinner(f"Cloning and reviewing project with {selected_model}"):
                            st.subheader(fact)
                            project_path = clone_repo(repo_url)
                            project_name = os.path.basename(project_path).split("_")[0]
                            files = read_project_files(project_path)
                            files = [f for f in files if f.endswith(supported_files)]
                            report_dir = os.path.join("user_data", st.session_state.username, "projects", project_name, "code_review_reports")
                            os.makedirs(report_dir, exist_ok=True)
                            st.session_state["report_dir"] = report_dir
                            collection = create_collection(f"{st.session_state.username}_{project_name}")

                            progress_bar = st.progress(0)
                            status_placeholder = st.empty()
                            file_review_data = []

                            def review_file(i, file_path):
                                file_name = os.path.basename(file_path)
                                try:
                                    with open(file_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                    with open(FILE_PROMPT_PATH, "r", encoding="utf-8") as f:
                                        prompt_template = f.read()
                                    prompt = prompt_template.replace("{{content}}", content)

                                    review = safe_llm_call(prompt, selected_model)
                                    review_text = review.get("result", str(review)) if isinstance(review, dict) else review
                                    # Clean <think> sections from LLM output
                                    review_text = re.sub(r"//*//*", "", review_text, flags=re.DOTALL)
                                    review_text = re.sub(r"//* ", "", review_text, flags=re.DOTALL)
                                    review_text = re.sub(r"##", "", review_text, flags=re.DOTALL)
                                    review_text = re.sub(r"<think>.*?</think>", "", review_text, flags=re.DOTALL)
                                    review_text=remove_markdown_using_html(review_text)
                                    embedding = get_embedding(content)
                                    add_to_collection(collection, doc_id=i + 1, embedding=embedding,
                                                    metadata={"file": str(file_path), "summary": review_text})
                                    with open(os.path.join(report_dir, f"review_{i+1}.json"), "w") as out:
                                        json.dump({"file": file_path, "summary": review_text}, out)
                                    return {"File": file_name, "Status": "✅ Reviewed", "Review": review_text}
                                except Exception as e:
                                    return {"File": file_name, "Status": f"❌ {str(e)}", "Review": f"Error: {str(e)}"}

                            with ThreadPoolExecutor(max_workers=20) as executor:
                                futures = {executor.submit(review_file, i, file): file for i, file in enumerate(files)}
                                for i, future in enumerate(as_completed(futures)):
                                    file_review_data.append(future.result())
                                    progress_bar.progress((i + 1) / len(files))

                            # Display File-Level Review Table with Buttons
                            progress_bar.progress(1.0)
                            status_placeholder.empty()
                            st.subheader("📄 Project Summary")
                            if file_review_data:
                                st.write("### File Reviews")
                                # Table header
                                col1, col2, col3 = st.columns([3, 1, 2])
                                with col1:
                                    st.write("**Filename**")
                                with col2:
                                    st.write("**Review**")
                                with col3:
                                    st.write("**Download PDF**")

                                # Table rows
                                for i, review in enumerate(file_review_data):
                                    col1, col2, col3 = st.columns([3, 1, 2])
                                    with col1:
                                        st.write(review["File"])
                                    with col2:
                                        if st.button("View", key=f"review_{i}"):
                                            st.session_state[f"show_review_{i}"] = not st.session_state.get(f"show_review_{i}", False)
                                    with col3:
                                        pdf_buffer = generate_pdf(review["Review"], review["File"])
                                        st.download_button(
                                            label="Download",
                                            data=pdf_buffer,
                                            file_name=f"{review['File']}_review.pdf",
                                            mime="application/pdf",
                                            key=f"download_{i}"
                                        )
                                    if st.session_state.get(f"show_review_{i}", False):
                                        with st.expander(f"Review for {review['File']}"):
                                            st.markdown(review["Review"])
                            else:
                                st.info("No files were reviewed. Check if the repository contains supported file types (.java, .py, .js, .html, .txt).")

                            # ===== ✅ Whole Project-Level Review =====
                            st.subheader("🧠 Overall-Project Summary")
                            project_code_combined = ""
                            for file_path in files:
                                try:
                                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                        content = f.read()
                                        project_code_combined += f"\n\n### File: {os.path.basename(file_path)}\n{content}"
                                except Exception as e:
                                    continue
                            # ✅ Load project review prompt from prompts directory
                            PROJECT_PROMPT_PATH = "prompts/project_review_prompt.txt"
                            if os.path.exists(PROJECT_PROMPT_PATH):
                                with open(PROJECT_PROMPT_PATH, "r", encoding="utf-8") as f:
                                    prompt_template = f.read()
                            else:
                                prompt_template = "Please review the following project code:\n\n{{project_code_combined}}"

                            project_prompt = prompt_template.replace("{{project_code_combined}}", project_code_combined)
                            project_review = safe_llm_call(project_prompt, selected_model)
                            review_text = project_review.get("result", str(project_review)) if isinstance(project_review, dict) else str(project_review)
                            review_text = re.sub(r"<think>.*?</think>", "", review_text, flags=re.DOTALL)
                            review_text=remove_markdown_using_html(review_text)

                            path_md = os.path.join(report_dir, "project_overall_review.md")
                            with open(path_md, "w") as f:
                                f.write(review_text)
                            st.markdown(review_text)
                            with open(path_md, "rb") as f:
                                st.download_button("📥 Download Project-Level Review", f, file_name="project_overall_review.md")

                    except Exception as e:
                        st.error(f"Review Failed: {e}")
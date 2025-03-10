import os
import shutil
from git import Repo
from urllib.parse import urlparse
from datetime import datetime

def clone_repo(repo_url, base_dir="cloned_projects"):
    # Extract project name from repo_url
    parsed_url = urlparse(repo_url)
    project_name = os.path.splitext(os.path.basename(parsed_url.path))[0]

    # Create unique timestamp-based directory
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    clone_dir = os.path.join(base_dir, f"{project_name}_{timestamp}")

    # Ensure base directory exists
    os.makedirs(base_dir, exist_ok=True)

    # Clone into unique directory
    Repo.clone_from(repo_url, clone_dir)

    return clone_dir
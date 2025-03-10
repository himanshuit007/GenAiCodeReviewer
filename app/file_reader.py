import os

def read_project_files(base_path, extensions=['.py', '.java', '.xml', '.yml']):
    code_files = {}
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, file)
                with open(full_path, 'r', errors='ignore') as f:
                    code_files[full_path] = f.read()
    return code_files
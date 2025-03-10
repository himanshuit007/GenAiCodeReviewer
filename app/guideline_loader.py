def load_guidelines(file_path='guidelines/default_guidelines.txt'):
    with open(file_path, 'r') as f:
        return f.read()
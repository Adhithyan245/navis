import os
import py_compile
import sys

def check_syntax(directory):
    error_count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    py_compile.compile(path, doraise=True)
                except py_compile.PyCompileError as e:
                    print(f"Syntax error in {path}:\n{e}")
                    error_count += 1
    return error_count

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Checking syntax in {current_dir}...")
    errors = check_syntax(current_dir)
    if errors > 0:
        print(f"Found {errors} syntax error(s).")
        sys.exit(1)
    else:
        print("All Python files compiled successfully!")
        sys.exit(0)

import os, textwrap

base = 'D:/01_Projects/Syncguard'

def w(rel, content):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f'OK: {rel}')

w('backend/app/__init__.py', '')
w('backend/app/api/__init__.py', '')
w('backend/app/core/__init__.py', '')
w('backend/app/db/__init__.py', '')
w('backend/app/schemas/__init__.py', '')
w('backend/app/services/__init__.py', '')
w('backend/app/connectors/__init__.py', '')
w('backend/app/workers/__init__.py', '')
w('backend/app/utils/__init__.py', '')
w('backend/tests/__init__.py', '')
w('backend/tests/unit/__init__.py', '')
w('backend/tests/integration/__init__.py', '')
w('backend/tests/fixtures/__init__.py', '')
w('frontend/src/__init__.py', '')

print('All __init__.py files created')

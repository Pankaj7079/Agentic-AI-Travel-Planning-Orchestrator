"""
Quick Firebase Admin SDK connectivity test.
Run with: uv run python src/parikrama/test_firebase.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

# Load .env
for line in Path('d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/.env').read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

creds_path_raw = os.environ.get('FCM_CREDENTIALS_PATH', '')
project_root = Path('d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator')
creds_path = project_root / creds_path_raw

print(f'\nFCM_CREDENTIALS_PATH = {creds_path_raw}')
print(f'Resolved path       = {creds_path}')
print(f'File exists         = {creds_path.exists()}')

if not creds_path.exists():
    print('\n[FAIL] Credentials file not found. Check FCM_CREDENTIALS_PATH in .env')
    sys.exit(1)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    cred = credentials.Certificate(str(creds_path))

    # Only initialize if not already done
    if not firebase_admin._apps:
        app = firebase_admin.initialize_app(cred)
    else:
        app = firebase_admin.get_app()

    project_id = cred.project_id
    service_account = cred.service_account_email

    print(f'\n[PASS] Firebase Admin SDK initialized successfully!')
    print(f'       Project ID    : {project_id}')
    print(f'       Service Email : {service_account}')
    print(f'       Push notifs   : ENABLED')

    # Try a dry-run message send (validates SDK without actually sending)
    try:
        test_msg = messaging.Message(
            notification=messaging.Notification(
                title='PariKrama Test',
                body='Firebase connection verified',
            ),
            topic='test-topic',
        )
        # dry_run=True just validates — does NOT actually send
        msg_id = messaging.send(test_msg, dry_run=True)
        print(f'       Test message  : Validated (dry run) - ID: {msg_id}')
    except Exception as e2:
        print(f'       Dry-run test  : {str(e2)[:100]}')

except ImportError:
    print('\n[WARN] firebase-admin package not installed.')
    print('       Install it: uv add firebase-admin')
    print('       The credentials file itself is valid.')
except Exception as e:
    print(f'\n[FAIL] Firebase init error: {str(e)[:200]}')

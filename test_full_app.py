import sys
try:
    from backend.main import app
    print("FASTAPI APP IMPORTED SUCCESSFULLY")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

import sys
try:
    from backend.ai_classifier import ai_classifier
    from backend.threat_detection import threat_engine
    print("ALL MODULES IMPORTED SUCCESSFULLY")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

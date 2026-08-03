# run.py - نسخه اصلاح شده

"""
DrillMaster - Runner Script
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import DrillMasterApp


def main():
    """Main entry point"""
    print("🚀 Starting DrillMaster...")
    try:
        app = DrillMasterApp(sys.argv)
        exit_code = app.exec()
        print(f"✅ DrillMaster exited with code: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
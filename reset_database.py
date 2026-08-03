# reset_database.py - نسخه اصلاح شده

#!/usr/bin/env python3
"""
Reset Database - حذف دیتابیس قدیمی و ساخت جدید
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_database():
    """Reset database completely"""
    files_to_remove = [
        'drillmaster.db',
        'drillmaster.db-shm',
        'drillmaster.db-wal',
    ]
    # ✅ log فایل را حذف نمی‌کنیم
    
    print("🧹 Cleaning up old database files...")
    
    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"✅ Removed: {file}")
            except Exception as e:
                print(f"❌ Failed to remove {file}: {str(e)}")
        else:
            print(f"ℹ️ Not found: {file}")
    
    print("\n🔄 Creating new database...")
    
    try:
        from core.database import DatabaseManager
        
        db_manager = DatabaseManager()
        if db_manager.initialize():
            print("✅ New database created successfully!")
            
            # ✅ نمایش اطلاعات کاربران پیش‌فرض
            print("\n📋 Default Users Created:")
            print("  👤 admin / [DRILLMASTER_ADMIN_PASSWORD env var]")
            print("  👤 engineer / [DRILLMASTER_USER_PASSWORD env var]")
            print("  👤 viewer / viewer123")
            print("\n⚠️  Change passwords in production!")
            
            hierarchy = db_manager.get_hierarchy()
            print(f"\n📊 Hierarchy: {len(hierarchy)} companies")
            
            projects = db_manager.get_all_projects()
            print(f"📊 Projects: {len(projects)}")
            
            db_manager.close()
            return True
        else:
            print("❌ Failed to initialize database")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🔄 DrillMaster Database Reset")
    print("=" * 50)
    
    # ✅ تأیید از کاربر
    confirm = input(
        "\n⚠️  This will DELETE ALL DATA!\n"
        "Type 'RESET' to confirm: "
    )
    
    if confirm != "RESET":
        print("❌ Reset cancelled.")
        sys.exit(0)
    
    if reset_database():
        print("\n✅ Database reset completed!")
        print("Run: python run.py")
    else:
        print("\n❌ Database reset failed!")
        sys.exit(1)
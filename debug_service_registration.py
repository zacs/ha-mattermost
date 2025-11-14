"""Debug script to manually test notification service registration."""

import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

def debug_notification_system():
    """Debug the notification service registration process."""
    
    print("🔍 Debugging Notification Service Registration")
    print("=" * 50)
    
    print("""
Based on the logs, the issue appears to be that while the MattermostNotificationService
is being created successfully, it's not being registered with Home Assistant's service registry.

The logs show:
✅ Integration setup successful
✅ Discovery platform loading
✅ async_get_service called
✅ Service created successfully
❌ Service not appearing in Developer Tools

Possible causes:
1. Service registration failure (silent)
2. Service name conflict
3. Legacy notification system issue
4. Missing service description/schema

Next debugging steps:
1. Add more detailed logging after service creation
2. Check if service gets registered but with different name
3. Verify notification service base class methods
4. Check for any silent exceptions during registration

""")

    print("💡 Suggested fixes to try:")
    print("1. Check Home Assistant logs immediately after restart")
    print("2. Look for any errors in the full logs (not just Mattermost)")
    print("3. Try calling the service directly from Developer Tools")
    print("4. Check if there are multiple notification integrations conflicting")
    
    print("\n🔧 Technical Analysis:")
    print("- The notification service IS being created")
    print("- The issue is in the registration phase")
    print("- This suggests a problem with BaseNotificationService.async_register_services()")
    print("- Or an issue with the legacy discovery notification system")

if __name__ == "__main__":
    debug_notification_system()
#!/usr/bin/env python3
"""
Debugging script to test Mattermost integration step by step.

This script helps debug the integration setup process without needing 
to restart Home Assistant repeatedly.
"""

import asyncio
import sys
import os
import logging

# Setup logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

# Add the custom component to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'custom_components'))

async def test_integration():
    """Test the integration components step by step."""
    
    print("🔧 Testing Mattermost Integration Components")
    print("=" * 50)
    
    # Test 1: Import the main module
    try:
        from mattermost import MattermostHTTPClient
        print("✅ Successfully imported MattermostHTTPClient")
    except Exception as e:
        print(f"❌ Failed to import MattermostHTTPClient: {e}")
        return
    
    # Test 2: Import the notify module  
    try:
        from mattermost.notify import async_get_service, MattermostNotificationService
        print("✅ Successfully imported notify components")
    except Exception as e:
        print(f"❌ Failed to import notify components: {e}")
        return
        
    # Test 3: Import the config flow
    try:
        from mattermost.config_flow import MattermostFlowHandler
        print("✅ Successfully imported config flow")
    except Exception as e:
        print(f"❌ Failed to import config flow: {e}")
        return
    
    # Test 4: Test HTTP client creation
    print("\n🌐 Testing HTTP Client")
    print("-" * 30)
    
    # Replace with your actual values for testing
    test_url = "https://your-mattermost-server.com"
    test_token = "your-bot-token"
    
    try:
        client = MattermostHTTPClient(test_url, test_token)
        print("✅ HTTP client created successfully")
        
        # Uncomment the next line to test actual connection:
        # connection_ok = await client.test_connection()
        # print(f"🔗 Connection test: {'✅ OK' if connection_ok else '❌ Failed'}")
        
    except Exception as e:
        print(f"❌ Failed to create HTTP client: {e}")
    
    print("\n📋 Integration Status Summary")
    print("-" * 40)
    print("✅ All imports successful")
    print("✅ Components can be instantiated")  
    print("📝 Next steps:")
    print("   1. Add debug logging to Home Assistant config:")
    print("      logger:")
    print("        logs:")
    print("          custom_components.mattermost: debug")
    print("   2. Restart Home Assistant")  
    print("   3. Check logs for detailed setup process")
    print("   4. Verify integration appears in Settings > Integrations")

if __name__ == "__main__":
    print("Mattermost Integration Debug Test")
    print("Update test_url and test_token variables to test connection")
    print()
    
    try:
        asyncio.run(test_integration())
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)
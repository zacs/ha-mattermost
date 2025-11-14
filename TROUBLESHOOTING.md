# Mattermost Integration Troubleshooting Guide

## Issue: notify.mattermost service not appearing

If the integration loads without errors but the notification service doesn't appear, follow these troubleshooting steps:

### 1. Enable Debug Logging

Add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.mattermost: debug
    homeassistant.components.notify: debug
    homeassistant.helpers.discovery: debug
```

### 2. Restart Home Assistant

After adding the debug logging, restart Home Assistant completely.

### 3. Check the Logs

Look for these specific log messages in the Home Assistant logs:

**Expected Success Messages:**
```
INFO (MainThread) [custom_components.mattermost] Setting up Mattermost integration with config: ...
DEBUG (MainThread) [custom_components.mattermost] Successfully connected to Mattermost server
INFO (MainThread) [custom_components.mattermost] Mattermost integration data stored, setting up notify platform
INFO (MainThread) [custom_components.mattermost] Mattermost notify platform setup initiated
INFO (MainThread) [custom_components.mattermost.notify] async_get_service called with discovery_info: present
INFO (MainThread) [custom_components.mattermost.notify] Found Mattermost data in discovery info, creating service
INFO (MainThread) [custom_components.mattermost.notify] Initializing MattermostNotificationService
```

**Common Error Patterns:**
- If you see "Failed to connect to Mattermost server" - check your server URL and bot token
- If you see "No Mattermost data in discovery info" - there's a platform setup issue
- If you don't see any Mattermost logs at all - the integration isn't loading

### 4. Verify Integration Status

Go to **Settings** → **Devices & Services** → **Integrations** and confirm:
- Mattermost integration appears in the list
- Shows as "configured" with no errors
- Displays your server URL

### 5. Check Service Registration

Try this in **Developer Tools** → **Services**:
- Look for services starting with `notify.`
- The `notify.mattermost` service should be listed
- If not listed, there's a service registration issue

### 6. Manual Service Test

If the service appears, test it with:

```yaml
service: notify.mattermost
data:
  message: "Test message from Home Assistant"
  title: "Test Notification"
```

### 7. Common Issues and Fixes

#### Issue: Service not registering
**Symptoms:** Integration shows as configured but no notification service appears

**Solution:** 
1. Remove the integration completely
2. Restart Home Assistant
3. Re-add the integration with fresh configuration

#### Issue: "Could not connect" during setup
**Symptoms:** Setup fails with connection errors

**Fixes:**
- Verify server URL format: `https://your-server.com` (no /api/v4 suffix)
- Check bot token is valid and active
- Ensure bot has channel access
- Test server accessibility from Home Assistant host

#### Issue: Messages not sending
**Symptoms:** Service exists but messages don't appear in Mattermost

**Fixes:**
- Verify channel names don't include # symbol
- Ensure bot is added to private channels
- Check bot permissions in Mattermost
- Review Home Assistant logs for API errors

### 8. Manual Integration Reload

If you need to reload the integration without restarting:

1. Go to **Settings** → **Devices & Services** → **Integrations**
2. Find the Mattermost integration
3. Click the three dots menu → **Reload**

### 9. Complete Reset Procedure

If all else fails, perform a complete reset:

1. Remove the Mattermost integration from Settings → Integrations
2. Delete the `custom_components/mattermost` directory
3. Restart Home Assistant
4. Copy the integration files back
5. Restart Home Assistant again
6. Re-configure the integration

### 10. Verification Checklist

✅ Home Assistant version 2023.1 or later  
✅ Mattermost server accessible from Home Assistant host  
✅ Bot token is valid and active  
✅ Bot account has proper permissions  
✅ Default channel exists and bot has access  
✅ Integration shows as configured in UI  
✅ Debug logging enabled and checked  
✅ notify.mattermost service appears in Developer Tools  

### Still Having Issues?

If the integration still doesn't work:

1. Share the relevant log messages (with tokens redacted)
2. Verify your Mattermost server version and configuration
3. Test the bot token with a manual API call:
   ```bash
   curl -H "Authorization: Bearer YOUR_BOT_TOKEN" \
        https://your-server.com/api/v4/users/me
   ```

The integration has been tested with Mattermost servers and should work reliably when properly configured.
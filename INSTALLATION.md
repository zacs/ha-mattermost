# Installation Guide - Mattermost Home Assistant Integration

This guide will walk you through setting up the Mattermost notification integration for Home Assistant.

## Prerequisites

1. **Home Assistant** running (Core, Container, or Supervised)
2. **Mattermost Server** (self-hosted or cloud instance)
3. **Admin access** to your Mattermost server to create bot accounts

## Step 1: Create a Mattermost Bot Account

### Option A: Using Mattermost Web Interface

1. **Log into your Mattermost server** as an administrator
2. **Navigate to System Console**
   - Click the menu button (≡) in the top left
   - Select "System Console"
3. **Enable Bot Accounts** (if not already enabled)
   - Go to "Integrations" → "Integration Management"
   - Enable "Enable Bot Account Creation"
4. **Create a Bot Account**
   - Go to "Integrations" → "Bot Accounts"
   - Click "Add Bot Account"
   - Fill in the details:
     - **Username**: `homeassistant` (or any name you prefer)
     - **Display Name**: `Home Assistant` (or any display name you prefer)
     - **Description**: `Home Assistant notification bot`
     - **Role**: Select appropriate role (usually "Member" is sufficient)
5. **Generate Access Token**
   - After creating the bot, click "Create Token"
   - **IMPORTANT**: Copy and save this token securely - you cannot retrieve it later!
6. **Add Bot to Channels**
   - Go to the channels where you want to receive notifications
   - Use `/invite @homeassistant` (or your bot's username) to add the bot

### Option B: Using Mattermost CLI (for self-hosted)

```bash
# Create the bot user
mmctl user create --email bot@yourdomain.com --username homeassistant --password "secure-password"

# Create a bot account  
mmctl bot create homeassistant --display-name "Home Assistant" --description "Home Assistant notification bot"

# Generate access token
mmctl bot create-token homeassistant
```

## Step 2: Install the Integration

### Method A: HACS (Recommended when available)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Search for "Mattermost"
4. Click "Install"
5. Restart Home Assistant

### Method B: Manual Installation

1. **Create the directory structure**
   ```bash
   # Create custom components directory if it doesn't exist
   mkdir -p /config/custom_components/mattermost
   ```

2. **Download and copy files**
   - Download this repository
   - Copy all files from the `custom_components/mattermost/` directory to your Home Assistant `/config/custom_components/mattermost/`:
   ```
   /config/custom_components/
   └── mattermost/
       ├── __init__.py
       ├── config_flow.py
       ├── const.py
       ├── icons.json
       ├── manifest.json
       ├── notify.py
       ├── services.yaml
       └── strings.json
   ```

3. **Restart Home Assistant**

## Step 3: Configure the Integration

### Using the Home Assistant UI

1. **Navigate to Integrations**
   - Go to "Settings" → "Devices & Services"
   - Click "Add Integration"

2. **Search for Mattermost**
   - Type "Mattermost" in the search box
   - Click on the Mattermost integration

3. **Enter Configuration Details**
   - **Mattermost Server URL**: Your server URL (e.g., `https://chat.company.com`)
   - **Bot Token**: The token you generated in Step 1
   - **Default Channel**: Default channel name (without #, e.g., `general`)

4. **Test Connection**
   - The integration will test the connection automatically
   - If successful, you'll see a confirmation message

### Manual Configuration (if UI setup fails)

Add to your `configuration.yaml`:

```yaml
# This is typically not needed as the integration uses config flow
# But included here for reference
notify:
  - platform: mattermost
    url: "https://your-mattermost-server.com"
    api_key: !secret mattermost_token
    default_channel: "general"
```

Add to your `secrets.yaml`:
```yaml
mattermost_token: "your-bot-token-here"
```

## Step 4: Test the Integration

### Basic Test

1. **Go to Developer Tools** in Home Assistant
2. **Navigate to Services tab**
3. **Test basic notification**:
   ```yaml
   service: notify.mattermost
   data:
     message: "Hello from Home Assistant! 🏠"
   ```

### Test with Specific Channel

```yaml
service: notify.mattermost
data:
  message: "Test message to specific channel"
  target: "alerts"
```

### Test with Attachment

```yaml
service: notify.mattermost
data:
  title: "Test Notification"
  message: "This is a test message with rich formatting"
  data:
    attachments:
      - color: "#36a64f"
        author_name: "Home Assistant"
        title: "Integration Test"
        text: "If you can see this, the integration is working correctly!"
```

## Step 5: Create Your First Automation

Create a simple automation to test the integration:

```yaml
automation:
  - alias: "Mattermost Test Automation"
    trigger:
      platform: time
      at: "12:00:00"
    action:
      service: notify.mattermost
      data:
        title: "Daily Test Message"
        message: "Mattermost integration is working! Current time: {{ now().strftime('%Y-%m-%d %H:%M:%S') }}"
        target: "general"
```

## Troubleshooting

### Common Issues and Solutions

#### 1. "Invalid authentication" Error
**Problem**: Bot token is incorrect or expired
**Solutions**:
- Verify the token was copied correctly (no extra spaces)
- Regenerate the bot token in Mattermost
- Ensure the bot account is active

#### 2. "Cannot connect" Error  
**Problem**: Network or server issues
**Solutions**:
- Verify the Mattermost server URL is correct and accessible
- Check if the server uses HTTPS and has valid certificates
- Test connectivity: `curl -I https://your-mattermost-server.com`
- Check Home Assistant logs for detailed error messages

#### 3. "Could not find channel" Error
**Problem**: Bot doesn't have access to the specified channel
**Solutions**:
- Add the bot to the channel: `/invite @your-bot-username`
- Verify the channel name is correct (without # symbol)
- Use channel ID instead of name if needed

#### 4. File Upload Failures
**Problem**: File permissions or path issues
**Solutions**:
- Ensure file paths are within Home Assistant's allowed directories
- Check file permissions (should be readable by Home Assistant user)
- For remote files, verify URLs are accessible and in the allowed external URLs list

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.mattermost: debug
    mattermostdriver: debug
```

### Check Home Assistant Logs

1. Go to "Settings" → "System" → "Logs"
2. Look for entries related to "mattermost"
3. Check the Home Assistant log file: `/config/home-assistant.log`

## Security Best Practices

1. **Use Secrets**: Store bot tokens in `secrets.yaml`, not directly in configuration files
2. **Limit Bot Permissions**: Only give the bot access to channels it needs
3. **Regular Token Rotation**: Periodically regenerate bot tokens
4. **HTTPS Only**: Always use HTTPS for Mattermost server connections
5. **Network Security**: Ensure proper firewall rules between Home Assistant and Mattermost

## Advanced Configuration

### Custom Bot Settings

You can customize the bot behavior by modifying the `notify.py` file:

```python
# Note: The integration uses the bot's configured display name
# No username override is applied by default

# Change default author name from "Home Assistant"
"author_name": "Your System Name"
```

### Multiple Mattermost Instances

You can configure multiple Mattermost instances by setting up multiple config entries through the UI, each with different server URLs and tokens.

### Integration with Other Services

The Mattermost integration works well with:
- **Camera snapshots**: Automatically send security images
- **Sensor alerts**: Monitor temperature, humidity, etc.
- **Device tracking**: Welcome home/goodbye messages
- **System monitoring**: CPU, memory, disk space alerts

## Next Steps

1. **Explore the examples**: Check out `examples/automations.yaml` for inspiration
2. **Set up useful automations**: Security alerts, weather reports, system monitoring
3. **Customize notifications**: Use rich attachments for better formatted messages
4. **Monitor and iterate**: Review which notifications are useful and adjust accordingly

## Getting Help

If you encounter issues:

1. **Check the logs** first (see troubleshooting section above)
2. **Review the documentation** in this repository
3. **Search existing issues** in the project repository
4. **Create a new issue** with detailed information:
   - Home Assistant version
   - Integration version  
   - Mattermost version
   - Full error logs
   - Configuration (with sensitive data removed)

## Contributing

Found a bug or want to add a feature? Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

**Congratulations!** You now have Mattermost notifications set up in Home Assistant. Start creating automations to keep your team informed about your smart home status!
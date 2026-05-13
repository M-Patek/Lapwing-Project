# Security Guidelines

## API Key Management

### Never Commit Secrets

**DO NOT commit these files:**
- `.env` - Contains real API keys (already in `.gitignore`)
- `*.pem`, `*.key` - Private keys
- `secrets.json`, `secrets.yaml` - Secret configurations

### Use Template Files

**Always use `.env.example` as template:**
```bash
# Copy template to create your local config
cp .env.example .env

# Edit .env with your real API keys
notepad .env
```

### Security Check

Run before committing:
```bash
python security_check.py
```

This will scan for:
- API keys (sk-...)
- Hardcoded secrets
- Passwords in source code

### Current Configuration

**Provider:** DeepSeek
**Model:** deepseek-v4-flash

Required environment variables:
```bash
DEEPSEEK_API_KEY=your-key-here
```

### If You Accidentally Committed Secrets

1. **Immediately revoke the exposed key** at https://platform.deepseek.com/
2. **Generate a new key**
3. **Update your `.env` file**
4. **Force push to remove from git history** (if pushed)

### Best Practices

1. **Keep `.env` in `.gitignore`** (already done)
2. **Use different keys for dev/prod**
3. **Rotate keys regularly**
4. **Never share your `.env` file**
5. **Use environment-specific configs**

## Reporting Security Issues

If you find a security vulnerability, please:
1. Do not open a public issue
2. Contact the maintainer directly

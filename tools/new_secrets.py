"""Print new values for Vercel Environment Variables; never save them in source."""
import secrets
print('SECRET_KEY=' + secrets.token_hex(32))
print('ADMIN_PASSWORD=' + secrets.token_urlsafe(24))

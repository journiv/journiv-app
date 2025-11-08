# 📘 Journiv - Private Journal
<p align="center">
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta">
  <img src="https://img.shields.io/badge/active%20development-yes-brightgreen" alt="Active Development">
  <img src="https://img.shields.io/badge/backups-recommended-critical" alt="Backups Recommended">
</p>

> ⚠️ **Beta Software**
>
> Journiv is currently in **beta** and under **active development**.
> While the developers aims to keep data **backward-compatible**, breaking changes may still occur. Please **keep regular backups of your data** to avoid loss during updates.


Journiv is a self-hosted private journal. It features comprehensive journaling capabilities including mood tracking, prompt-based journaling, media uploads, analytics, and advanced search with a clean and minimal UI.

<p align="center">
  <a href="https://journiv.com" target="_blank">
    <img src="https://img.shields.io/badge/Visit%20Website-405DE6?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Visit Journiv Website">
  </a>
  &nbsp;&nbsp;
  <a href="https://hub.docker.com/r/swalabtech/journiv-app" target="_blank">
    <img src="https://img.shields.io/docker/pulls/swalabtech/journiv-app?style=for-the-badge&logo=docker&logoColor=white&color=2496ED" alt="Docker Pulls">
  </a>
  &nbsp;&nbsp;
  <a href="https://discord.com/invite/CuEJ8qft46" target="_blank">
    <img src="https://img.shields.io/badge/Join%20us%20on%20Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Journiv Discord">
  </a>
  &nbsp;&nbsp;
  <a href="https://www.reddit.com/r/Journiv/" target="_blank">
    <img src="https://img.shields.io/badge/Join%20Reddit%20Community-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Join Journiv Reddit">
  </a>
</p>

<div align="center">
  <video
    src="https://github.com/user-attachments/assets/e34f800d-b2d9-4fca-b3ee-c71e850ed1e9"
    controls
    width="640"
    playsinline
    preload="metadata">
  </video>
</div>
<div align="center">
  <a href="https://www.youtube.com/watch?v=nKoUh7VP-eE" target="_blank">
    <img src="https://github.com/user-attachments/assets/9ff6c98f-88d5-4780-982a-d485f869d68c" height="400">
  </a>
  &nbsp;&nbsp;&nbsp;
  <a href="https://www.youtube.com/shorts/-cRwaPKltvQ" target="_blank">
    <img src="https://github.com/user-attachments/assets/d236fdc3-a6da-496b-a51d-39ca77d9be44" height="400">
  </a>
</div>

<p align="center">
  👉 <a href="https://www.youtube.com/watch?v=nKoUh7VP-eE" target="_blank">Watch Web Demo</a> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.youtube.com/shorts/-cRwaPKltvQ" target="_blank">Watch Mobile Demo</a>
</p>

## 🏁 Quick Start

### Installation

#### Docker Compose (Recommended)
```yaml
services:
  journiv:
    image: swalabtech/journiv-app:latest
    container_name: journiv
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=your-secret-key-here # Replace with a strong secret key
      - DOMAIN_NAME=192.168.1.1 # Your server IP or domain
    volumes:
      - journiv_data:/data
    restart: unless-stopped

volumes:
  journiv_data:
```

**Generate a secure SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# OR
openssl rand -base64 32
```

**Run the container:**
```
docker compose -f docker-compose.yml up -d
```
---

#### Docker Run (If you are not using Docker Compose)
```bash
docker run -d \
  --name journiv \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret-key-here \
  -e DOMAIN_NAME=192.168.1.1 \
  -v journiv_data:/data \
  --restart unless-stopped \
  swalabtech/journiv-app:latest
```

**Access Journiv:** Open `http://192.168.1.1:8000` (replace with your server IP) in your browser to start journaling!
You can also open it on your mobile device and install it as a Progressive Web App (PWA).


### Highly Recommended: Use HTTPS

Journiv works on your local network using plain HTTP, but enabling HTTPS dramatically improves the experience, especially when accessing through a web browser. Many browsers restrict advanced features (secure storage, service workers, etc.) on HTTP connections.

#### Why HTTPS Matters

**Secure Storage for Login Tokens:**
- **HTTPS or localhost**: Browser uses encrypted storage for login tokens
- **HTTP on network**: Tokens stored in local storage without encryption

**Faster Loads & Offline Support:**
- Service worker caches assets (JS, icons, fonts) for instant loading
- Works offline and auto-updates when new versions are available
- Browsers only enable service workers on HTTPS or localhost

**Progressive Web App (PWA) Features:**
- Installing Journiv to your home screen is possible with `http` but `https` enables offline access.
- View past entries offline without network access
- Near-instant loading on all devices

**Recommendations:**
- **Best**: HTTPS with valid SSL certificate (Let's Encrypt via Caddy/Traefik)
- **Good**: Access via `localhost` or `127.0.0.1` (secure storage enabled)
- **OK**: HTTP on local network (limited features, tokens less secure)

**Note:** Mobile apps (coming soon) always use secure storage regardless of connection type.

#### Enabling HTTPS

Enable HTTPS in minutes using any of these methods:

| Method                | Description                                               |
| --------------------- | --------------------------------------------------------- |
| **Caddy**             | Automatic HTTPS via Let's Encrypt – one-line setup        |
| **Traefik**           | Docker-friendly reverse proxy with automatic certificates |
| **Tailscale HTTPS**   | Free `.ts.net` domain with HTTPS out of the box           |
| **Cloudflare Tunnel** | Instant secure URL                                        |


## 🐳 Docker Compose Configuration

Journiv provides multiple Docker Compose configurations for different use cases:

### Available Configurations
- **`docker-compose.simple.yml`** - Minimal production setup to get started
- **`docker-compose.yml`** - Full production configuration with profiles
- **`docker-compose.dev.yml`** - Development configuration with hot reload

### 🔧 Configuration Management

#### Environment Variables

All configurations use environment variables for customization. The minimal required configuration:

```bash
SECRET_KEY=your-secret-key-here
DOMAIN_NAME=your-server-ip-or-domain
```

Optional environment variables (see `.env.template` for full list):
- `DATABASE_URL` - Database connection string (defaults to SQLite)
- `MEDIA_ROOT`, `LOG_DIR` - Storage paths (defaults to `/data/media`, `/data/logs`)
- `ENABLE_CORS`, `CORS_ORIGINS` - CORS configuration for mobile apps
- `MAX_FILE_SIZE_MB` - Upload size limit
- `LOG_LEVEL` - Logging verbosity

#### Database Configuration

**SQLite (Default)**

No configuration needed. The database is automatically created at `/data/journiv.db` inside the container.

```yaml
# Default behavior - no DATABASE_URL needed
volumes:
  - journiv_data:/data
```

**PostgreSQL (Optional)**

For multi-user deployments, set these environment variables:

```bash
POSTGRES_HOST=postgres
POSTGRES_USER=journiv
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=journiv_prod
POSTGRES_PORT=5432
```

Or use the full database URL:

```bash
DATABASE_URL=postgresql://journiv:password@postgres:5432/journiv_prod
```

#### Storage and Media

All application data is stored in `/data/` inside the container:

```
/data/
├── journiv.db          # SQLite database file
├── media/              # Uploaded images, videos, audio
└── logs/               # Application logs
```

Mount this directory as a volume to persist data:

```yaml
volumes:
  - journiv_data:/data  # Named volume (recommended)
  # OR
  - ./data:/data         # Bind mount (for easy access)
```

**Supported file types:**
- Images: JPEG, PNG, GIF, WebP
- Videos: MP4, AVI, MOV, WebM
- Audio: MP3, WAV, OGG, M4A, AAC

### 🔍 Health Checks

Monitor your Journiv instance using the health endpoints:

```bash
# Check application health
curl http://localhost:8000/api/v1/health

# Response when healthy:
{
  "status": "healthy",
  "database": "connected",
  "version": "0.1.0-beta.4"
}

# Check memory usage
curl http://localhost:8000/api/v1/health/memory
```

### 🗂️ Backup and Data Management

#### Backing Up Your Data

All your data is in the `/data` volume. To back it up:

**Using Docker volumes:**
```bash
# Stop the container
docker stop journiv

# Create a backup
docker run --rm \
  -v journiv_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/journiv-backup-$(date +%Y%m%d).tar.gz /data

# Restart the container
docker start journiv
```

**Using bind mounts:**
```bash
# Simply copy the data directory
cp -r ./data ./journiv-backup-$(date +%Y%m%d)
```

#### Restoring From Backup

**Docker volumes:**
```bash
# Stop and remove the container
docker stop journiv && docker rm journiv

# Remove old volume
docker volume rm journiv_data

# Restore from backup
docker run --rm \
  -v journiv_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/journiv-backup-YYYYMMDD.tar.gz -C /

# Start the container again
docker-compose up -d
```


## 🔒 Security

### Authentication System

Journiv supports two authentication methods:

#### 1. Email/Password Authentication (Default)

Journiv uses a stateless JWT-based authentication designed for self-hosted environments.

**Token Types:**
- **Access Token**: Short-lived (15 minutes), used for API requests
- **Refresh Token**: Long-lived (7 days), used to obtain new access tokens

**How It Works:**
1. Login generates both tokens
2. Access token expires after 15 minutes
3. Client automatically refreshes using refresh token
4. Same refresh token is reused until it expires (7 days)
5. After 7 days, user must log in again

**Token Management:**
- Tokens are stateless and not stored in the database
- Each token includes a unique JWT ID (JTI) for future compatibility
- To invalidate all tokens instantly, change `SECRET_KEY` and restart

**Token Lifecycle Example:**
```
Day 0, 00:00: Login → Access (exp: 15min) + Refresh (exp: 7 days)
Day 0, 00:15: Auto-refresh → New Access token, keep Refresh token
Day 0, 00:30: Auto-refresh → New Access token, keep Refresh token
...
Day 7, 00:00: Refresh token expires → User must log in again
```

#### 2. OIDC/SSO Authentication (Optional)

Journiv supports OpenID Connect (OIDC) for Single Sign-On with identity providers like Pocket ID, Keycloak, Authentik, or Auth0.

**Key Features:**
- **Passwordless authentication** - Sign in with your existing identity provider
- **Single Sign-On (SSO)** - One login for multiple applications
- **Single Sign-Out** - Logout from Journiv and your identity provider simultaneously
- **Auto-provisioning** - Create accounts automatically on first login
- **PKCE security** - Enhanced security for the authorization code flow

**Supported Providers:**
- [Pocket ID](https://pocketid.app/) - Self-hosted OIDC provider with passkey support
- [Keycloak](https://www.keycloak.org/) - Enterprise identity and access management
- [Authentik](https://goauthentik.io/) - Open-source identity provider
- [Auth0](https://auth0.com/) - Managed authentication service
- Any OIDC-compliant provider

**How OIDC Works:**
1. User clicks "Sign in with SSO" on login page
2. Redirected to your identity provider (e.g., Pocket ID)
3. Authenticate with your provider (passkey, password, 2FA, etc.)
4. Provider redirects back to Journiv with authorization code
5. Journiv exchanges code for user information
6. Account created automatically (if auto-provisioning enabled)
7. Journiv issues its own JWT tokens (same as email/password flow)

**Token Management:**
- OIDC provider handles initial authentication only
- Journiv manages access/refresh tokens independently
- Token refresh is handled by Journiv backend (not the OIDC provider)
- Logout clears both Journiv tokens AND provider session (SSO logout)

**Configuration:**

See the [OIDC Setup Guide](#oidc-sso-setup) below for detailed configuration instructions.

**Security Best Practices:**
- Generate a strong `SECRET_KEY` (at least 32 random characters)
- Run behind a firewall or VPN (don't expose to the internet directly)
- Use HTTPS for all connections (especially for OIDC)
- Change password if you suspect compromise
- Log out from untrusted devices
- Use strong OIDC provider with 2FA/passkeys when available

## OIDC/SSO Setup

Enable Single Sign-On authentication with your existing identity provider.

### Prerequisites

- An OIDC-compliant identity provider (Pocket ID, Keycloak, Authentik, Auth0, etc.)
- Admin access to your identity provider to register Journiv as a client
- HTTPS enabled for both Journiv and your identity provider (recommended)

### Quick Start: Pocket ID Example

[Pocket ID](https://pocketid.app/) is a self-hosted OIDC provider with passkey support. Perfect for homelab setups!

#### Step 1: Install OIDC Provider
Install [Pocked ID](https://pocket-id.org/docs/setup/installation) or an OIDC provider of your choice.

Please ensure you have completed the initial setup of your OIDC provider.

#### Step 2: Register Journiv in Pocket ID

1. Go to **Settings → Applications → Create Application**
2. Fill in the application details:
   - **Name**: `Journiv`
   - **Client ID**: `journiv-app` (or choose your own or one generated by your OIDC provider)
   - **Redirect URI**: `http://journiv-domain:journiv-port/api/v1/auth/oidc/callback`. Must match `OIDC_REDIRECT_URI` in Journiv config.
   - **Scopes**: Select `openid`, `email`, `profile`
   - **Logout Callback URI (if supported by your OIDC provider)**: `http://journiv-domain:journiv-port/:8000`
   - **Client Launch URI (if needed by your OIDC provider)**: `http://journiv-domain:journiv-port/:8000`

3. Save and copy the **Client ID** and/or **Client Secret** (you'll need this)

#### Step 3: Configure Journiv

Add these environment variables to your Journiv deployment:

**Docker Compose Environment or .env file:**
```yaml
      # OIDC Configuration
      - OIDC_ENABLED=true
      - OIDC_ISSUER=https://pocketid.example.com
      - OIDC_CLIENT_ID=journiv-app or once generated by your OIDC provider
      - OIDC_CLIENT_SECRET=your-client-secret-from-pocket-id
      - OIDC_REDIRECT_URI=http://journiv-domain:journiv-port/api/v1/auth/oidc/callback
      - OIDC_SCOPES=openid email profile
      - OIDC_AUTO_PROVISION=true
```

#### Step 4: Test SSO Login

1. Open Journiv in your browser
2. Click **"Sign in with SSO"** on the login page
3. Authenticate with your Pocket ID credentials
4. You'll be redirected back to Journiv and logged in automatically!

### Configuration Options

#### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `OIDC_ENABLED` | Enable OIDC authentication | `true` |
| `OIDC_ISSUER` | Your OIDC provider's issuer URL | `https://auth.example.com` |
| `OIDC_CLIENT_ID` | OAuth2 client ID from your provider | `journiv-app` |
| `OIDC_CLIENT_SECRET` | OAuth2 client secret from your provider | `super-secret-key` |
| `OIDC_REDIRECT_URI` | Callback URL (must match provider config) | `https://journiv-domain:port/api/v1/auth/oidc/callback` |

#### Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_SCOPES` | OAuth2 scopes to request | `openid email profile` |
| `OIDC_AUTO_PROVISION` | Auto-create accounts on first login | `true` |
| `OIDC_DISABLE_SSL_VERIFY` | Disable SSL verification (dev only!) | `false` |
| `REDIS_URL` | Redis for OIDC state (production) | `none` |

#### Understanding Auto-Provisioning

**When `OIDC_AUTO_PROVISION=true` (Default):**
- New users are created automatically on first SSO login
- Account uses email from OIDC provider
- No pre-registration required

**When `OIDC_AUTO_PROVISION=false`:**
- Users must be registered via email/password first
- Only existing users can login via SSO
- Links OIDC identity to existing account

### Troubleshooting

#### "Invalid redirect URI" Error

**Cause:** Mismatch between Journiv's `OIDC_REDIRECT_URI` and provider's registered redirect URI.

**Fix:**
1. Check your provider's application settings
2. Verify redirect URI matches exactly (including protocol, domain, port, path)
3. Ensure no trailing slashes

Example correct URI: `https://journiv.myhomelab.com/api/v1/auth/oidc/callback`

#### "SSL certificate verification failed" Error

**Cause:** Self-signed certificate on OIDC provider.

**Fix:** Use valid SSL certificates (Let's Encrypt, Cloudflare, etc.)

#### "Invalid client credentials" Error

**Cause:** Wrong `CLIENT_ID` or `CLIENT_SECRET`.

**Fix:**
1. Copy client ID and secret from provider exactly
2. Check for extra spaces or quotes
3. Regenerate secret if needed

#### "User not authorized" with Auto-Provision Disabled

**Cause:** User doesn't exist and `OIDC_AUTO_PROVISION=false`.

**Fix:**
1. Register user via email/password first
2. Then login with SSO to link accounts
3. Or enable `OIDC_AUTO_PROVISION=true`

#### OIDC Login Works but Logout Doesn't Clear Provider Session

**Cause:** Provider doesn't support `end_session_endpoint`.

**Status:** Journiv will clear local session but provider session remains active. This is a provider limitation, not a bug.

**Workaround:** Manually logout from provider separately.

### FAQ

**Q: Can I use both email/password and OIDC?**
A: Yes! Users can choose either method. Existing email/password users can link OIDC accounts.

**Q: What happens if OIDC provider goes down?**
A: Existing sessions continue working (tokens are local). New logins via OIDC will fail, but email/password login still works.

**Q: Can I use multiple OIDC providers?**
A: Currently, only one OIDC provider is supported.

**Q: Is my OIDC password stored in Journiv?**
A: No! OIDC passwords are only stored in your identity provider. Journiv never sees your OIDC credentials.

## ✨ Features

### Core Features

**Authentication & User Management**
- User registration and login with JWT tokens
- OpenID Connect (OIDC) Single Sign-On support
- Password hashing with Argon2
- Refresh token support with configurable expiry
- User profile management and settings
- Support for multiple authentication methods (email/password + OIDC)

**Journal Management**
- Create, read, update, and delete journals
- Journal analytics (entry counts, last entry date)
- Color and icon customization
- Favoriting and archiving (coming soon)

**Entry Management**
- Rich text entries with word count tracking
- Full CRUD operations on entries
- Advanced search and filtering
- Date range filtering
- Entry pinning (coming soon)

**Tag System**
- Create and manage tags
- Tag entries with many-to-many relationships
- Tag-based filtering and search
- Tag usage statistics and analytics
- Popular tags and suggestions

**Mood Tracking**
- Log moods with timestamps
- Mood analytics and trends
- Streak calculation and tracking
- Recent mood history
- Pattern analysis

**Prompt-Based Journaling**
- Daily writing prompt suggestions
- Prompt search and filtering by category/difficulty
- Usage statistics and analytics
- Direct entry creation from prompts

**Media Management**
- Upload images, videos, and audio files
- Automatic thumbnail generation
- File validation and size limits
- Metadata extraction
- Supported formats: JPEG, PNG, GIF, WebP, MP4, AVI, MOV, WebM, MP3, WAV, OGG, M4A, AAC

**Analytics & Insights**
- Automatic writing streak tracking
- Writing pattern analysis
- Productivity metrics and trends
- Journal-level analytics
- Content insights dashboard

**Search**
- Full-text search across all entries
- Multi-filter search with 10+ filter options
- Global search across content types
- Tag-based and date-based filtering
- Search performance analytics

### Technical Features

**Infrastructure**
- Docker containerization for easy deployment
- SQLite-first architecture (PostgreSQL optional)
- Alembic database migrations
- Structured logging with configurable levels
- Health check endpoints
- Production-ready security headers
- Redis support for distributed caching (OIDC state management)

**Timezone Support**
- Automatic timezone detection on registration
- User-specific timezone storage
- Smart date calculations in user's local timezone
- Daily prompts change at midnight in user's timezone
- Writing streaks calculated using local dates
- Update timezone anytime in profile settings


## 🏗️ Architecture

### Tech Stack

**Backend Framework**
- FastAPI 0.104.1 - Modern async web framework
- SQLModel 0.0.14 - Type-safe ORM built on SQLAlchemy 2.0
- Pydantic 2.x - Data validation and settings management

**Database**
- SQLite (default) - Zero-configuration embedded database
- PostgreSQL (optional) - For multi-user production deployments
- Alembic - Database migration management

**Security**
- JWT authentication via python-jose
- OpenID Connect (OIDC) via Authlib with PKCE support
- Argon2 password hashing via passlib
- Rate limiting via slowapi
- Security headers (CSP, HSTS, X-Frame-Options)
- Secure OIDC state management with Redis or in-memory cache

**Media & Storage**
- Filesystem-based media storage
- Pillow - Image processing and thumbnails
- python-magic - File type detection
- ffmpeg-python - Video processing

**Infrastructure**
- Docker and Docker Compose
- Gunicorn with Uvicorn workers (production)
- Structured logging with Python logging module
- Health check endpoints

**Testing**
- pytest - Test framework
- httpx - Async HTTP client for API testing

### Project Structure
```
journiv-backend/
├── app/
│   ├── api/v1/              # API endpoints by version
│   │   └── endpoints/       # Route handlers
│   ├── core/                # Core functionality
│   │   ├── config.py        # Application configuration
│   │   ├── database.py      # Database setup and engine
│   │   ├── security.py      # Auth utilities
│   │   └── logging_config.py
│   ├── middleware/          # Custom middleware
│   │   ├── request_logging.py
│   │   ├── csp_middleware.py
│   │   └── trusted_host.py
│   ├── models/              # SQLModel database models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic layer
│   ├── web/                 # Flutter web app (PWA)
│   └── main.py              # FastAPI application entry point
├── alembic/                 # Database migrations
├── scripts/                 # Deployment and utility scripts
├── tests/                   # Test suite
└── docker-compose.yml       # Docker configuration
```

## 📚 Documentation

### API Documentation

Once Journiv is running, access the interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs` - Interactive API testing
- **ReDoc**: `http://localhost:8000/redoc` - Clean API reference
- **OpenAPI Schema**: `http://localhost:8000/openapi.json` - Machine-readable spec

### Development Resources

**Database Schema**
- Models defined in `app/models/` directory
- Relationships documented in model files
- Migrations tracked in `alembic/versions/`

**Code Documentation**
- API endpoints: `app/api/v1/endpoints/`
- Business logic: `app/services/`
- Database models: `app/models/`
- Request/response schemas: `app/schemas/`

## 🤝 Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

## 📄 License

This project is licensed under the terms specified in the LICENSE file.

## 🆘 Support

Need help or want to report an issue?

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions and share ideas
- **Email**: journiv@protonmail.com
- **Discord**: Join our [community server](https://discord.gg/CuEJ8qft46)

---

[![Star History Chart](https://api.star-history.com/svg?repos=journiv/journiv-app&type=Date)](https://star-history.com/#journiv/journiv-app&Date)

**Made with care for privacy-conscious journaling**

Disclaimer:
This repository contains portions of code, documentation, or text generated with the assistance of AI/LLM tools. All outputs have been reviewed and adapted by the author to the best of their ability before inclusion.

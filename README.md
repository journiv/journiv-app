# 📘 Journiv - Private Journal

Journiv is a self-hosted private journal. It features comprehensive journaling capabilities including mood tracking, prompt-based journaling, media uploads, analytics, and advanced search with a clean and minimal UI.

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
      - SECRET_KEY=your-secret-key-here
      - DOMAIN_NAME=192.168.1.1 # Your server IP or domain
    volumes:
      - ./data:/data
    restart: unless-stopped
```

**Generate a secure SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# OR
openssl rand -base64 32
```

#### Docker Run
```bash
docker run -d \
  --name journiv \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret-key-here \
  -e DOMAIN_NAME=192.168.1.1 \
  -v $(pwd)/data:/data \
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
  "version": "0.1.0-beta.1"
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

**Security Best Practices:**
- Generate a strong `SECRET_KEY` (at least 32 random characters)
- Run behind a firewall or VPN (don't expose to the internet directly)
- Use HTTPS for all connections
- Change password if you suspect compromise
- Log out from untrusted devices

**Token Lifecycle Example:**
```
Day 0, 00:00: Login → Access (exp: 15min) + Refresh (exp: 7 days)
Day 0, 00:15: Auto-refresh → New Access token, keep Refresh token
Day 0, 00:30: Auto-refresh → New Access token, keep Refresh token
...
Day 7, 00:00: Refresh token expires → User must log in again
```

## ✨ Features

### Core Features

**Authentication & User Management**
- User registration and login with JWT tokens
- Password hashing with Argon2
- Refresh token support with configurable expiry
- User profile management and settings

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
- Argon2 password hashing via passlib
- Rate limiting via slowapi
- Security headers (CSP, HSTS, X-Frame-Options)

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

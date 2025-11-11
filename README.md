# 📘 Journiv - Private Journal

> ⚠️ **Beta Software**
>
> Journiv is currently in **beta** and under **active development**.
> While the developers aims to keep data **backward-compatible**, breaking changes may still occur. Please **keep regular backups of your data** to avoid loss during updates.


Journiv is a self-hosted private journal. It features comprehensive journaling capabilities including mood tracking, prompt-based journaling, media uploads, analytics, and advanced search with a clean and minimal UI.
<p align="center">
  <a href="https://journiv.substack.com/" target="_blank">
    <img src="https://img.shields.io/badge/📬%20Subscribe%20to%20Journiv%20Latest%20Updates%20on%20Substack-1E1E1E?style=for-the-badge&logo=substack&logoColor=FF6719&labelColor=1E1E1E&color=FF6719" alt="Subscribe to Journiv Latest Updates on Substack">
  </a>
</p>

---

<p align="center">
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta">
  <img src="https://img.shields.io/badge/active%20development-yes-brightgreen" alt="Active Development">
  <img src="https://img.shields.io/badge/backups-recommended-critical" alt="Backups Recommended">
</p>

<p align="center">
  <a href="https://journiv.com" target="_blank">
    <img src="https://img.shields.io/badge/Visit%20Website-405DE6?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Visit Journiv Website">
  </a>
  &nbsp;&nbsp;
  <a href="https://hub.docker.com/r/swalabtech/journiv-app" target="_blank">
    <img src="https://img.shields.io/docker/pulls/swalabtech/journiv-app?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Pulls">
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

#### Environment Variables

All configurations use environment variables for customization. The minimal required configuration:

```bash
SECRET_KEY=your-secret-key-here
DOMAIN_NAME=your-server-ip-or-domain
```

**Access Journiv:** Open `http://192.168.1.1:8000` (replace with your server IP) in your browser to start journaling!

## Documentation

Read the [docs](https://github.com/journiv/journiv-app/wiki/Journiv-Documentation) to learn more about Journiv and configuring it.


## Contributing

Contributions are welcome! Please see CONTRIBUTING.md and LICENSE for guidelines.

## License

This project is licensed under the terms specified in the LICENSE file.

## Support

Need help or want to report an issue?

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions and share ideas
- **Email**: journiv@protonmail.com
- **Discord**: Join our [community server](https://discord.gg/CuEJ8qft46)

![Star History Chart](https://api.star-history.com/svg?repos=journiv/journiv-app&type=Date)

---

**Made with care for privacy-conscious journaling**

Disclaimer:
This repository contains portions of code, documentation, or text generated with the assistance of AI/LLM tools. All outputs have been reviewed and adapted by the author to the best of their ability before inclusion.

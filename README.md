# 📘 Journiv - Private Journal

> ⚠️ **Beta Software**
>
> Journiv is currently in **beta** and under **active development**.
> While the developers aims to keep data **backward-compatible**, breaking changes may still occur. Please **keep regular backups of your data** to avoid loss during updates.


Journiv is a self-hosted private journal. It features comprehensive journaling capabilities including mood tracking, prompt-based journaling, media uploads, analytics, and advanced search with a clean and minimal UI.

<p align="center">
  <a href="https://www.pikapods.com/pods?run=journiv" target="_blank">
    <img src="https://www.pikapods.com/static/run-button.svg" alt="Run on PikaPods">
  </a>
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
<p align="center">
  <img src="https://img.shields.io/badge/status-beta-orange" alt="Status: Beta">
  <img src="https://img.shields.io/badge/active%20development-yes-brightgreen" alt="Active Development">
  <img src="https://img.shields.io/badge/backups-recommended-critical" alt="Backups Recommended">
</p>

<!-- <div align="center">
  <video
    src="https://github.com/user-attachments/assets/e34f800d-b2d9-4fca-b3ee-c71e850ed1e9"
    controls
    width="640"
    playsinline
    preload="metadata">
  </video>
</div> -->


<div align="center">
  <a href="https://www.youtube.com/watch?v=nKoUh7VP-eE" target="_blank">
    <img height="400" alt="Journiv_Web_Tab_Mobile" src="https://github.com/user-attachments/assets/de613e87-a103-4935-a7ff-78013cba0e00" />
    <!-- <img src="https://github.com/user-attachments/assets/d5c9e87d-83e1-4e99-8491-d44ea61fbecc" height="400"> -->
  </a>
  <!-- &nbsp;&nbsp;&nbsp;
  <a href="https://www.youtube.com/shorts/-cRwaPKltvQ" target="_blank">
    <img src="https://github.com/user-attachments/assets/d236fdc3-a6da-496b-a51d-39ca77d9be44" height="400">
  </a> -->
</div>

<p align="center">
  👉 <a href="https://www.youtube.com/@JournivApp" target="_blank">Watch Demo Videos</a> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
</p>

## Quick Start
Give Journiv a quick try with one docker command.

> [!NOTE]
> This `docker run` command starts a **minimal** version of Journiv. It lack components needed for various features of Journiv like import/export etc. For a complete docker compose file use [this](https://github.com/journiv/journiv-app/blob/refs/tags/latest/docker-compose.yml).

### Docker Run

```bash
docker run -d \
  --name journiv \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret-key-here \
  -e DOMAIN_NAME=192.168.1.1 \
  -e ALLOW_INSECURE_COOKIE_AUTH_OVER_HTTP=true \
  -v journiv_data:/data \
  --restart unless-stopped \
  swalabtech/journiv-app:latest
```

**Access Journiv:** Open `http://192.168.1.1:8000` (replace with your server IP) in your browser to try it out.

> [!WARNING]
> The insecure HTTP opt-in above exists for isolated, trusted LANs only. HTTP
> exposes passwords and refresh cookies to interception by other devices on the
> network. Use `DOMAIN_SCHEME=https` for any internet-accessible or untrusted
> network deployment.

**For complete installation guide see [installation guide](https://journiv.com/docs/installation).**

### Web interfaces

The production container serves both compiled frontends from the same FastAPI
origin and public port:

```text
/              React frontend (primary)
/legacy/       Flutter frontend (temporary legacy interface)
/api/v1/*      FastAPI API
/pub/*         Public publishing routes
/docs          FastAPI docs when enabled
/openapi.json  FastAPI OpenAPI schema
```

React is the default Journiv interface from this release onward. The Flutter
interface remains available temporarily at `/legacy/` for users who need to
switch back during the transition and may be removed in a future release.

Upgrades from versions where Flutter owned `/` are handled by a narrowly scoped
retirement worker at `/flutter_service_worker.js`. It replaces only the old
root Flutter worker, removes the standard `flutter-app-*` caches, unregisters
itself, and reloads a controlled window. React also performs a one-time check
for that exact root registration. Other service-worker registrations are left
untouched, preserving a path for future React PWA support.

## Demo
Want to just try a [demo](https://demo.almostadatacenter.com)?
(Thanks to [JasonFieldz](https://github.com/JasonFieldz) for hosting a demo instance).
- Username: demo@test.com
- Password: Demo1234

## Documentation

Read the [docs](https://journiv.com/docs) to learn more about Journiv and configuring it.


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

## Disclaimer
**AI-Assisted Development**

Journiv is a personal source avaliable project developed outside of my full-time work as a software engineer. It grew out of a need I had for many years for a capable, private, self-hosted journaling application. I could not find an existing option that matched what I wanted, so Journiv started as a project to build one.

AI-powered software development tools have made it practical for me to develop and maintain a project of this scope in the limited time available outside of work. Without these tools, I realistically would not have the time to build many of the features and experiences that Journiv provides today.

AI assistance has been used most extensively in the development of the latest React frontend (V2), including implementation, refactoring, testing, code review assistance, and documentation. Other parts of the repository also contains portions of code, documentation, or text generated with the assistance of AI/LLM tools.

AI tools are used as development aids, while product requirements, architecture, design decisions, and release decisions remain human-directed.

The level of manual review varies by area of the codebase. Backend changes are generally read and reviewed at the code level, with an understanding of the Python implementation and surrounding application behavior. For the React frontend, review is more heavily focused on the resulting user experience and application behavior through hands-on UI testing, automated tests, and targeted inspection of the generated code rather than a line-by-line review of every change.

AI-assisted contributions are refined, tested, and iterated on as part of the normal development process, with the goal of meeting the same functional, maintainability, security, and quality expectations as the rest of the project.

AI use during development is separate from Journiv's runtime behavior. Journiv does not require an LLM service in order to run, and the use of AI coding tools during development does not cause journal entries or other private user content to be sent to an AI provider.

Journiv recognizes that people have different preferences and comfort levels around AI-assisted software development. This disclosure is intended to be clear about how Journiv is built so that users and contributors can make an informed decision about whether the project is right for them.

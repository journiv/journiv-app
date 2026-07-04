# 📘 Journiv - Private Journal

> [!NOTE]
> Active development on this project is currently paused during June–August due to summer travel and family commitments.
>
> Development will resume in August.
>
> For any urgent issues, please contact: contact@journiv.com.


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
  -v journiv_data:/data \
  --restart unless-stopped \
  swalabtech/journiv-app:latest
```

**Access Journiv:** Open `http://192.168.1.1:8000` (replace with your server IP) in your browser to try it out.

**For complete installation guide see [installation guide](https://journiv.com/docs/installation).**

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
**AI/LLM Usage**

This repository contains portions of code, documentation, or text generated with the assistance of AI/LLM tools. All outputs have been reviewed and adapted by the author to the best of their ability before inclusion.

# Code signing policy

Current releases and GitHub Actions artifacts are unsigned. No code signing certificate or production signing service is configured.

## Project roles

- Author and reviewer: [B1GM4NT1NGS](https://github.com/B1GM4NT1NGS).
- Release signing approver: [B1GM4NT1NGS](https://github.com/B1GM4NT1NGS).

Changes from other contributors must be reviewed by the maintainer. If signing is added, production signing requests will require the maintainer's manual approval and multi-factor authentication for the relevant maintainer accounts.

## Build and release origin

The [Windows build workflow](.github/workflows/windows-build.yml) builds from this repository on GitHub-hosted Windows runners, runs the automated checks, and uploads an unsigned executable as a GitHub Actions artifact. Workflow actions are pinned to commit hashes. The executable includes the project name and version in its Windows metadata.

No release is described as signed without verification of its signature. Third-party components retain their own licenses and identities; see [third-party notices](THIRD_PARTY.md).

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. See the [privacy policy](PRIVACY.md).

# Code signing policy

Simple Screen Recorder is applying to the SignPath Foundation open-source code signing program. Approval is pending; the current releases and GitHub Actions artifacts are unsigned. No SignPath signing certificate or production signing service is currently configured.

The requested service is free code signing provided by [SignPath.io](https://signpath.io), with a certificate from the [SignPath Foundation](https://signpath.org). This attribution will be updated to confirm active signing after approval and verification of a signed release.

## Project roles

- Author and reviewer: [B1GM4NT1NGS](https://github.com/B1GM4NT1NGS).
- Release signing approver: [B1GM4NT1NGS](https://github.com/B1GM4NT1NGS).

Changes from other contributors must be reviewed by the maintainer. Once signing is available, production signing requests will require the maintainer's manual approval. SignPath and GitHub maintainer accounts must use multi-factor authentication before production signing is enabled.

## Build and release origin

The [Windows build workflow](.github/workflows/windows-build.yml) builds from this repository on GitHub-hosted Windows runners, runs the automated checks, and uploads an unsigned executable as a GitHub Actions artifact. Workflow actions are pinned to commit hashes. The executable includes the project name and version in its Windows metadata.

After approval, the workflow will be connected to the assigned SignPath project and signing policy so the artifact's origin can be verified. Only verified signed output will be published as a signed release. Third-party components retain their own licenses and identities; see [third-party notices](THIRD_PARTY.md).

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. See the [privacy policy](PRIVACY.md).

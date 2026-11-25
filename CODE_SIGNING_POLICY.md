# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

**Status:** SpecAnalytiXBase has not applied to the SignPath Foundation yet; the releases are not signed (and Windows Smart App Control may block them). This page will say from which version the releases are signed.

## What is signed

- `SpecAnalytiXBase.exe` and the installer `Setup_for_SpecAnalytiXBase_ver_<version>.exe` of each stable release on the [Releases page](https://github.com/janpalacky-pixel/SpecAnalytiXBase/releases).
- They are built only by GitHub Actions ([`release-build.yml`](.github/workflows/release-build.yml)) from the source code in this repository, after the full test suite has passed. Nothing built on a personal computer is signed.
- Third-party libraries included in the program (Python, PyQt5, NumPy, SciPy, Matplotlib and others) are **not** signed by this project; they are included as their authors published them.
- The [nightly build](https://github.com/janpalacky-pixel/SpecAnalytiXBase/releases/tag/nightly) is not signed.

Every signing request is approved by hand by an approver (below), for each release.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [Jan Palacký](https://github.com/janpalacky-pixel) |
| Approvers | [Jan Palacký](https://github.com/janpalacky-pixel) |

Committers may change the source code; reviewers check every change from anyone else before it is merged; approvers approve each signing request. All of them use multi-factor authentication for GitHub and SignPath.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. In detail:

- **New version check:** at the start, the program asks GitHub (api.github.com) whether a newer release exists — one small HTTPS request; nothing about the user, the computer or the data is sent (only the program's version, in the User-Agent, as GitHub asks for one). It can be switched off: File › Settings and saved items… › "Check for a new version at the start". Help › Check for a new version… asks only when you click it.
- **Test datasets:** downloaded from this project's GitHub releases only when you ask for them.
- **Links** (help pages, the Releases page, e-mail) open in your browser only when you click them.

Your spectra, results and settings stay on your computer.

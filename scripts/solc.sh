# Sourced, not run: the pinned solc for this machine's architecture (proof-of-fix#152: the CI test runner is arm64).
# solc 0.8.37 (2026-09-10), static builds. Each sha256 is the one in binaries.soliditylang.org/<platform>/list.json,
# and the same as the release's assets on GitHub (solc-static-linux, solc-static-linux-arm). The compiler runs
# inside the Foundry image, which has both architectures, so a Mac or Linux host picks the Linux build of its own.
case "$(uname -m)" in
  x86_64 | amd64)
    SOLC_PLATFORM=linux-amd64
    SOLC_SHA256=5de843c2c93563cc66425c99a4fb13fdbf32b4c4ae07469480faaf126e14404a
    ;;
  aarch64 | arm64)
    SOLC_PLATFORM=linux-arm64
    SOLC_SHA256=717142f4275804e75c3d0bafd264db669da9cf411550c7c29cc68f634d17a9da
    ;;
  *)
    echo "no pinned solc for $(uname -m)" >&2
    exit 1
    ;;
esac
SOLC_BUILD="solc-$SOLC_PLATFORM-v0.8.37+commit.f401782d"
SOLC="contracts/.cache/$SOLC_BUILD"

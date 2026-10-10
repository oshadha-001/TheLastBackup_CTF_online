# Validation of the Vercel edition

Test date: 10 October 2026, Asia/Colombo. This is a new application in its own Python environment, separate from the original Docker project.

## Executed

**30 automated tests passed** using Python 3.12 and temporary SQLite databases. Tests include:

- Missing configuration and rejection of SQLite for online deployment.
- PostgreSQL driver selection and TLS configuration without opening a remote connection.
- Public pages, CSS delivery, private-response headers and health checks.
- Anonymous access controls, registration validation and password hashing.
- CSRF enforcement, POST-only logout and prerequisite checks.
- Full six-stage flow: archive flag, PNG extraction, evidence review, cipher decryption, compressed image download, image hash validation, deleted-file recovery and final verification.
- Case-sensitive flags, duplicate solves, all twelve hint purchases and final score of 955 with all hints (1,150 without hints).
- Player isolation and persisted state after creating a new app instance.
- Concurrent solve/hint updates and persisted rate limits.
- Organizer access, progress export, reset, disable and password-rotation session invalidation.
- Denial of private file URLs and path traversal; cookie fields cannot override database progress.
- Evidence download byte integrity and consistent Vercel configuration.

Browser checks ran against the real Waitress preview at http://localhost:8002:

- Created the local-only `preview_qa` account through the registration form.
- Submitted all six known test flags through the UI and observed each unlock.
- Selected the correct transaction/audit pair in the portal and submitted the final four-field answer.
- Observed six completed stages, 1,150 points and the case-closed message; inspected the saved database state to confirm persistence.
- Inspected desktop and mobile homepage screenshots and the mobile challenge board.
- Confirmed document width equalled viewport width (375 CSS pixels) on the homepage, challenge board, portal and evidence explorer. Tables and file contents use their own scroll containers.
- Signed the test account out and left the homepage open. The test account exists only in the local database; it is not in the upload files.

The forensic download is 66,423 bytes and expands to a 67,108,864-byte (64 MiB) FAT16 image. Its SHA-256 is `033a1ac3e953701aff29f22fb9ac8535ce5c6b4612f6aaeedcc3d232d22beabd`, matching the decrypted warning generated for this edition. Build/source syntax and upload-copy integrity checks also passed. A fresh copy of the 38 upload files independently rebuilt its private evidence and served the homepage and health route successfully through Flask test requests.

The initial Windows test run found a text-decoding error in one test helper; explicitly reading UTF-8 fixed it. The sandbox's temporary-directory permissions required a workspace temporary directory during the build/test run. A localhost permission-review timeout was resolved on the allowed retry; the preview now runs. These were development-environment issues, not hidden successful deployment claims.

## Still required online

- Link the user's new Vercel project and dedicated PostgreSQL provider.
- Set production environment variables and complete an actual Vercel build/deployment.
- Exercise the hosted PostgreSQL connection, schema creation, concurrent updates and cold starts in the deployed environment. PostgreSQL configuration was checked locally, but no live PostgreSQL credentials were supplied.
- Check HTTPS cookies, gated downloads, registration and a fresh six-stage journey at the deployed URL.
- Verify provider backups by restoring into a separate database.
- Perform an independent student blind solve and assess the changed Stage 6 learning outcome.

The browser test used known organizer answers to validate the UI. It is not an independent blind solve. Local success does not establish production load capacity or full compliance with the original four-VM assignment design. No GitHub repository or Vercel deployment was created automatically.

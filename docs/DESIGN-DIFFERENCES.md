# Vercel edition and original lab

This is a separate web adaptation, not a claim that the original four-VM architecture runs on Vercel.

| Feature | Original local Docker project | Vercel edition |
|---|---|---|
| Platform | CTFd, MariaDB and Redis | Custom Flask scoring and PostgreSQL |
| Deployment | Multiple Docker services, local ports | One Flask function with same-origin routes |
| Stage 1 | Static archive | Authenticated archive routes |
| Stage 2 | Lossless PNG | Lossless PNG with same-origin /portal clue |
| Stage 3 | Separate evidence portal | Integrated evidence portal and persisted review state |
| Stage 4 | Gated ciphertext and memo | Gated downloads after Stage 3 solve and review |
| Stage 5 | Organizer-issued raw image | Gated gzip download; decompress to 64 MiB FAT16 |
| Stage 6 | Real analyst SSH account, POSIX filesystem and separate verifier | Browser explorer of preserved Linux files, pointer and hashes; integrated verifier |
| Handover | Some manual organizer release | Server-enforced prerequisite checks for downloads/routes |
| State | Docker volumes and local verifier SQLite | Hosted PostgreSQL; SQLite only for local preview/tests |
| Reset | Container restart, snapshots and account state | Per-player progress reset; immutable evidence rebuild |
| UI | CTFd custom theme and separate sites | New consistent pages in one app |

All six story stages, six static flag values, point values and hint costs remain. Stage 6 still requires comparing the Stage 5 trusted manifest hash with candidate manifests, verifying route bytes and identifying release/route/service/event. It no longer demonstrates live SSH, Unix permissions, an actual symlink operation or privilege escalation. The browser explicitly labels this difference; it never executes shell commands.

Online handover text in the image and the portal link inside the PNG change, so their bytes differ from the original lab. The build recomputes the image hash and dependent encrypted warning. Never mix original image/cipher files with this edition's downloads.

For Assignment 02, explain these changes and their effect on learning outcomes and obtain any needed lecturer acceptance. This adaptation is not evidence that the original isolated VM/container requirement or Linux practical has been demonstrated. Use the original Docker environment when those are required. Independent difficulty assessment, a student blind solve and the group's actual individual script/contribution evidence remain the group's work.

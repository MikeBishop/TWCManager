Make the 1.3.4 Docker image and sample config start

Two bugs stop a fresh 1.3.4 install from starting. Both are already fixed on `main`; this backports them to `release/1.3.4`.

## The Docker image never installs TWCManager

The Makefile's `docker` target is `deps build_pkg config tesla-control`. `build_pkg` builds a wheel and never installs it.

- **Symptom:** the published `v1.3.4` and `v1.3.3.post1` images restart in a loop with `/usr/bin/python3: No module named TWCManager`. I reproduced it by pulling both on arm64. `latest` (built from `main`) imports fine.
- **Fix:** the target now runs `install_pkg`, as on main since 02428483.

## The sample config doesn't parse

`etc/twcmanager/config.json` is missing the comma after the `HomeAssistant` block. TWCManager's loader strips the comments and then fails with `yaml.parser.ParserError … expected ',' or '}'` at `"TeslaMate": {`.

- **Who it hits:** every fresh install that starts from the sample, Docker or not. The Docker entrypoint copies it on first start.
- **Fix:** the comma is added. Main fixed the same block in c8ce9fd0.

## Tested

The test used the published `v1.3.4` image with the fixed sample config. Inside the image I ran `install_pkg`'s steps, `pip3 install -r requirements.txt` then `pip3 install .`, because the image's Makefile can't be changed in place. Results:
- It starts with the Dummy interface and the web UI answers.
- TeslaBLE finds `tesla-control`.
- Through `nsenter --net=/rootns/net`, `tesla-control` reaches the host's Bluetooth adapter.

## Release

Rebuilding from the `v1.3.4` tag reproduces the bug, because the tag carries the old Makefile. A working image needs **v1.3.4.post1** tagged from this branch. With #PR_TAGS, that release also updates `v1.3.4` and `v1.3`, so everyone pinned to `v1.3.4`, including `docker-compose-v1.3.4.yml` on main, gets it on their next pull.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

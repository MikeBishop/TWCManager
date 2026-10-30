Fix the Docker image's BLE and the docs' compose downloads

Two problems keep Docker users from a working install. I tested each on an arm64 host with Docker and Bluetooth.

## BLE is off in the image

`make docker` installs `tesla-control` in `/home/twcmanager/gobin`. The container runs as root, so TeslaBLE's default `~/gobin/tesla-control` is `/root/gobin/tesla-control`. The binary isn't on `PATH` either, so the image logs `tesla-control binary not found - BLE module will be disabled` unless the user sets `teslaControlPath`. The `/home/twcmanager/gobin` fallback that used to cover this was removed in 3278ad2c.

- The Dockerfile now puts `/home/twcmanager/gobin` on `PATH`, so TeslaBLE's existing `shutil.which` lookup finds the binary. The code keeps no hard-coded path.
- Tested: an image built from `latest` with only this `ENV` line logs `tesla-control binary found at: /home/twcmanager/gobin/tesla-control`. Inside it, `nsenter --net=/rootns/net -- tesla-control -ble …` reaches the host's adapter. It times out looking for a made-up VIN, which shows the adapter answered.

## The compose file the docs download doesn't exist

`docs/Software_Docker.md` tells users to `curl` `contrib/docker/docker-compose-v1.3.4.yml`, for both a new stable install and an upgrade. That file was never added, so `curl` saves GitHub's 404 page as `docker-compose.yml`.

- **New `docker-compose-v1.4.0.yml`:** `docker-compose.yml` with the image pinned to `twcmanager/twcmanager:v1.4.0`. The docs' two `curl` lines and the "latest Stable version" text now point to v1.4.0.
- **New `docker-compose-v1.3.4.yml`:** the 1.3.4 docs download this file from `main`. It is 1.3.4's own `docker-compose.yml`, pinned to `v1.3.4`.

## Timing

`docker-compose-v1.4.0.yml` pulls `v1.4.0`, which exists only once 1.4.0 is tagged, so merge this with the release. The published `v1.3.4` image can't start; #PR_1_3_4 fixes it on `release/1.3.4`, and #PR_TAGS makes a `v1.3.4.post1` also update `v1.3.4`, which this file pins.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

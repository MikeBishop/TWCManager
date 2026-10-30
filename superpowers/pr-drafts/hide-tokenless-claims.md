List a cloud API on the Vehicles page only while its token is held

On a Fleet-only install, the Vehicles page listed each car with "Owner API: read-only (no Owner API token)". Without its token the Owner API can't read the car either, so the line was misleading.

When TWCManager lists the cars on a Tesla account, it claims each one for both the Owner API and the Fleet API, so that a token added later starts managing the car without listing the account again. Those claims stay. The page now skips a cloud API's line until that API's token is held, and it shows up as soon as a token is added. The same applies the other way: an Owner-only install no longer shows a Fleet API line.

## Evidence

- **Unit tests:** 2,585 passed, 1 xfailed. A new test covers each direction (Owner token only, Fleet token only).
- **Changelog:** none. The Vehicles page is new in 1.4.1, so no release has shown this line.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

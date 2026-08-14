# Releasing to npm (trusted publishing, no token, no 2FA prompt)

Publishing runs through `.github/workflows/release.yml` using npm
**trusted publishing (OIDC)**: the GitHub Actions run proves its identity to
the npm registry cryptographically. No npm token is stored anywhere, and no
2FA code is needed at publish time - the 2FA-bypass-token deprecation
(January 2027) does not affect this flow.

## One-time setup (needs an npmjs.com web login once)

1. Log in at <https://www.npmjs.com> (this is the only step that ever needs
   the 2FA phone).
2. Go to the package: `codesys-mcp-sp21-plus` > **Settings**.
3. Under **Trusted publisher**, choose **GitHub Actions** and enter:
   - Organization or user: `phobicdotno`
   - Repository: `Codesys-MCP-SP21-plus`
   - Workflow filename: `release.yml`
   - Environment: leave empty
4. Save. Done - nothing on the machine or in the repo holds a secret.

## Releasing a version

```powershell
# 1. bump "version" in package.json, update CHANGELOG, commit and push
# 2. tag it (tag MUST match package.json version - the workflow verifies):
git tag v0.15.3
git push origin v0.15.3
```

The workflow then: installs deps, checks the tag against `package.json`,
and runs `npm publish` - which triggers `prepublishOnly` (full build + test
suite) on the runner before anything goes live. A failed build or test
aborts the publish.

## Notes

- Local `npm publish` from a terminal still works as a fallback (interactive
  2FA with the phone).
- The dev machine's global install is a symlink to the local clone
  (`npm install -g .`), so it does not depend on the registry at all -
  publishing is for OTHER machines that `npm install -g codesys-mcp-sp21-plus`.
- Trusted publishing requires npm >= 11.5.1 on the runner; the workflow
  upgrades npm explicitly before publishing.

# Gentoo packaging

`net-misc/psssh/` is an ebuild for Pascal Simple SSH itself.
`dev-python/pyte/` is a fallback ebuild for its `pyte` dependency, **only
needed if `dev-python/pyte` isn't already available** in the main tree or in
GURU - check with `emerge -s pyte` (with GURU enabled) before adding it.

These were written without access to a real Portage installation, so treat
them as a solid first draft, not a verified/tested package. Before opening a
PR against [GURU](https://github.com/gentoo/guru), please:

1. **Verify the dependency atoms.** `dev-python/PyQt6`'s exact USE flags
   (`gui`, `network`, `widgets`) and slot, and whether `dev-python/pyte` and
   `dev-python/keyring` are already packaged, should be checked against the
   current tree - package layouts do shift over time.
2. **Verify the archive layout.** `SRC_URI` assumes GitHub's tag archive for
   `v${PV}` extracts to a `psssh-${PV}` directory (GitHub strips the leading
   "v"). Confirm once with:
   ```
   wget -qO- https://github.com/pascalbrax/psssh/archive/refs/tags/v1.1.2.tar.gz | tar -tz | head -1
   ```
3. **Generate the Manifest** (requires real Portage tools, which aren't
   available in the environment these were written in):
   ```
   cd net-misc/psssh
   ebuild psssh-1.1.2.ebuild manifest
   ```
4. **Lint and test-build:**
   ```
   pkgcheck scan net-misc/psssh
   emerge --pretend --verbose net-misc/psssh
   ```
5. Confirm the app actually launches (`psssh`), and that SFTP "Edit" opens
   files via `xdg-open` correctly on your desktop environment.

`KEYWORDS="~amd64"` is set for a first submission (unstable/testing); that's
the normal starting point for a new package.

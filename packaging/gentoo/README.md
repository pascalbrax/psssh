# Gentoo packaging

`net-misc/psssh/` is an ebuild for Pascal Simple SSH itself. Its `pyte`
dependency is already packaged (`dev-python/pyte`, confirmed via `emerge -p`),
so no fallback ebuild is needed for it.

This was written without access to a real Portage installation, so treat
them as a solid first draft, not a verified/tested package. `pkgcheck scan`
has since been run against a real tree and the findings applied (renamed
`dev-python/PyQt6` -> `dev-python/pyqt6`, dropped the empty `IUSE=""`, added
the missing `desktop` eclass inherit for `doicon`/`domenu`, and narrowed
`PYTHON_COMPAT` to the two targets the `23.0` profile actually offers). Before
opening a PR against [GURU](https://github.com/gentoo/guru), please still:

1. Re-run `pkgcheck scan net-misc/psssh` and confirm it's clean.
2. **Verify the archive layout.** `SRC_URI` assumes GitHub's tag archive for
   `v${PV}` extracts to a `psssh-${PV}` directory (GitHub strips the leading
   "v"). Confirm once with:
   ```
   wget -qO- https://github.com/pascalbrax/psssh/archive/refs/tags/v1.1.3.tar.gz | tar -tz | head -1
   ```
3. **Generate the Manifest:**
   ```
   cd net-misc/psssh
   ebuild psssh-1.1.3.ebuild manifest
   ```
4. **Test-build:**
   ```
   emerge --pretend --verbose net-misc/psssh
   ```
5. Confirm the app actually launches (`psssh`), and that SFTP "Edit" opens
   files via `xdg-open` correctly on your desktop environment.

`KEYWORDS="~amd64"` is set for a first submission (unstable/testing); that's
the normal starting point for a new package.

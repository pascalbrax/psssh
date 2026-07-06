# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# NOTE: only add this if dev-python/pyte isn't already present in the main
# tree or GURU - check first with `emerge -s pyte` / the GURU search page.
# LICENSE below is set from upstream's own LICENSE file at the time of
# writing; re-verify it against the actual release tarball before submitting.

EAPI=8

DISTUTILS_USE_PEP517=setuptools
PYTHON_COMPAT=( python3_{10..13} )

inherit distutils-r1 pypi

DESCRIPTION="Simple VTXXX-compatible terminal emulator library for Python"
HOMEPAGE="
	https://github.com/selectel/pyte/
	https://pypi.org/project/pyte/
"

LICENSE="LGPL-3+"
SLOT="0"
KEYWORDS="~amd64"

RDEPEND="dev-python/wcwidth[${PYTHON_USEDEP}]"
BDEPEND="
	$(python_gen_cond_dep '
		dev-python/setuptools[${PYTHON_USEDEP}]
	')
"

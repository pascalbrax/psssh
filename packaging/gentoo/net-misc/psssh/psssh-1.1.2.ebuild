# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

DISTUTILS_USE_PEP517=setuptools
DISTUTILS_SINGLE_IMPL=1
PYTHON_COMPAT=( python3_12 python3_13 )

inherit distutils-r1 desktop xdg

DESCRIPTION="Qt SSH/SFTP client with true-color terminal emulation (Pascal Simple SSH)"
HOMEPAGE="https://github.com/pascalbrax/psssh"
# GitHub strips the leading "v" from a version-shaped tag when naming the
# archive's top-level directory, so this extracts to ${PN}-${PV} - confirm
# with `wget -q -O- "${SRC_URI}" | tar -tz | head -1` before first upload.
SRC_URI="https://github.com/pascalbrax/psssh/archive/refs/tags/v${PV}.tar.gz -> ${P}.tar.gz"
S="${WORKDIR}/${PN}-${PV}"

LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64"

REQUIRED_USE="${PYTHON_REQUIRED_USE}"

RDEPEND="
	$(python_gen_cond_dep '
		dev-python/pyqt6[gui,network,widgets,${PYTHON_USEDEP}]
		dev-python/paramiko[${PYTHON_USEDEP}]
		dev-python/pyte[${PYTHON_USEDEP}]
		dev-python/keyring[${PYTHON_USEDEP}]
	')
"
DEPEND="${RDEPEND}"
BDEPEND="
	$(python_gen_cond_dep '
		dev-python/setuptools[${PYTHON_USEDEP}]
	')
"

# No upstream test suite is shipped yet, so this doesn't call
# distutils_enable_tests.

src_install() {
	distutils-r1_src_install
	doicon -s 256 "${S}"/psssh/assets/icon.png
	domenu "${S}"/packaging/linux/psssh.desktop
}

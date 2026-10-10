#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"

if ! command -v uv >/dev/null 2>&1; then
	brew install uv
fi

if ! command -v pi >/dev/null 2>&1; then
	curl -fsSL https://pi.dev/install.sh | sh
fi

if [[ ! -x .venv/bin/python ]]; then
	uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt

symbol_dir=""
for candidate in \
	"/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols" \
	"/usr/share/kicad/symbols"; do
	if [[ -d "$candidate" ]]; then
		symbol_dir="$candidate"
		break
	fi
done

kicad_bin=""
for candidate in \
	"/Applications/KiCad/KiCad.app/Contents/MacOS" \
	"/usr/bin"; do
	if [[ -x "$candidate/kicad-cli" ]]; then
		kicad_bin="$candidate"
		break
	fi
done

activate="$root/.venv/bin/activate"
marker="# pcb-agent local tools"
if [[ -n "$symbol_dir" || -n "$kicad_bin" ]]; then
	grep -q "$marker" "$activate" || cat >>"$activate" <<EOF

$marker
EOF
	if [[ -n "$symbol_dir" ]] && ! grep -q 'KICAD_SYMBOL_DIR=' "$activate"; then
		printf 'export KICAD_SYMBOL_DIR=%q\n' "$symbol_dir" >>"$activate"
	fi
	if [[ -n "$symbol_dir" && -n "$kicad_bin" ]]; then
		kicad_major="$("$kicad_bin/kicad-cli" version | head -n 1 | cut -d. -f1)"
		kicad_var="KICAD${kicad_major}_SYMBOL_DIR"
		export "$kicad_var=$symbol_dir"
		if ! grep -q "${kicad_var}=" "$activate"; then
			printf 'export %s=%q\n' "$kicad_var" "$symbol_dir" >>"$activate"
		fi
	fi
	if [[ -n "$symbol_dir" ]]; then
		export KICAD_SYMBOL_DIR="$symbol_dir"
	fi
	if [[ -n "$kicad_bin" ]] && ! grep -Fq "$kicad_bin" "$activate"; then
		printf 'export PATH=%q:"$PATH"\n' "$kicad_bin" >>"$activate"
	fi
fi

freerouting_version="2.5.0"
case "$(uname -s)-$(uname -m)" in
	Darwin-arm64)
		freerouting_asset="freerouting-cli-${freerouting_version}-macos-arm64.tar.gz"
		freerouting_sha="515eded3c615c13eaa336d5044f5df042bdb8d67181aac30fd0f7a457f1f93a7"
		;;
	Darwin-x86_64)
		freerouting_asset="freerouting-cli-${freerouting_version}-macos-x64.tar.gz"
		freerouting_sha="7a0d039902469d21766f953da01c463479e374e190797ce4a8b0bbaf2fe1a990"
		;;
	Linux-aarch64 | Linux-arm64)
		freerouting_asset="freerouting-cli-${freerouting_version}-linux-arm64.tar.gz"
		freerouting_sha="9acbfd88c62d40012e7b591c934b340e449486dbe8aae3387943a84119f77171"
		;;
	Linux-x86_64)
		freerouting_asset="freerouting-cli-${freerouting_version}-linux-x64.tar.gz"
		freerouting_sha="64a957a9ef2a2fbde6ab2001bb32800f5ba34f9fd15575e363512934b870d63a"
		;;
	*)
		echo "No Freerouting CLI build for $(uname -s)-$(uname -m)" >&2
		exit 1
		;;
esac

freerouting_dir="$root/.tools/freerouting"
freerouting_bin="$freerouting_dir/freerouting-cli"
if [[ ! -x "$freerouting_bin" ]] || [[ "$(cat "$freerouting_dir/VERSION" 2>/dev/null || true)" != "$freerouting_version" ]]; then
	freerouting_tmp="$(mktemp -d)"
	curl -fL --retry 3 -o "$freerouting_tmp/$freerouting_asset" \
		"https://github.com/freerouting/freerouting/releases/download/v${freerouting_version}/$freerouting_asset"
	echo "$freerouting_sha  $freerouting_tmp/$freerouting_asset" | shasum -a 256 -c -
	mkdir -p "$freerouting_dir"
	tar -xzf "$freerouting_tmp/$freerouting_asset" -C "$freerouting_dir"
	chmod +x "$freerouting_bin"
	printf '%s\n' "$freerouting_version" >"$freerouting_dir/VERSION"
	rm -rf "$freerouting_tmp"
fi
if ! grep -Fq "$freerouting_dir" "$activate"; then
	printf 'export PATH=%q:"$PATH"\n' "$freerouting_dir" >>"$activate"
fi

kicad_python=""
for candidate in \
	"/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3" \
	"/usr/bin/python3"; do
	if [[ -x "$candidate" ]] && "$candidate" -c "import pcbnew" >/dev/null 2>&1; then
		kicad_python="$candidate"
		break
	fi
done
if [[ -n "$kicad_python" ]]; then
	if ! grep -q 'KICAD_PYTHON=' "$activate"; then
		printf 'export KICAD_PYTHON=%q\n' "$kicad_python" >>"$activate"
	fi
else
	echo "No Python with KiCad's pcbnew module. /layout cannot build boards until KiCad is installed." >&2
fi

if [[ ! -f .tools/jlcpcb/economic-parts.csv ]]; then
	.venv/bin/python skills/parts/fetch_catalog.py
fi

.venv/bin/python -c "import skidl; print('skidl', skidl.__version__)"
.venv/bin/kicad-mcp --help >/dev/null
"$freerouting_bin" -h >/dev/null
echo "Python tools are in .venv. Freerouting ${freerouting_version} is in .tools/freerouting."
echo "Start the agent with: source .venv/bin/activate && pi"

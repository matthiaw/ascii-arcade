# Copyright (c) 2026 Matthias Wegner
# SPDX-License-Identifier: MIT (see the LICENSE file)
#
# Homebrew formula. The release workflow (.github/workflows/release.yml) updates the tag below.
#   brew tap matthiaw/arcade https://github.com/matthiaw/ascii-arcade
#   brew trust --formula matthiaw/arcade/ascii-arcade
#   brew install ascii-arcade
class AsciiArcade < Formula
  desc "Thirty games for the terminal, drawn in truecolor half-block pixels"
  homepage "https://github.com/matthiaw/ascii-arcade"
  url "https://github.com/matthiaw/ascii-arcade.git", tag: "v1.15.0"
  license "MIT"
  head "https://github.com/matthiaw/ascii-arcade.git", branch: "main"

  depends_on "python@3.14"

  def install
    libexec.install Dir["*.py"], "VERSION"
    python = Formula["python@3.14"].opt_bin/"python3.14"
    (bin/"arcade").write <<~SH
      #!/bin/sh
      exec "#{python}" "#{libexec}/arcade.py" "$@"
    SH
    doc.install "README.md", "LICENSE"
  end

  def caveats
    <<~EOS
      Start the menu with:   arcade
      Start one game with:   arcade stackfall   (arcade --list shows all)
      Best in WezTerm (brew install --cask wezterm); iTerm2, kitty and Ghostty work too.
      In macOS Terminal.app press G in the menu for smart or solid pixels.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/arcade --version")
    assert_match "stackfall", shell_output("#{bin}/arcade --list")
  end
end

#!/usr/bin/env bash

# Install Gesahni zsh configuration
echo "🔧 Installing Gesahni zsh configuration..."

# Check if configuration already exists
if grep -q "GESAHNI DEVELOPMENT ALIASES" ~/.zshrc; then
    echo "⚠️  Gesahni configuration already exists in ~/.zshrc"
    echo "   Skipping installation..."
    exit 0
fi

# Add configuration to .zshrc
echo "" >> ~/.zshrc
echo "# =============================================================================" >> ~/.zshrc
echo "# GESAHNI DEVELOPMENT ALIASES AND FUNCTIONS" >> ~/.zshrc
echo "# =============================================================================" >> ~/.zshrc

# Add the configuration
cat gesahni-zshrc-config.sh >> ~/.zshrc

echo "✅ Gesahni configuration added to ~/.zshrc"
echo ""
echo "🔄 To activate the new configuration, run:"
echo "   source ~/.zshrc"
echo ""
echo "💡 Or restart your terminal"
echo ""
echo "🚀 Then you can use commands like:"
echo "   gesahni-start  (or gs) - Start both backend and frontend"
echo "   gesahni-stop   (or gx) - Stop all processes"
echo "   gesahni-back   (or gb) - Start only backend"
echo "   gesahni-front  (or gf) - Start only frontend"
echo "   gesahni-help   (or gh) - Show all commands"

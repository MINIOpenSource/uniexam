#!/bin/bash

# Check for Python 3.8+
python3 -c 'import sys; sys.exit(not (sys.version_info.major == 3 and sys.version_info.minor >= 8))'
if [ $? -ne 0 ]; then
    echo "Python 3.8 or higher is required. Please install it and try again."
    exit 1
fi
echo "Python 3.8+ found."

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        exit 1
    fi
else
    echo "Virtual environment .venv already exists."
fi

# Activate virtual environment (hint for user)
echo "To activate the virtual environment, run: source .venv/bin/activate"

# Install dependencies
echo "Installing dependencies from pyproject.toml (including dev and docs extras)..."
# Ensure pip is called from the virtual environment if script is run directly
# or if the user hasn't activated it yet.
if [ -f ".venv/bin/pip" ]; then
    .venv/bin/pip install .[dev,docs]
else
    echo "Pip not found in .venv/bin. Please ensure the virtual environment was created correctly."
    exit 1
fi

if [ $? -ne 0 ]; then
    echo "Failed to install dependencies."
    exit 1
fi
echo "Dependencies installed successfully."

# Prompt for .env file
echo ""
echo "---------------------------------------------------------------------"
echo "Setup almost complete!"
echo "Please create a .env file in the project root if you haven't already."
echo "You can copy .env.example (if it exists) or create a new one."
echo "Example .env content:"
echo "APP_DOMAIN=\"localhost\""
echo "FRONTEND_DOMAIN=\"http://localhost:3000\""
echo "LISTENING_PORT=\"17071\""
echo "INITIAL_ADMIN_PASSWORD=\"your_strong_password_here\""
echo "---------------------------------------------------------------------"


# Prompt for running the application
echo ""
echo "To run the application, first activate the virtual environment (if not already):"
echo "source .venv/bin/activate"
echo ""
echo "Then run:"
echo "python run.py"
echo "---------------------------------------------------------------------"

# Make the script executable (this chmod is for the file itself,
# the user running this script might need to do it once before the first run)
# chmod +x install.sh # This line in the script itself doesn't make sense as it's run by an interpreter.
                      # The file needs to be chmod'ed from outside.

echo "Installation script finished."

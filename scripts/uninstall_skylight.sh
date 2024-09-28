#!/bin/bash

# Variables
SERVICE="/etc/systemd/system/skylight.service"
DEFAULTS_FILE="/etc/default/skylight"
INSTALL_PATH="/root/skylight"         # Path to the Skylight installation
PYTHON_ENV_PATH="/root/skylight-env"  # Path to the Python virtual environment

# Stop the Skylight service if it's running
echo "[UNINSTALL] Stopping Skylight service..."
sudo systemctl stop skylight.service

# Disable the service to prevent it from starting at boot
echo "[UNINSTALL] Disabling Skylight service..."
sudo systemctl disable skylight.service

# Remove the systemd service file
if [ -f "$SERVICE" ]; then
    echo "[UNINSTALL] Removing Skylight service file..."
    sudo rm "$SERVICE"
else
    echo "[UNINSTALL] Skylight service file not found, skipping."
fi

# Remove the defaults configuration file
if [ -f "$DEFAULTS_FILE" ]; then
    echo "[UNINSTALL] Removing /etc/default/skylight file..."
    sudo rm "$DEFAULTS_FILE"
else
    echo "[UNINSTALL] /etc/default/skylight file not found, skipping."
fi

# Reload systemd to apply changes
echo "[UNINSTALL] Reloading systemd daemon..."
sudo systemctl daemon-reload

# Check if Skylight installation directory exists and remove it
if [ -d "$INSTALL_PATH" ]; then
    echo "[UNINSTALL] Removing Skylight installation directory..."
    sudo rm -rf "$INSTALL_PATH"
else
    echo "[UNINSTALL] Skylight installation directory not found, skipping."
fi

# Check if Python virtual environment exists and remove it
if [ -d "$PYTHON_ENV_PATH" ]; then
    echo "[UNINSTALL] Removing Python virtual environment..."
    sudo rm -rf "$PYTHON_ENV_PATH"
else
    echo "[UNINSTALL] Python virtual environment not found, skipping."
fi

echo "[UNINSTALL] Skylight service and related files removed successfully."

#!/bin/bash

# Variables
REPO="deltamaker/skylight.git"            # Replace with your Skylight repository URL
SERVICE="/etc/systemd/system/skylight.service"
INSTALL_PATH="${HOME}/skylight"          # Directory where Skylight will be installed
SCRIPTS_DIR="${INSTALL_PATH}/scripts"    # Path to the scripts directory
PYTHONDIR="${HOME}/skylight-env"         # Python virtual environment directory
REQUIREMENTS="${SCRIPTS_DIR}/requirements.txt"   # Path to requirements.txt in scripts directory
DEFAULTS_FILE="/etc/default/skylight"    # Path to the /etc/default/skylight file
CONFIG_PATH="${SCRIPTS_DIR}/config.yaml" # Path to config.yaml in scripts directory

# Force script to exit if an error occurs
set -e

# Set locale to avoid issues
export LC_ALL=C

# Function to check for root user
verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "[ERROR] This script must not be run as root!"
        exit -1
    fi
}

# Step 1: Preflight checks
preflight_checks() {
    if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F 'skylight.service')" ]; then
        echo "[PRE-CHECK] Skylight service found!"
    else
        echo "[INFO] Skylight service not found, proceeding with installation."
    fi
}

# Step 2: Download or update the repository
check_download() {
    if [ ! -d "${INSTALL_PATH}" ]; then
        echo "[DOWNLOAD] Cloning repository..."
        git clone https://github.com/${REPO} "${INSTALL_PATH}"
    else
        echo "[DOWNLOAD] Repository already found, pulling latest changes..."
        git -C "${INSTALL_PATH}" pull
    fi
}

# Step 3: Create Python virtual environment and install dependencies
create_virtualenv() {
    echo "[VIRTUALENV] Setting up Python environment..."
    
    # Create virtualenv if it doesn't already exist
    if [ ! -d "${PYTHONDIR}" ]; then
        virtualenv -p python3 "${PYTHONDIR}"
    fi

    # Install/update dependencies from requirements.txt
    echo "[VIRTUALENV] Installing dependencies from ${REQUIREMENTS}..."
    ${PYTHONDIR}/bin/pip install -r "${REQUIREMENTS}"
}

# Step 4: Create /etc/default/skylight file dynamically
create_defaults_file() {
    echo "[CONFIG] Creating /etc/default/skylight file..."

    sudo /bin/sh -c "cat > ${DEFAULTS_FILE}" <<EOF
# Configuration for Skylight Daemon

SKYLIGHT_USER=root
SKYLIGHT_EXEC=${PYTHONDIR}/bin/python
SKYLIGHT_ARGS="${INSTALL_PATH}/skylight_main.py --config ${CONFIG_PATH}"

EOF

    echo "[CONFIG] /etc/default/skylight file created!"
}

# Step 5: Create and install systemd service
install_service() {
    echo "[INSTALL] Installing Skylight service..."

    # Reference the skylight.service file from the scripts directory
    S=$(<"${SCRIPTS_DIR}/skylight.service")

    S=$(sed "s|TC_USER|$(whoami)|g" <<< "$S")

    echo "$S" | sudo tee "${SERVICE}" > /dev/null

    sudo systemctl daemon-reload
    sudo systemctl enable skylight.service
    echo "[INSTALL] Skylight service installed and enabled!"
}

# Step 6: Start the Skylight service
start_service() {
    echo "[SERVICE] Starting Skylight service..."
    sudo systemctl start skylight.service
    echo "[SERVICE] Skylight service started!"
}

# Helper function for reporting status
report_status() {
    echo -e "\n###### $1"
}

# Start the installation process
verify_ready
preflight_checks
check_download
create_virtualenv
create_defaults_file
install_service
start_service
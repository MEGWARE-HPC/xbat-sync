#!/bin/bash

# ANSI color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Define the installation directory for the xbat-sync script
SYNC_DIR="/usr/local/sbin/xbat-sync"

# Function to display help information
help_menu() {
    echo "=========================="
    echo "XBAT-SYNC Setup Help Menu"
    echo "=========================="
    echo -e "${YELLOW}Usage: ${GREEN}$0 <command> [options]${NC}"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo -e "  ${GREEN}env${NC}          Generate .env file template"
    echo -e "  ${GREEN}install${NC}      Install the xbat-sync script"
    echo -e "  ${GREEN}uninstall${NC}    Uninstall the xbat-sync script"
    echo -e "  ${GREEN}help${NC}         Display this help message"
    echo ""
    echo -e "${YELLOW}Options for 'env':${NC}"
    echo -e "  ${GREEN}[directory]${NC}  Specify the directory to generate .env file (default: current directory)"
    echo -e "    Examples:"
    echo -e "      $0 env src   # Generates .env in ./src"
    echo -e "      $0 env       # Generates .env in current directory"
}

# Function to generate .env file with default values if it doesn't exist
generate_env() {
    # Set default destination directory to current directory
    ENV_DIR="."

    # Check if a second argument is provided for the directory
    if [ "$#" -eq 2 ]; then
        ENV_DIR="$2"
    fi

    # Validate the specified directory
    if [ "$ENV_DIR" != "." ] && [ "$ENV_DIR" != "src" ]; then
        echo -e "${RED}Error: ${GREEN}.env${NC} file should only be generated in '.' or 'src' directories."
        exit 1
    fi

    # Check if .env file already exists in the specified subdirectory
    if [ -f "./.env" ]; then
        EXISTING_FILE="./.env"
    elif [ -f "./src/.env" ]; then
        EXISTING_FILE="./src/.env"
    else
        EXISTING_FILE=""
    fi

    if [ -n "$EXISTING_FILE" ]; then
        echo -e "${RED}Warning: ${GREEN}.env${NC} file already exists in ${GREEN}$(dirname "$EXISTING_FILE") ${NC}directory. Skipping generation..."
    else
        # Prompt user for input environment parameters
        read -p "Please enter the username of the source XBAT server (default admin): " XBAT_SOURCE_USER
        XBAT_SOURCE_USER=${XBAT_SOURCE_USER:-admin}
        
        read -sp "Please enter the password of the source XBAT server: " XBAT_SOURCE_PASSWORD
        echo
        
        read -p "Please enter the address of the source XBAT server (default localhost:7000): " XBAT_SOURCE_ADDRESS
        XBAT_SOURCE_ADDRESS=${XBAT_SOURCE_ADDRESS:-localhost:7000}
        
        read -p "Please enter the username of the destination XBAT server (default admin): " XBAT_DEST_USER
        XBAT_DEST_USER=${XBAT_DEST_USER:-admin}
        
        read -sp "Please enter the password of the destination XBAT server: " XBAT_DEST_PASSWORD
        echo
        
        read -p "Please enter the address of the destination XBAT server (default localhost:7000): " XBAT_DEST_ADDRESS
        XBAT_DEST_ADDRESS=${XBAT_DEST_ADDRESS:-localhost:7000}

        read -p "Please set the filter keys separated by commas (e.g., issuer,state): " FILTER_KEYS
        read -p "Please set the corresponding filter values separated by commas (e.g., demo,done): " FILTER_VALUES
        
        read -p "Please set whether to check the existence of metric data during synchronization (true/false): " CHECK_METRIC_DB
        CHECK_METRIC_DB=${CHECK_METRIC_DB:-true}

        read -p "Please set the minimum synchronization runNr or use default: " MIN_RUN_NR
        MIN_RUN_NR=${MIN_RUN_NR:-0}
        
        read -p "Please set the number of simultaneous tasks or use default: " BATCH_SIZE
        BATCH_SIZE=${BATCH_SIZE:-1}
        
        read -p "Please set whether to load the last synchronized runNrs (true/false): " LOAD_LAST_SYNC
        LOAD_LAST_SYNC=${LOAD_LAST_SYNC:-false}

        # Define the default .env file content
        cat <<EOF >"$ENV_DIR/.env"
XBAT_SOURCE_USER=$XBAT_SOURCE_USER
XBAT_SOURCE_PASSWORD=$XBAT_SOURCE_PASSWORD
XBAT_SOURCE_ADDRESS=$XBAT_SOURCE_ADDRESS
XBAT_DEST_USER=$XBAT_DEST_USER
XBAT_DEST_PASSWORD=$XBAT_DEST_PASSWORD
XBAT_DEST_ADDRESS=$XBAT_DEST_ADDRESS
FILTER_KEYS=$FILTER_KEYS
FILTER_VALUES=$FILTER_VALUES
CHECK_METRIC_DB=$CHECK_METRIC_DB
MIN_RUN_NR=$MIN_RUN_NR
BATCH_SIZE=$BATCH_SIZE
LOAD_LAST_SYNC=$LOAD_LAST_SYNC
EOF

        echo -e "${YELLOW}Info: ${GREEN}.env${NC} file generated with user input values in ${GREEN}$ENV_DIR/.env${NC}. Please verify the parameters for the ${YELLOW}servers${NC}."
    fi

}

# Function to install the xbat-sync script
install() {
    echo "Installing xbat-sync..."
    uninstall
    # Define the source directory
    SRC_DIR="./src"

    # Determine the location of .env file
    if [ -f "$SRC_DIR/.env" ]; then
        ENV_FILE="$SRC_DIR/.env"
    elif [ -f "./.env" ]; then
        ENV_FILE="./.env"
    else
        echo -e "${RED}Error: ${GREEN}.env${NC} file not found in either ./src or current path."
        exit 1
    fi

    # Create the xbat-sync directory if it doesn't exist
    mkdir -p "$SYNC_DIR"

    # Copy files from src to sync path
    cp "$SRC_DIR/run.py" "$SYNC_DIR/"
    cp "$SRC_DIR/requirements.txt" "$SYNC_DIR/"
    cp "$ENV_FILE" "$SYNC_DIR/"

    # Navigate to the xbat-sync directory
    cd "$SYNC_DIR" || exit

    # Create a virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    # Activate the virtual environment and install dependencies
    source venv/bin/activate
    pip3 install -r requirements.txt
    deactivate

    # Add a cronjob to run the script every hour using the virtual environment's Python interpreter
    (crontab -l 2>/dev/null; echo "0 * * * * $SYNC_DIR/venv/bin/python3 $SYNC_DIR/run.py") | crontab -

    echo "Setup complete. The xbat-sync script will run every hour."
}

# Function to uninstall the sync script
uninstall() {
    echo "Uninstalling xbat-sync script..."
    # Remove the cronjob that runs run.py every hour
    (crontab -l 2>/dev/null | grep -v "$SYNC_DIR/venv/bin/python3 $SYNC_DIR/run.py") | crontab -

    # Delete the xbat-sync directory
    rm -rf "$SYNC_DIR"

    echo "Uninstallation complete."
}

# Check if an argument is provided and call the appropriate function
case "$1" in
    env)
        generate_env "$@"
        ;;
    install)
        install
        ;;
    uninstall)
        uninstall
        ;;
    help)
        help_menu
        ;;
    *)
        echo -e "${RED}Error: Unknown command '${1}'. Please execute '${0} help' to query parameters.${NC}"
        exit 1
        ;;
esac

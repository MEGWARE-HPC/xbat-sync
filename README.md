# xbat-sync - xbat Synchronization Script

This script synchronizes benchmarks between two xbat instances. For more details on xbat visit [xbat](https://xbat.dev).

## Environment generation

- Create an `.env` file and add environment variables to it. The template is as follows:

```ini
XBAT_SOURCE_USER=<user>
XBAT_SOURCE_PASSWORD=<password>
XBAT_SOURCE_ADDRESS=<address>
XBAT_DEST_USER=<user>
XBAT_DEST_PASSWORD=<password>
XBAT_DEST_ADDRESS=<address>

FILTER_KEYS=<filter_key1>,<filter_key2>,...
FILTER_VALUES=<filter_value1>,<filter_value2>,...

CHECK_METRIC_DB=<default: true>
MIN_RUN_NR=<min_run_number>
BATCH_SIZE=<batch_size>
LOAD_LAST_SYNC=<default: false>
```

- You can generate a default .env file to `src` directory use the following command:  

```bash
./setup.sh env src
```
> [!NOTE]  
> Please note: The environment variables for the source and destination XBAT servers must be filled in correctly.  
> FILTER_KEYS and FILTER_VALUES need to be the same length, and connected by commas to avoid adding spaces.

## Developer Usage

- Create a new virtual environment, activate it, and install the required packages.

```bash
cd src

python3 -m venv venv
source venv/bin/activate

pip3 install -r requirements.txt
```

- After setting the environments, the script can be run using the following command:

```bash
python3 run.py
```

## Cronjob installation

- Before executing the script, make sure the `.env` file has been generated in the `src` directory, which contains the required environment variables.
- The setup script (`setup.sh`) can be used to install and uninstall the synchronization script. To schedule the script to run hourly, add a cron job with the `setup.sh` script:

```bash
./setup.sh install
```

## Uninstallation

- To uninstall the script, use:

```bash
./setup.sh uninstall
```

The synchronization script will be removed from the cronjob and `xbat-sync` will be uninstalled.

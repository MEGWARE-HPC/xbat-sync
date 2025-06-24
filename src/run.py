import os
import asyncio
import time
import shutil
from pathlib import Path
from aiohttp import ClientSession, TCPConnector, FormData
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
failed_runNrs = []
load_dotenv()

SRC_USER = os.getenv("XBAT_SOURCE_USER")
SRC_PASSWORD = os.getenv("XBAT_SOURCE_PASSWORD")
SRC_ADDRESS = os.getenv("XBAT_SOURCE_ADDRESS")
DEST_USER = os.getenv("XBAT_DEST_USER")
DEST_PASSWORD = os.getenv("XBAT_DEST_PASSWORD")
DEST_ADDRESS = os.getenv("XBAT_DEST_ADDRESS")
FILTER_KEYS = os.getenv("FILTER_KEYS", "").split(',')
FILTER_VALUES = os.getenv("FILTER_VALUES", "").split(',')
MIN_RUN_NR = os.getenv("MIN_RUN_NR", "0")
CHUNK_SIZE = os.getenv("CHUNK_SIZE", "1")
BATCH_SIZE = os.getenv("BATCH_SIZE", "1")
LOAD_LAST_SYNC = os.getenv("LOAD_LAST_SYNC",
                           "false").lower() in ['true', '1', 'y']
SYNC_PATH = Path("/tmp/xbat/sync")
LAST_SYNC_FILE = SYNC_PATH / "last_sync.txt"
FAILED_SYNC_FILE = SYNC_PATH / "failed_sync.txt"
CHECK_METRIC_DB = os.getenv("CHECK_METRIC_DB",
                            "false").lower() in ['true', '1', 'y']

if len(FILTER_KEYS) != len(FILTER_VALUES):
    raise ValueError("FILTER_KEYS and FILTER_VALUES must have the same length")


async def get_token(session, user, password, address):
    """
    Get an access token for the given user and password
    """
    url = f"https://{address}/oauth/token"
    data = {
        'grant_type': 'password',
        'username': user,
        'password': password,
        "client_id": user
    }
    async with session.post(url, data=data) as response:
        if response.status == 200:
            token_info = await response.json()
            logger.info(f"Successfully got token from {address}")
            return token_info.get('access_token')
        else:
            raise Exception(
                f"Failed to get token from {address}: {await response.text()}")


async def get_all_benchmarks(session, token, address):
    """
    Get all benchmarks information from the given address using the provided token
    """
    url = f"https://{address}/api/v1/benchmarks"
    headers = {'accept': '*/*', 'Authorization': f'Bearer {token}'}
    async with session.get(url, headers=headers) as response:
        if response.status == 200:
            benchmarks_data = await response.json()
            if benchmarks_data and "data" in benchmarks_data:
                return benchmarks_data['data']
        else:
            raise Exception(
                f"Failed to get benchmarks from {address}: {await response.text()}"
            )


async def get_sync_runNrs(src_benchmarks, dest_benchmarks):
    """
    Get the run numbers of the benchmarks to be synchronized
    """
    if FILTER_KEYS != ['']:
        filter_conditions = ', '.join([
            f"\n{key}: {value}"
            for key, value in zip(FILTER_KEYS, FILTER_VALUES)
        ])
        logger.info(f"Filter conditions: {filter_conditions}")
        src_runNrs = [
            benchmark.get('runNr') for benchmark in src_benchmarks if all(
                benchmark.get(FILTER_KEYS[i]) == FILTER_VALUES[i]
                for i in range(len(FILTER_KEYS)))
        ]
    else:
        logger.info(f"No filters are loaded, syncing all benchmarks")
        src_runNrs = [
            benchmark.get('runNr') for benchmark in src_benchmarks
            if benchmark.get('state') not in ["pending", "queued", "running"]
        ]
    dest_runNrs = [benchmark.get('runNr') for benchmark in dest_benchmarks]
    runNrs = sorted([x for x in src_runNrs if x not in dest_runNrs])
    return runNrs


async def export_benchmarks(session, token, address, runNrs, anonymise=False):
    """
    Export benchmarks to be synchronized and save them to SYNC directory
    """
    if not runNrs:
        logger.error("No runNrs for benchmarks provided for export")
        return None, None

    url = f"https://{address}/api/v1/benchmarks/export"
    headers = {
        'accept': 'application/octet-stream',
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {"runNrs": runNrs, "anonymise": anonymise}
    try:
        async with session.post(url, headers=headers, json=data) as response:
            if response.status == 200:
                if CHECK_METRIC_DB:
                    csv_counts = int(response.headers['csv-counts'])
                    if csv_counts > 0:
                        folder_path, tar_path = await export_process(
                            runNrs, response)
                        return folder_path, tar_path
                    else:
                        logger.error(
                            f"No metric data found in Benchmark {runNrs}, skip synchronization..."
                        )
                        return None, None
                else:
                    folder_path, tar_path = await export_process(
                        runNrs, response)
                    return folder_path, tar_path
            else:
                failed_runNrs.extend(runNrs)
                logger.error(
                    f"Failed to export benchmarks {runNrs} from {address}: {await response.text()}"
                )
                return folder_path, None
    except Exception as e:
        failed_runNrs.extend(runNrs)
        logger.error(
            f"An error occurred while exporting benchmarks {runNrs}: {e}")
        return folder_path, None


async def export_process(runNrs, response):
    timestamp_ns = str(time.time_ns())
    folder_path = SYNC_PATH / timestamp_ns
    folder_path.mkdir(parents=True, exist_ok=True)
    if len(runNrs) == 1:
        tar_name = f"{runNrs[0]}.tar.gz"
    else:
        tar_name = f"{runNrs[0]}-{runNrs[-1]}.tar.gz"
    tar_path = folder_path / tar_name
    with tar_path.open('wb') as f:
        while True:
            chunk = await response.content.read(1024)
            if not chunk:
                break
            f.write(chunk)
    logger.debug(f"Benchmarks exported to {tar_path}")
    return folder_path, tar_path


async def import_benchmarks(session,
                            token,
                            address,
                            tar_path,
                            reassignRunNr=False,
                            updateColl=True):
    """
    Import benchmarks from exported files into a destination instance
    """
    if not tar_path:
        logger.error("No file provided for import")
        return None

    url = f"https://{address}/api/v1/benchmarks/import"
    headers = {'accept': '*/*', 'Authorization': f'Bearer {token}'}
    form_data = FormData()
    with tar_path.open('rb') as file:
        form_data.add_field('file',
                            file,
                            content_type='multipart/form-data',
                            filename=tar_path.name)
        form_data.add_field('reassignRunNr', str(reassignRunNr).lower())
        form_data.add_field('updateColl', str(updateColl).lower())
        try:
            async with session.post(url, headers=headers,
                                    data=form_data) as response:
                if response.status == 204:
                    logger.info(
                        f"Benchmarks {tar_path.stem.split('.')[0]} successfully imported into destination xbat"
                    )
                else:
                    failed_runNrs.append(tar_path.stem.split('.')[0])
                    logger.error(
                        f"Failed to import benchmarks {tar_path.stem.split('.')[0]} from {address}: {await response.text()}"
                    )
                return response.status
        except Exception as e:
            failed_runNrs.append(tar_path.stem.split('.')[0])
            logger.error(
                f"An error occurred while importing benchmarks {tar_path.stem.split('.')[0]}: {e}"
            )
            return 0


async def process_chunk(session, src_token, dest_token, runNrs):
    """
    Process a chunk of runNrs by exporting and importing benchmarks.
    """
    logger.info(f"Synchronizing these runNrs now: {runNrs}")
    try:
        folder_path, exported_path = await export_benchmarks(
            session, src_token, SRC_ADDRESS, runNrs)
        import_response = await import_benchmarks(session, dest_token,
                                                  DEST_ADDRESS, exported_path)
        if import_response == 204:
            try:
                shutil.rmtree(exported_path.parent)
            except Exception as e:
                logger.error(
                    f"Error during deletion of original folder: {str(e)}")
    except Exception as e:
        logger.error(
            f"HTTP response {import_response}: An error occurred in chunk processing: {e}"
        )
    if folder_path and folder_path.exists():
        try:
            shutil.rmtree(folder_path)
        except Exception as e:
            logger.error(f"Error during deletion of original folder: {str(e)}")


async def fetch_data(session):
    """
    Fetch necessary data from source and destination.
    """
    src_token = await get_token(session, SRC_USER, SRC_PASSWORD, SRC_ADDRESS)
    dest_token = await get_token(session, DEST_USER, DEST_PASSWORD,
                                 DEST_ADDRESS)

    if not src_token:
        raise ValueError(f"Failed to obtain source {SRC_ADDRESS} token")
    if not dest_token:
        raise ValueError(f"Failed to obtain destination {DEST_ADDRESS} token")

    src_benchmarks = await get_all_benchmarks(session, src_token, SRC_ADDRESS)
    dest_benchmarks = await get_all_benchmarks(session, dest_token,
                                               DEST_ADDRESS)
    runNrs = await get_sync_runNrs(src_benchmarks, dest_benchmarks)
    if MIN_RUN_NR and int(MIN_RUN_NR) > 0:
        min_runNr = int(MIN_RUN_NR)
        start_runNr, end_runNr = load_sync_history()
        if start_runNr and end_runNr:
            if start_runNr < min_runNr and min_runNr < end_runNr:
                min_runNr = end_runNr

        start_index = next((index for index, value in enumerate(runNrs)
                            if value == min_runNr or value > min_runNr), -1)
        if start_index != -1:
            runNrs = runNrs[start_index:]
        else:
            runNrs = []
        if LOAD_LAST_SYNC:
            logger.info(
                f"Loading last synchronization history with runNrs: {start_runNr} - {end_runNr}"
            )
        logger.info(f"Set the minimum runNr to {min_runNr}")

    logger.info(
        f"{len(runNrs)} Benchmarks are currently in the synchronization queue."
    )
    return src_token, dest_token, runNrs


async def process_sync(session, src_token, dest_token, runNrs):
    """
    Process the synchronization of benchmarks in chunks.
    """
    # The number of simultaneous export tasks is CHUNK_SIZE * BATCH_SIZE, but for better performance I recommend using a smaller chunk_size and a larger batch_size.
    if CHUNK_SIZE and int(CHUNK_SIZE) > 0:
        chunk_size = int(CHUNK_SIZE)
        logger.debug(f"Set chunk size to {chunk_size}")
    else:
        chunk_size = 1
    runNrs_chunks = [
        runNrs[i:i + chunk_size] for i in range(0, len(runNrs), chunk_size)
    ]

    if BATCH_SIZE and int(BATCH_SIZE) > 0:
        batch_size = int(BATCH_SIZE)
        logger.debug(f"Set batch size to {batch_size}")
    else:
        batch_size = 1
    num_batches = (len(runNrs_chunks) + batch_size - 1)

    for batch_index in range(num_batches):
        start_index = batch_index * batch_size
        end_index = min(start_index + batch_size, len(runNrs_chunks))
        current_batch = runNrs_chunks[start_index:end_index]

        tasks = [
            process_chunk(session, src_token, dest_token, chunk)
            for chunk in current_batch
        ]
        await asyncio.gather(*tasks)


def save_sync_history(start_runNr, end_runNr):
    with open(LAST_SYNC_FILE, 'w') as file:
        file.write(f"{start_runNr}\n{end_runNr}")


def load_sync_history():
    if LOAD_LAST_SYNC and LAST_SYNC_FILE.exists():
        with open(LAST_SYNC_FILE, 'r') as file:
            lines = file.readlines()
            if len(lines) >= 2:
                return int(lines[0].strip()), int(lines[1].strip())
    return None, None


def save_failed_sync(failed_runNrs):
    if failed_runNrs:
        failed_runNrs = list(set(failed_runNrs))
        if LOAD_LAST_SYNC:
            with open(FAILED_SYNC_FILE, 'a') as file:
                for runNr in sorted(failed_runNrs):
                    file.write(f"{runNr}\n")
        else:
            with open(FAILED_SYNC_FILE, 'w') as file:
                for runNr in sorted(failed_runNrs):
                    file.write(f"{runNr}\n")
    else:
        if FAILED_SYNC_FILE.exists():
            os.remove(FAILED_SYNC_FILE)


async def main():
    start_time = time.time()
    logger.info(f"Starting synchronization ...")
    async with ClientSession(connector=TCPConnector(ssl=False)) as session:
        src_token, dest_token, runNrs = await fetch_data(session)

        if len(runNrs) > 0:
            await process_sync(session, src_token, dest_token, runNrs)
            save_sync_history(runNrs[0], runNrs[-1])

    end_time = time.time()

    if len(runNrs) == 1:
        logger.info(
            f"Synchronization runNrs: {runNrs[0]} completed successfully.")
    elif len(runNrs) > 1:
        logger.info(
            f"Synchronization runNrs: {runNrs[0]} - {runNrs[-1]} completed successfully."
        )
    else:
        logger.info("No Benchmarks to synchronize, exiting...")

    if failed_runNrs:
        logger.error(f"Failed to synchronize runNrs: {sorted(failed_runNrs)}.")
    save_failed_sync(failed_runNrs)

    logger.info(f"Total execution time: {end_time - start_time: .2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())

import os
import asyncio
import aiohttp
import aiofiles
from typing import List, Tuple

# TODO: Lets put all the async utils in a single file, looking to minimize the utils file a bit

async def download_file(url: str, dst: str):
    '''
    Async download routine for an image url to a given file location, will create parent paths.
    Returns url and file location on success and throws exceptions on network errors to be accumulated.
    '''
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        response = await session.get(url)            
        assert response.status == 200
        data = await response.read()

    parent_dirs = os.path.dirname(dst)
    if not os.path.exists(parent_dirs):
        os.makedirs(parent_dirs)

    async with aiofiles.open(dst, 'wb') as outfile:
        await outfile.write(data)
    return url, dst


async def gather_download_routines(urls: List[str], file_names: List[str]):
    '''
    Assemble a list of async download routines for execution. Accumulates exceptions.
    '''
    download_futures = [download_file(url, dst) for url, dst in zip(urls, file_names)]
    return await asyncio.gather(*download_futures, return_exceptions=True)


def download(urls: List[str], filenames: List[str], retry: int = 2) -> Tuple[int, List]:
    '''
    Bulk download a list of urls to their respective filename. Executes async routines for better performance.
    Will retry any failed downloads a set number of times. Return failed download locations otherwise.
    '''
    results = asyncio.run(gather_download_routines(urls, filenames))
    success = set()
    for item in results:
        if isinstance(item, Exception):
            continue
        success.add(item)

    failed = set(zip(urls, filenames)) - success
    
    if failed and retry > 0:
        urls, dsts = tuple(zip(*failed))
        failed = download(urls, dsts, retry=retry - 1)

    return failed

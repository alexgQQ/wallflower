import asyncio
import io
import os
from typing import List, Set, Tuple

import aiofiles
import aiohttp
from PIL import Image


async def download_file(url: str, dst: str):
    """
    Async download routine for an image url to a given file location, will create parent paths.
    Returns url and file location on success and throws exceptions on network errors to be accumulated.
    """
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False)
    ) as session:
        response = await session.get(url)
        assert response.status == 200
        data = await response.read()

    parent_dirs = os.path.dirname(dst)
    if not os.path.exists(parent_dirs):
        os.makedirs(parent_dirs)

    async with aiofiles.open(dst, "wb") as outfile:
        await outfile.write(data)
    return url, dst


async def gather_download_routines(urls: List[str], file_names: List[str]):
    """
    Assemble a list of async download routines for execution. Accumulates exceptions.
    """
    download_futures = [download_file(url, dst) for url, dst in zip(urls, file_names)]
    return await asyncio.gather(*download_futures, return_exceptions=True)


def download(
    urls: List[str], filenames: List[str], retry: int = 2
) -> Set[Tuple[str, str]]:
    """
    Download a list of urls to their respective filename. Executes async routines for better performance.
    Will retry any failed downloads a set number of times. Return failed download locations otherwise.
    """
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


async def load_file(url: str, timeout: int = 1):
    """
    Async load routine for an image url.
    """
    if url.startswith("http"):
        to = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False), timeout=to
        ) as session:
            response = await session.get(url)
            assert response.status == 200
            data = await response.read()
            return Image.open(io.BytesIO(data))
    else:
        async with aiofiles.open(url, mode="rb") as afp:
            data = await afp.read()
            return Image.open(io.BytesIO(data))


async def gather_load_routines(urls: List[str], timeout: int = 1):
    """
    Assemble a list of async load routines for execution.
    """
    load_futures = [load_file(url, timeout=timeout) for url in urls]
    return await asyncio.gather(*load_futures, return_exceptions=True)


def load(uris: List[str], timeout: int = 1):
    """
    Bulk load a list of urls to their respective filename. Executes async routines for better performance.
    """
    data = asyncio.run(gather_load_routines(uris, timeout=timeout))
    errors = []
    results = []
    for url, item in zip(uris, data):
        if isinstance(item, Exception):
            errors.append(url)
            results.append(None)
        else:
            results.append(item)
    return results, errors

import os
import asyncio
import aiohttp
import aiofiles
from gcloud.aio.storage import Storage
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


async def load_file(url: str):
    '''
    Async load routine for an image url.
    '''
    if url.startswith('http'):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            response = await session.get(url)
            assert response.status == 200
            return await response.read()
    else:
        async with aiofiles.open(url, mode='rb') as afp:
            return await afp.read()


async def gather_load_routines(urls: List[str]):
    '''
    Assemble a list of async load routines for execution.
    '''
    load_futures = [load_file(url) for url in urls]
    return await asyncio.gather(*load_futures, return_exceptions=True)


def load(urls: List[str]):
    '''
    Bulk load a list of urls to their respective filename. Executes async routines for better performance.
    '''
    data = asyncio.run(gather_load_routines(urls))
    errors = []
    success = []
    for item in data:
        if isinstance(item, Exception):
            errors.append(item)
        else:
            success.append(item)
    return success, errors


async def upload_file(src: str, dst: str, bucket: str):
    ''' Async upload routine for uploading an image to a google bucket. '''

    async with aiofiles.open(src, mode='rb') as afp:
        fobj = await afp.read()

        async with aiohttp.ClientSession() as session:
            storage = Storage(session=session)
            status = await storage.upload(bucket, dst, fobj)
            return src, dst


async def gather_upload_routines(
    file_names: List[str], destinations: List[str], bucket: str
    ):
    '''
    Gather coroutines for async execution, returns an exception in case of network errors.
    '''
    upload_futures = [upload_file(src, dst, bucket) for src, dst in zip(file_names, destinations)]
    return await asyncio.gather(*upload_futures, return_exceptions=True)


def upload(
    file_names: List[str], destinations: List[str], bucket: str
    ):
    '''
    Bulk upload a list of files to a bucket. Executes async routines for better performance.
    '''
    return asyncio.run(gather_upload_routines(file_names, destinations, bucket))

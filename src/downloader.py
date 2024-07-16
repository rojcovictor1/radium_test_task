import asyncio
import hashlib
import os
import tempfile
from functools import partial

import aiofiles
import aiohttp
from environs import Env
from git import Repo

env = Env()
env.read_env()

REPO_URL = env.str("REPO_URL")
BASE_URL = env.str("BASE_URL")
SEM = asyncio.Semaphore(3)
HTTP_STATUS_OK = 200
CHUNK_SIZE = 4096


async def download_file(session, url, dest):
    async with SEM:
        async with session.get(url) as response:
            if response.status == HTTP_STATUS_OK:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                async with aiofiles.open(dest, 'wb') as file_handle:
                    await file_handle.write(await response.read())
            else:
                raise aiohttp.ClientResponseError(
                    request_info=response.request_info,
                    history=None,
                    status=response.status,
                    message=f"Failed to download {url}, status code: "
                    f"{response.status}"
                )


async def fetch_repository_files():
    temp_dir = tempfile.mkdtemp()
    Repo.clone_from(REPO_URL, temp_dir, branch='master')

    file_paths = []
    for root, _, files in os.walk(temp_dir):
        file_paths.extend(get_relative_paths(root, files, temp_dir))

    return temp_dir, file_paths


def get_relative_paths(root, files, temp_dir):
    paths = []
    for filename in files:
        full_path = os.path.join(root, filename)
        relative_path = os.path.relpath(full_path, temp_dir)
        paths.append(relative_path)
    return paths


async def create_download_tasks(session, file_paths, temp_dir, base_url):
    download_tasks = []
    for file_path in file_paths:
        dest = os.path.join(temp_dir, file_path)
        url = os.path.join(base_url, file_path)
        download_tasks.append(download_file(session, url, dest))

    return download_tasks


def read_chunk(file_handle, chunk_size=CHUNK_SIZE):
    return file_handle.read(chunk_size)


def calculate_sha256(file_path):
    hash_sha256 = hashlib.sha256()
    with open(file_path, 'rb') as file_handle:
        for chunk in iter(partial(read_chunk, file_handle), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


async def main():
    async with aiohttp.ClientSession() as session:
        temp_dir, file_paths = await fetch_repository_files()
        download_tasks = await create_download_tasks(
            session, file_paths, temp_dir, BASE_URL)

        await asyncio.gather(*download_tasks)

        for root, _, files in os.walk(temp_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                sha256_hash = calculate_sha256(file_path)
                print(f"{filename}: {sha256_hash}")


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import hashlib
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiofiles
import aiohttp
import pytest

from src.downloader import (
    calculate_sha256, create_download_tasks, download_file,
    fetch_repository_files, get_relative_paths, main)


@pytest.mark.asyncio
async def test_download_files():
    async with aiohttp.ClientSession() as session:
        temp_dir = tempfile.mkdtemp()
        url = "https://example.com/testfile.txt"
        dest = os.path.join(temp_dir, "testfile.txt")

        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.read = AsyncMock(return_value=b'Test content')

        async with aiohttp.ClientSession().get(url) as response:
            response_mock.__aenter__.return_value = response_mock
            session.get = MagicMock(return_value=response_mock)

            await download_file(session, url, dest)

            assert os.path.exists(dest)
            async with aiofiles.open(dest, 'rb') as filename:
                file_content = await filename.read()
                assert file_content == b'Test content'


@pytest.mark.asyncio
async def test_download_files_failure():
    async with aiohttp.ClientSession() as session:
        temp_dir = tempfile.mkdtemp()
        url = "https://example.com/testfile.txt"
        dest = os.path.join(temp_dir, "testfile.txt")

        response_mock = AsyncMock()
        response_mock.status = 404
        response_mock.__aenter__.return_value = response_mock

        session.get = MagicMock(return_value=response_mock)

        with pytest.raises(aiohttp.ClientResponseError):
            await download_file(session, url, dest)


def test_calculate_sha256():
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"test content")
            temp_file_path = temp_file.name

        hash_value = calculate_sha256(temp_file_path)
        expected_hash = hashlib.sha256(b"test content").hexdigest()
        assert hash_value == expected_hash

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def create_temporary_files(temp_dir):
    file1_path = os.path.join(temp_dir, 'file1.txt')
    file2_path = os.path.join(temp_dir, 'file2.txt')

    with open(file1_path, 'w') as file1:
        file1.write('content1')

    with open(file2_path, 'w') as file2:
        file2.write('content2')

    return file1_path, file2_path


def cleanup_temporary_files(file1_path, file2_path, temp_dir):
    if file1_path:
        os.remove(file1_path)

    if file2_path:
        os.remove(file2_path)

    os.rmdir(temp_dir)


def test_get_relative_paths():
    temp_dir = tempfile.mkdtemp()
    file1_path = None
    file2_path = None

    try:
        file1_path, file2_path = create_temporary_files(temp_dir)

        root, _, files = next(os.walk(temp_dir))
        relative_paths = get_relative_paths(root, files, temp_dir)
        expected_paths = ['file1.txt', 'file2.txt']
        assert sorted(relative_paths) == sorted(expected_paths)

    finally:
        cleanup_temporary_files(file1_path, file2_path, temp_dir)


@pytest.mark.asyncio
async def test_fetch_repository_files():
    with patch('src.downloader.Repo.clone_from') as mock_clone:
        mock_clone.return_value = None

        temp_dir, file_paths = await fetch_repository_files()

        assert os.path.exists(temp_dir)
        assert isinstance(file_paths, list)


@pytest.mark.asyncio
async def test_create_download_tasks():
    async with aiohttp.ClientSession() as session:
        temp_dir = tempfile.mkdtemp()
        file_paths = ['file1.txt', 'file2.txt']

        try:
            download_tasks = await create_download_tasks(
                session, file_paths, temp_dir, 'https://example.com/'
            )
            assert len(download_tasks) == 2
            for task in download_tasks:
                assert asyncio.iscoroutine(task)
        except Exception as error:
            pytest.fail(
                f"Unexpected exception during create_download_tasks: {error}")
        finally:
            os.rmdir(temp_dir)


@pytest.mark.asyncio
async def test_main():
    with patch('src.downloader.fetch_repository_files') as mock_fetch, \
            patch('src.downloader.create_download_tasks') as mock_create, \
            patch('src.downloader.calculate_sha256') as mock_hash, \
            patch('aiohttp.ClientSession.get') as mock_get:
        temp_dir = tempfile.mkdtemp()
        file1_path = 'file1.txt'
        file2_path = 'file2.txt'
        file_paths = [file1_path, file2_path]
        mock_fetch.return_value = (temp_dir, file_paths)

        async def mock_download_file(*args):
            # Create dummy files to simulate download
            async with aiofiles.open(args[1], 'w') as filename:
                await filename.write('Test content')

        mock_create.side_effect = lambda *args: [
            mock_download_file('https://example.com/' + file1_path,
                               os.path.join(temp_dir, file1_path)),
            mock_download_file('https://example.com/' + file2_path,
                               os.path.join(temp_dir, file2_path))
        ]
        mock_hash.return_value = 'dummyhash'

        response_mock = AsyncMock()
        response_mock.status = 200
        response_mock.read = AsyncMock(return_value=b'Test content')
        response_mock.__aenter__.return_value = response_mock

        mock_get.return_value = response_mock

        await main()

        mock_fetch.assert_called_once()
        mock_create.assert_called_once()
        assert mock_hash.call_count == 2


if __name__ == "__main__":
    asyncio.run(main())

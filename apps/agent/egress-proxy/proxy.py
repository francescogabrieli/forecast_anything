"""Small allowlist-only HTTPS CONNECT proxy for the isolated Eve service."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

ALLOWED_HOST = "api.openai.com"
ALLOWED_PORT = 443
MAX_HEADER_BYTES = 16 * 1024


async def reply(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    writer.write(f"HTTP/1.1 {status} {reason}\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()


async def tunnel(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    async def copy(
        source: asyncio.StreamReader, destination: asyncio.StreamWriter
    ) -> None:
        while chunk := await source.read(64 * 1024):
            destination.write(chunk)
            await destination.drain()

    tasks = {
        asyncio.create_task(copy(reader, upstream_writer)),
        asyncio.create_task(copy(upstream_reader, writer)),
    }
    _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    upstream_writer: asyncio.StreamWriter | None = None
    try:
        header_size = 0
        request_line = await asyncio.wait_for(reader.readline(), timeout=5)
        header_size += len(request_line)
        parts = request_line.decode("ascii", errors="replace").strip().split()
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            header_size += len(line)
            if header_size > MAX_HEADER_BYTES:
                await reply(writer, 431, "Request Header Fields Too Large")
                return
            if line in (b"\r\n", b"\n", b""):
                break

        if (
            len(parts) != 3
            or parts[0] != "CONNECT"
            or parts[1] != f"{ALLOWED_HOST}:{ALLOWED_PORT}"
        ):
            await reply(writer, 403, "Egress Denied")
            return

        addresses = await asyncio.get_running_loop().getaddrinfo(
            ALLOWED_HOST, ALLOWED_PORT, type=socket.SOCK_STREAM
        )
        public_addresses = [
            entry[4][0]
            for entry in addresses
            if ipaddress.ip_address(entry[4][0]).is_global
        ]
        if not public_addresses:
            await reply(writer, 502, "No Public Upstream Address")
            return

        for address in public_addresses:
            try:
                upstream_reader, upstream_writer = await asyncio.wait_for(
                    asyncio.open_connection(address, ALLOWED_PORT), timeout=5
                )
                break
            except OSError:
                continue
        else:
            await reply(writer, 502, "Upstream Unavailable")
            return

        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await tunnel(reader, writer, upstream_reader, upstream_writer)
    except (asyncio.TimeoutError, UnicodeError, ValueError, OSError):
        try:
            await reply(writer, 400, "Bad Request")
        except OSError:
            pass
    finally:
        if upstream_writer is not None:
            upstream_writer.close()
            await upstream_writer.wait_closed()
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 3128, limit=MAX_HEADER_BYTES)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

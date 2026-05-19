"""
Generate a Pyrogram String Session for the assistant userbot.

Usage:
    python generate_session.py

You will be asked for your phone number and the login code.
The session string will be printed — copy it to STRING_SESSION in your .env
"""

import asyncio
from pyrogram import Client


async def main():
    print("\n" + "="*55)
    print("  Pyrogram String Session Generator")
    print("="*55)
    print("\nYou need an API_ID and API_HASH from https://my.telegram.org\n")

    api_id   = int(input("Enter API_ID  : ").strip())
    api_hash = input("Enter API_HASH : ").strip()

    async with Client(":memory:", api_id=api_id, api_hash=api_hash) as client:
        session = await client.export_session_string()

    print("\n" + "="*55)
    print("  ✅ Your String Session:")
    print("="*55)
    print(f"\n{session}\n")
    print("Copy the above string and set it as STRING_SESSION in your .env\n")


if __name__ == "__main__":
    asyncio.run(main())

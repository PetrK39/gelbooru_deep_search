import argparse
import asyncio
import os
import sys
import shutil
from argparse import ArgumentError, Namespace, ArgumentParser
from asyncio import AbstractEventLoop
from sys import stderr
from typing import List, Optional, Coroutine, Literal

from attr import dataclass
from pygelbooru import Gelbooru, API_GELBOORU, API_SAFEBOORU, API_RULE34
import logging
from pygelbooru.gelbooru import GelbooruImage
from typing_extensions import LiteralString

MAX_POSTS_PER_SEARCH = 20000
MAX_POSTS_PER_PAGE = 100

@dataclass
class BooruConfig:
    api: str
    max_posts_per_search: int
    max_posts_per_page: int

class TagsException(Exception):
    pass

KNOWN_API = {"gelbooru": BooruConfig(api=API_GELBOORU, max_posts_per_search=20_000, max_posts_per_page=100),
             "safebooru": BooruConfig(api=API_SAFEBOORU, max_posts_per_search=200_000, max_posts_per_page=1_000),
             "rule34": BooruConfig(api=API_RULE34, max_posts_per_search=200_000, max_posts_per_page=1_000)
             }

def build_gelbooru(api_key: str | None = None,
                   user_id: str | None = None,
                   loop: AbstractEventLoop | None = None,
                   api: str = API_GELBOORU) -> Gelbooru:
    return Gelbooru(api_key, user_id, loop, api)

async def generate_deep_search(gelbooru: Gelbooru, booru_config: BooruConfig, tags: list[str], visualizer: bool = False) -> list[str]:
    logging.info("Generating deep search...")

    last_id = await get_last_id_async(gelbooru, tags)

    if not last_id:
        raise TagsException(f"Failed to find any post for search \"{' '.join(tags)}\"")
    
    logging.info(f"Last post id is {last_id}")

    last_seen_id = 0
    steps = []

    while last_seen_id <= last_id:
        temp = await find_last_id_from_min_id_async(gelbooru, booru_config, tags, last_seen_id, visualizer)
        if(temp == -1):
            break
        logging.info(f"Added step: {last_seen_id}, {temp}")
        steps.append((last_seen_id, temp))
        last_seen_id = temp

    return [f"{' '.join(tags)} id:>{step[0]} id:<={step[1]}" for step in steps]

async def get_last_id_async(gelbooru: Gelbooru, tags: list[str]) -> int | None:
    post: GelbooruImage = await gelbooru.search_posts(tags=tags, limit=1)

    if not post:
        return None
    else:
        return post.id

async def find_last_id_from_min_id_async(gelbooru: Gelbooru, booru_config: BooruConfig, tags: list[str], min_id: int, visualizer: bool) -> int:
    # adding 1 since we're checking first and last manually
    max_page = int(booru_config.max_posts_per_search / booru_config.max_posts_per_page)
    left, right = 1, max_page - 1
    last_full_page = -1

    # check if we have more than GELBOORU_MAX_POSTS_PER_SEARCH with current min_id
    posts_last_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                  limit=booru_config.max_posts_per_page,
                                                  page=max_page)
    logging.info(f"Reversed search, last page had {len(posts_last_page)} posts")
    if(len(posts_last_page) == booru_config.max_posts_per_page):
        return posts_last_page[-1].id

    # check if we hit last or beyond last page
    posts_first_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                   limit=booru_config.max_posts_per_page,
                                                   page=0)
    logging.info(f"Reversed search, first page had {len(posts_first_page)} posts")
    if(0 < len(posts_first_page) < booru_config.max_posts_per_page):
        return posts_first_page[-1].id
    elif(len(posts_first_page) == 0):
        return -1
    
    # binary search
    while left <= right:
        mid = (left + right) // 2
        posts = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                            limit=booru_config.max_posts_per_page,
                                            page=mid)
        if visualizer:
            print_visualisation(left, right, mid)
        # if last page with images (0 > len < MAX_PER_PAGE)
        if(0 < len(posts) < booru_config.max_posts_per_page):
            return posts[-1].id
        # elif not last page (len == MAX_PER_PAGE)
        elif(len(posts) == booru_config.max_posts_per_page):
            # save page num in case of next would contain 0 images
            last_full_page = mid
            left = mid + 1
        # else no images (len == 0)
        else:
            right = mid - 1
    
    # if last page with images was full
    posts_last_full = await gelbooru.search_posts(tags=[tags] + ['sort:id:asc', f'id:>{min_id}'], 
                                                  limit=booru_config.max_posts_per_page,
                                                  page=last_full_page)
    return posts_last_full[-1].id

def print_visualisation(left: int, right:int, mid:int):
    terminal_width, _ = shutil.get_terminal_size()
    visualisation = ['-'] * terminal_width
    visualisation[left % terminal_width] = '|'
    visualisation[right % terminal_width] = '|'
    visualisation[mid % terminal_width] = '+'
    string = ''.join(visualisation)
    sys.stderr.write(f"\r{string}")
    sys.stderr.flush()

def check_user_key_both_or_none():
    if args.user and not args.key:
        parser.error("When using --user you should also specify --key")
    elif not args.user and args.key:
        parser.error("When using --key you should also specify --user")

def check_have_limits_on_custom_booru():
    if args.api in KNOWN_API:
        pass
    elif not args.max_per_search and not args.max_per_page:
        parser.error("When using custom booru API --max-per-search and --max-per-page should be specified")
    elif not args.max_per_search:
        parser.error("When using custom booru API --max-per-search should be specified")
    elif not args.max_per_page:
        parser.error("When using custom booru API --max-per-page should be specified")

async def main(tags: list[str],
               user_id: str | None, api_key: str | None,
               api: str, max_per_search: int, max_per_page: int,
               visualizer: bool):
    booru_config = KNOWN_API.get(api, BooruConfig(api=api,
                                                  max_posts_per_search=max_per_search,
                                                  max_posts_per_page=max_per_page))

    gelbooru = build_gelbooru(user_id, api_key, api=booru_config.api)

    try:
        for deep_tag in await generate_deep_search(gelbooru, booru_config, tags, visualizer):
            print(deep_tag)
    except TagsException:
        logging.exception("Failed to find any post for search")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gelbooru Deep Search Generator")

    parser.add_argument("-t", "--tags", type=str, required=True, nargs="+", help="Required. Tags to search for.")

    parser.add_argument("-u", "--user", type=str, required=False, default=None, help="Not required. User ID.")
    parser.add_argument("-k", "--key", type=str, required=False, default=None, help="Not required. API key.")
    parser.add_argument("-a", "--api", type=str, required=False, default="gelbooru", help=f"Not required. API URL or known label such as {', '.join(KNOWN_API.keys())}. Default is \'gelbooru\'.")
    parser.add_argument("--max-per-search", type=int, required=False, help="Required if custom Gelbooru-compatible API is used. Represents maximum offset of pagination")
    parser.add_argument("--max-per-page", type=int, required=False, help="Required if custom Gelbooru-compatible API is used. Represents maximum posts retrieved with one API call")

    parser.add_argument("--no-visualizer", required=False, action="store_false", help="Not required. Disable binary search visualization.")
    parser.add_argument("--log-level", type=str, required=False, choices=["debug", "info", "warning", "error", "critical"], default="info", help="Not required. Logging level. Default is \'info\'.")

    args = parser.parse_args()
    check_user_key_both_or_none()
    check_have_limits_on_custom_booru()

    logging.basicConfig(stream=sys.stderr, level=args.log_level.upper(), format='%(asctime)s - %(levelname)s - %(message)s')

    asyncio.run(main(args.tags, args.user, args.key, args.api, args.no_visualizer, args.max_per_search, args.max_per_page))
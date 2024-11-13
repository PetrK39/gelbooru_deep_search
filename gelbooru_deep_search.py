import argparse
import asyncio
import os
import sys
import shutil
from argparse import ArgumentError, Namespace, ArgumentParser
from asyncio import AbstractEventLoop
from sys import stderr
from typing import List, Optional, Coroutine, Literal, Tuple, Generator

from attr import dataclass
from pygelbooru import Gelbooru, API_GELBOORU, API_SAFEBOORU, API_RULE34
import logging
from pygelbooru.gelbooru import GelbooruImage
from typing_extensions import LiteralString

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

async def generate_deep_search(gelbooru: Gelbooru, booru_config: BooruConfig, tags: list[str], visualizer: bool = False) -> list[tuple[int, int]]:
    logging.info("Generating deep search...")

    # try get last id for given search
    last_id: int | None = await get_last_id_async(gelbooru, tags)

    # raise an exception if there's no posts
    if not last_id:
        raise TagsException(f"Failed to find any post for search \"{' '.join(tags)}\"")
    logging.info(f"Last post id is {last_id}")

    last_seen_id: int = 0
    steps: list[tuple[int, int]] = []

    while last_seen_id <= last_id:
        temp = await find_last_id_from_min_id_async(gelbooru, booru_config, tags, last_seen_id, visualizer)
        if not temp:
            break
        logging.info(f"Added step: {last_seen_id}, {temp}")
        steps.append((last_seen_id, temp))
        last_seen_id = temp

    return steps

async def get_last_id_async(gelbooru: Gelbooru, tags: list[str]) -> int | None:
    if post:= await gelbooru.search_posts(tags=tags, limit=1):
        return post.id
    else:
        return None

async def find_last_id_from_min_id_async(gelbooru: Gelbooru,
                                         booru_config: BooruConfig,
                                         tags: list[str],
                                         min_id: int,
                                         visualizer: bool) -> int | None:
    max_page = int(booru_config.max_posts_per_search / booru_config.max_posts_per_page)

    # check if we have more than max_per_page posts with current min_id
    posts_last_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                  limit=booru_config.max_posts_per_page,
                                                  page=max_page)

    logging.info(f"Reversed search, last page had {len(posts_last_page)} posts")
    # if last page was full return last id
    if len(posts_last_page) == booru_config.max_posts_per_page:
        return posts_last_page[-1].id

    # check if we hit last or beyond last page
    posts_first_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                   limit=booru_config.max_posts_per_page,
                                                   page=0)
    logging.info(f"Reversed search, first page had {len(posts_first_page)} posts")

    # if first page is not full, return it's last id
    if 0 < len(posts_first_page) < booru_config.max_posts_per_page:
        return posts_first_page[-1].id
    # if first page is empty, return None, it's overshot
    elif len(posts_first_page) == 0:
        return None

    # if first and last pages aren't indicating end of the step, find it with binary search
    match await find_last_id_from_min_id_binary_search_async(gelbooru, booru_config, tags, min_id, visualizer):
        case "post", post_id:
            return post_id
        case "page", page_id:
            last_page_posts = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'],
                                                          limit=booru_config.max_posts_per_page,
                                                          page=page_id)
            return last_page_posts[-1].id
        case _:
            raise ValueError("Unknown ID type from find_last_id_from_min_id_binary_search_async()")

async def find_last_id_from_min_id_binary_search_async(gelbooru: Gelbooru,
                                                       booru_config: BooruConfig,
                                                       tags: list[str],
                                                       min_id: int,
                                                       visualizer: bool) -> tuple[str, int]:
    max_page: int = booru_config.max_posts_per_search // booru_config.max_posts_per_page
    left: int
    right: int
    left, right = 1, max_page - 1 # skip first and last since we're checking them manually
    last_full_page: int = 0

    while left <= right:
        mid = (left + right) // 2

        posts = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'],
                                            limit=booru_config.max_posts_per_page,
                                            page=mid)

        if visualizer: print_visualisation(left, right, mid)

        if 0 < len(posts) < booru_config.max_posts_per_page: # non-full ("last") page, what we need
            return "post", posts[-1].id
        elif len(posts) == booru_config.max_posts_per_page: # full page, we're too "left"
            last_full_page = mid # save page num in case of next would contain 0 images
            left = mid + 1
        else: # empty page, we're too "right"
            right = mid - 1

    # if we missed non-full page, return last full page
    return "page", last_full_page

def print_visualisation(left: int, right:int, mid:int):
    terminal_width, _ = shutil.get_terminal_size()
    visualisation = ['-'] * terminal_width
    visualisation[left % terminal_width] = '|'
    visualisation[right % terminal_width] = '|'
    visualisation[mid % terminal_width] = '+'
    string = ''.join(visualisation)
    sys.stderr.write(f"\r{string}")
    sys.stderr.flush()

def format_steps_to_searches(tags: list[str], steps: list[tuple[int, int]]) -> Generator[list[str]]:
    for step in steps:
        yield tags + [f"id:>{step[0]}",  f"id:<={step[1]}"]

def build_argparser() -> ArgumentParser:
    parser = argparse.ArgumentParser(description="Gelbooru Deep Search Generator")

    parser.add_argument("-t", "--tags", type=str, required=True, nargs="+", help="Required. Tags to search for.")

    parser.add_argument("-u", "--user", type=str, required=False, default=None, help="Not required. User ID.")
    parser.add_argument("-k", "--key", type=str, required=False, default=None, help="Not required. API key.")
    parser.add_argument("-a", "--api", type=str, required=False, default="gelbooru",
                        help=f"Not required. API URL or known label such as {', '.join(KNOWN_API.keys())}. Default is \'gelbooru\'.")
    parser.add_argument("--max-per-search", type=int, required=False,
                        help="Required if custom Gelbooru-compatible API is used. Represents maximum offset of pagination")
    parser.add_argument("--max-per-page", type=int, required=False,
                        help="Required if custom Gelbooru-compatible API is used. Represents maximum posts retrieved with one API call")

    parser.add_argument("--no-visualizer", required=False, action="store_false", dest="visualizer",
                        help="Not required. Disable binary search visualization.")
    parser.add_argument("--log-level", type=str, required=False,
                        choices=["debug", "info", "warning", "error", "critical"], default="info",
                        help="Not required. Logging level. Default is \'info\'.")

    return parser

def check_user_key_both_or_none(args: Namespace, parser: ArgumentParser) -> None:
    if args.user and not args.key:
        parser.error("When using --user you should also specify --key")
    elif not args.user and args.key:
        parser.error("When using --key you should also specify --user")

def check_have_limits_on_custom_booru(args: Namespace, parser: ArgumentParser) -> None:
    if args.api in KNOWN_API:
        pass
    elif not args.max_per_search and not args.max_per_page:
        parser.error("When using custom booru API --max-per-search and --max-per-page should be specified")
    elif not args.max_per_search:
        parser.error("When using custom booru API --max-per-search should be specified")
    elif not args.max_per_page:
        parser.error("When using custom booru API --max-per-page should be specified")

def configure_logging(args: Namespace) -> None:
    logging.basicConfig(stream=sys.stderr, level=args.log_level.upper(),
                        format='%(asctime)s - %(levelname)s - %(message)s')

def get_booru_config(args: Namespace) -> BooruConfig:
    return KNOWN_API.get(args.api, BooruConfig(api=args.api,
                                               max_posts_per_search=args.max_per_search,
                                               max_posts_per_page=args.max_per_page))

def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    check_user_key_both_or_none(args, parser)
    check_have_limits_on_custom_booru(args, parser)

    configure_logging(args)

    booru_config = get_booru_config(args)
    gelbooru = build_gelbooru(args.user, args.key, api=booru_config.api)

    try:
        steps = asyncio.run(generate_deep_search(gelbooru, booru_config, args.tags, args.visualizer))
        for tag in format_steps_to_searches(args.tags, steps):
            print(tag)
    except TagsException:
        logging.exception("Failed to find any post for search")

if __name__ == "__main__":
    main()
import argparse
import asyncio
import logging
import sys
import time
from argparse import Namespace, ArgumentParser
from typing import Iterator
from urllib.parse import urlparse

import pygelbooru  # type: ignore
from pygelbooru import Gelbooru # type: ignore
from pygelbooru.gelbooru import GelbooruImage # type: ignore
from attr import dataclass


@dataclass(frozen=True, repr=True)
class BooruConfig:
    api: str
    max_posts_per_search: int
    max_posts_per_page: int
    api_key: str | None = None
    user_id: str | None = None

    def __attrs_post_init__(self) -> None:
        # check api
        if not self.api:
            raise ValueError("api should be provided")
        elif not isinstance(self.api, str):
            raise TypeError(f"Expected api to be str, got {type(self.api).__name__}")
        if not self._is_url(self.api):
            raise ValueError("api should be a valid URL")

        # check max_posts_per_search
        if not self.max_posts_per_search:
            raise ValueError("max_posts_per_search should be provided")
        elif not isinstance(self.max_posts_per_search, int):
            raise TypeError(f"Expected max_posts_per_search to be int, got {type(self.max_posts_per_search).__name__}")
        if self.max_posts_per_search <= 0:
            raise ValueError("max_posts_per_search should be greater than 0")

        # check max_posts_per_page
        if not self.max_posts_per_page:
            raise ValueError("max_posts_per_page should be provided")
        elif not isinstance(self.max_posts_per_page, int):
            raise TypeError(f"Expected max_posts_per_page to be int, got {type(self.max_posts_per_page).__name__}")
        if self.max_posts_per_page <= 0:
            raise ValueError("max_posts_per_page should be greater than 0")

        # check max_posts_per_page > max_posts_per_search
        if self.max_posts_per_page > self.max_posts_per_search:
            raise ValueError("max_posts_per_page cannot be bigger than max_posts_per_search")

        # check api_key
        if not self.api_key:
            pass
        elif not isinstance(self.api_key, str):
            raise TypeError(f"Expected api_key to be str, got {type(self.api_key).__name__}")

        # check user_id
        if not self.user_id:
            pass
        elif not isinstance(self.user_id, str):
            raise TypeError(f"Expected user_id to be str, got {type(self.user_id).__name__}")

        # check api_key and user_id both or none
        if self.api_key and not self.user_id:
            raise ValueError("When specifying api_key, user_id should also be specified")
        elif not self.api_key and self.user_id:
            raise ValueError("When specifying user_id, api_key should also be specified")

    @property
    def max_pages(self) -> int:
        return self.max_posts_per_search // self.max_posts_per_page

    @staticmethod
    def _is_url(url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

class ForbiddenTagsException(Exception):
    pass
class EmptySearchException(Exception):
    pass

KNOWN_API = {
    "gelbooru": BooruConfig(api=pygelbooru.API_GELBOORU, max_posts_per_search=20_000, max_posts_per_page=100),
    "safebooru": BooruConfig(api=pygelbooru.API_SAFEBOORU, max_posts_per_search=200_000, max_posts_per_page=1_000),
    "rule34": BooruConfig(api=pygelbooru.API_RULE34, max_posts_per_search=200_000, max_posts_per_page=1_000)
    }

class GelbooruDeepSearch:
    _logger: logging.Logger
    _booru_config: BooruConfig
    _gelbooru: Gelbooru

    _request_counter: int
    _request_time: float

    # PROPERTIES

    @property
    def booru_config(self) -> BooruConfig:
        """
        Get associated BooruConfig instance
        """
        return self._booru_config

    @booru_config.setter
    def booru_config(self, booru_config: BooruConfig) -> None:
        """
        Set new BooruConfig for the instance and update internal Gelbooru instance
        :param booru_config: The BooruConfig
        :raises ValueError: If passed None
        :raises TypeError: If passed wrong type
        """
        if not booru_config:
            raise ValueError(f"booru_config should be provided")
        elif not isinstance(booru_config, BooruConfig):
            raise TypeError(f"Expected booru_config to be BooruConfig, got {type(booru_config).__name__}")

        self._booru_config = booru_config
        self._gelbooru = Gelbooru(booru_config.api_key, booru_config.user_id, api=booru_config.api)

        self._logger.debug(f"Updated booru_config {self.booru_config}")

    @property
    def request_counter(self) -> int:
        """
        Get request count
        :return:
        """
        return self._request_counter

    @property
    def request_time(self) -> float:
        """
        Get summary amount of request elapsed time in seconds
        :return:
        """
        return self._request_time

    # CTOR

    def __init__(self, booru_config: BooruConfig, log_level: str | int = logging.INFO):
        """
        Ctor of GelbooruDeepSearch
        :param booru_config:
        :raises ValueError: If passed parameter is None
        :raises TypeError: If passed parameter have wrong type
        """
        self._configure_logging()
        self.set_logging_level(log_level)
        self.booru_config = booru_config

        self._request_counter = 0
        self._request_time = 0.0

        self._logger.debug("Initialized GelbooruDeepSearch instance")

    # PUBLIC METHODS

    def set_logging_level(self, level: str | int) -> None:
        """
        Set the logging level for the instance
        :param level: The logging level as a string. Case-insensitive.
        :raises ValueError: If logging level is invalid
        :raises TypeError: If the level is not a string or an integer
        """
        if not isinstance(level, (str, int)):
            raise TypeError(f"Expected str or int, got {type(level).__name__}")
        if isinstance(level, str):
            level = level.upper()

        self._logger.setLevel(level)
        for handler in self._logger.handlers:
            handler.setLevel(level)

        self._logger.info(f"Set logging level to {logging.getLevelName(self._logger.level)}")

    async def get_deep_search_steps_async(self, tags: list[str] | str) -> list[tuple[int, int]]:
        """
        Generates list of tuple[int, int] each contains min and max post id that fits specified booru's search limits
        :param tags: str or list[str] representing a search, would be split by spaces and fixed automatically
        :raises ValueError: When tags is not a list[str]
        :raises ForbiddenTagsException: When tags contain sort:id:* tags as they're used internally
        :raises EmptySearchException: When search returned no results
        :return: list[tuple[int, int]]
        """
        # check and prepare tags
        if not isinstance(tags, str) and (not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags)):
            raise ValueError("Tags must be a string or a list of strings")

        if isinstance(tags, str): tags = [tags]
        tags = [tag for sublist in tags for tag in sublist.split()]
        self._logger.debug(f"Started deep search for tags {tags}")

        # reset stats
        self._logger.debug("Clearing stats")
        self._request_counter = 0
        self._request_time = 0.0

        # lower tags
        tags = [tag.lower() for tag in tags]

        # check tags for forbidden tags
        if "sort:id:asc" in tags or "sort:id:desc" in tags:
            raise ForbiddenTagsException("Tags must not contain sort:id:*")

        # get/check first/last post id
        first_id: int | None = await self._get_first_id_async(tags)
        last_id: int | None = await self._get_last_id_async(tags)
        if not first_id or not last_id:
            raise EmptySearchException(f"Failed to find any post for search \"{' '.join(tags)}\"")

        self._logger.debug(f"First id {first_id}, last id {last_id}")

        steps: list[tuple[int, int]] = []
        step_start: int = first_id

        # main loop, iterates until while condition or until it hits empty search
        while step_start < last_id:
            step_end = await self._find_last_id_linear_async(tags, step_start)
            if not step_end:
                steps.append((step_start, last_id))
                break
            steps.append((step_start, step_end))
            step_start = step_end

        self._logger.debug(f"Generated {len(steps)} steps")
        return steps

    # PRIVATE STATIC METHODS

    @staticmethod
    def _add_reverse_tag(tags: list[str]) -> list[str]:
        """
        Adds a tag to sort posts by id in ascending order
        :param tags:
        :return:
        """
        return tags + ["sort:id:asc"]
    @staticmethod
    def _add_min_tag(tags: list[str], min_id: int) -> list[str]:
        """
        Adds a tag to limit resulting posts with id higher than given
        :param tags:
        :param min_id:
        :return:
        """
        return tags + [f"id:>{min_id}"]
    @staticmethod
    def _add_reverse_and_min_tag(tags: list[str], min_id: int) -> list[str]:
        """
        Adds both a tag to sort posts by id in ascending order and
        a tag to limit resulting posts with id higher than given
        :param tags:
        :param min_id:
        :return:
        """
        return GelbooruDeepSearch._add_min_tag(
            GelbooruDeepSearch._add_reverse_tag(tags), min_id
        )


    # PRIVATE METHODS

    def _configure_logging(self) -> None:
        """
        Performs initial logging configuration
        :return:
        """
        self._logger = logging.Logger(__name__)
        self._logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(funcName)-30s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        self._logger.addHandler(ch)

    async def _gelbooru_search_wrapped(self, tags: list[str], limit: int | None = None,
                                       page: int | None = None) -> list[GelbooruImage] | GelbooruImage:
        if not limit:
            limit = self._booru_config.max_posts_per_page
        if not page:
            page = 0

        self._request_counter += 1
        self._logger.debug(f"Request #{self._request_counter}: {tags = }, {limit = }, {page = }")

        time_start = time.perf_counter()
        result = await self._gelbooru.search_posts(tags=tags, limit=limit, page=page)
        time_end = time.perf_counter()

        self._request_time += time_end - time_start

        self._logger.debug(f"Request #{self.request_counter} completed in {time_end - time_start:.3f}s")

        return result

    async def _get_first_id_async(self, tags: list[str]) -> int | None:
        """
        Get first post id for given tags or None if there's no posts
        :param tags:
        :return:
        """
        return await self._get_last_id_async(self._add_reverse_tag(tags))

    async def _get_last_id_async(self, tags: list[str]) -> int | None:
        """
        Get last post id for given tags or None if there's no posts
        :param tags:
        :return:
        """
        post = await self._gelbooru_search_wrapped(tags, 1)
        if isinstance(post, GelbooruImage):
            return post.id
        else:
            return None

    async def _find_last_id_linear_async(self, tags: list[str], min_id: int) -> int | None:
        """
        Find last post id for given BooruConfig limits starting form min_id or None if there's no posts
        :param tags:
        :param min_id:
        :return:
        """
        self._logger.debug(f"Starting linear search with {tags = }, {min_id = }")

        reversed_and_min_tags = self._add_reverse_and_min_tag(tags, min_id)

        # check if we have more than max_per_page posts with current min_id
        posts_last_page = await self._gelbooru_search_wrapped(tags=reversed_and_min_tags,
                                                              limit=self._booru_config.max_posts_per_page,
                                                              page=self._booru_config.max_pages)
        self._logger.debug(f"Last page returned {len(posts_last_page)} posts")

        # if last page was full return last id
        if len(posts_last_page) == self._booru_config.max_posts_per_page:
            self._logger.debug(f"Last page is full, returning id {posts_last_page[-1].id}")
            return posts_last_page[-1].id

        # check if we hit last or beyond last page
        posts_first_page = await self._gelbooru_search_wrapped(tags=reversed_and_min_tags,
                                                               limit=self._booru_config.max_posts_per_page,
                                                               page=0)
        self._logger.debug(f"First page returned {len(posts_first_page)} posts")

        # if first page is not full, return it's last id
        if 0 < len(posts_first_page) < self._booru_config.max_posts_per_page:
            self._logger.debug(f"First page is not full, returning id {posts_first_page[-1].id}")
            return posts_first_page[-1].id
        # if first page is empty, return None, it's an overshot
        elif len(posts_first_page) == 0:
            self._logger.debug(f"First page is empty, returning None")
            return None

        # if first and last pages aren't indicating end of the step, find it with binary search
        self._logger.debug("Using binary search to find mid page")
        return await self._find_last_id_binary_async(reversed_and_min_tags)

    async def _find_last_id_binary_async(self, reversed_and_min_tags: list[str]) -> int:
        """
        Find last post id for given search using binary search to find last available page
        :param reversed_and_min_tags:
        :return:
        """
        self._logger.debug(f"Starting binary search with tags: {reversed_and_min_tags}")

        left: int
        right: int
        left, right = 1, self._booru_config.max_pages - 1  # skip first and last since we're checking them manually
        last_full_page: int = 0

        while left <= right:
            mid = (left + right) // 2
            self._logger.debug(f"Binary search iteration: {left = }, {right = }, {mid = }")

            posts = await self._gelbooru_search_wrapped(tags=reversed_and_min_tags,
                                                        limit=self._booru_config.max_posts_per_page,
                                                        page=mid)
            self._logger.debug(f"Page {mid} returned {len(posts)} posts")

            if 0 < len(posts) < self._booru_config.max_posts_per_page:  # non-full ("last") page, what we need
                self._logger.debug(f"Found non-full page at {mid}, returning id {posts[-1].id}")
                return posts[-1].id
            elif len(posts) == self._booru_config.max_posts_per_page:  # full page, we're too "left"
                self._logger.debug(f"Page {mid} is full, updating last_full_page to {mid}")
                last_full_page = mid  # save page num in case of next would contain 0 images
                left = mid + 1
            else:  # empty page, we're too "right"
                self._logger.debug(f"Page {mid} is empty")
                right = mid - 1

        self._logger.debug("Binary search finished with no success, retrieving last post from last full page")
        # if we missed non-full page, return last full page's last post
        last_full_page_posts = await self._gelbooru_search_wrapped(tags=reversed_and_min_tags,
                                                                   limit=self._booru_config.max_posts_per_page,
                                                                   page=last_full_page)
        self._logger.debug(f"last full page is {last_full_page}, returning id {last_full_page_posts[-1].id}")
        return last_full_page_posts[-1].id

def format_steps_to_searches(tags: list[str], steps: list[tuple[int, int]]) -> Iterator[list[str]]:
    for i, step in enumerate(steps):
        if i == 0:
            yield tags + [f"id:>={step[0]}", f"id:<={step[1]}"]
        else:
            yield tags + [f"id:>{step[0]}", f"id:<={step[1]}"]

def _build_argparser() -> ArgumentParser:
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

    parser.add_argument("--log-level", type=str, required=False,
                        choices=["debug", "info", "warning", "error", "critical"], default="info",
                        help="Not required. Logging level. Default is \'info\'.")

    return parser

def _build_logger(level: str) -> logging.Logger:
    logger = logging.Logger(__name__)
    logger.setLevel(level.upper())
    ch = logging.StreamHandler()
    ch.setLevel(level.upper())
    formatter = logging.Formatter('%(asctime)s - %(funcName)-30s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger

def _check_user_key_both_or_none(args: Namespace, parser: ArgumentParser) -> None:
    if args.user and not args.key:
        parser.error("When using --user you should also specify --key")
    elif not args.user and args.key:
        parser.error("When using --key you should also specify --user")

def _check_have_limits_on_custom_booru(args: Namespace, parser: ArgumentParser) -> None:
    if args.api in KNOWN_API:
        pass
    elif not args.max_per_search and not args.max_per_page:
        parser.error("When using custom booru API --max-per-search and --max-per-page should be specified")
    elif not args.max_per_search:
        parser.error("When using custom booru API --max-per-search should be specified")
    elif not args.max_per_page:
        parser.error("When using custom booru API --max-per-page should be specified")

def _get_booru_config(args: Namespace) -> BooruConfig:
    if booru_config:= KNOWN_API.get(args.api):
        return booru_config
    else:
        return BooruConfig(api=args.api,
                           max_posts_per_search=args.max_per_search,
                           max_posts_per_page=args.max_per_search,
                           user_id=args.user,
                           api_key=args.key)

def main() -> None:
    parser = _build_argparser()
    args = parser.parse_args()

    _check_user_key_both_or_none(args, parser)
    _check_have_limits_on_custom_booru(args, parser)

    logger = _build_logger(args.log_level)

    booru_config = _get_booru_config(args)
    gds = GelbooruDeepSearch(booru_config, args.log_level)

    try:
        steps = asyncio.run(gds.get_deep_search_steps_async(args.tags))
        logger.info(f"Done in {gds.request_counter} requests with avg of {gds.request_time / gds.request_counter:.3f}s")
        print('\a', file=sys.stderr)  # \alert
        for tags_with_steps in format_steps_to_searches(args.tags, steps):
            print(' '.join(tags_with_steps))
    except TypeError:
        logger.exception("Wrong argument type")
    except ValueError:
        logger.exception("Wrong argument value")
    except ForbiddenTagsException:
        logger.exception("Tags contains forbidden tags")
    except EmptySearchException:
        logger.exception("Failed to find any post for search")

if __name__ == "__main__":
    main()
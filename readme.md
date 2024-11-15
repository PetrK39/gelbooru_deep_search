# Gelbooru Deep Search Generator

This Python script generates search lines that allow you to bypass limitations of Gelbooru search of 20000 images. It helps in efficiently finding posts that match specific tags by breaking down the search into manageable chunks.  

Compatible with any Gelbooru 0.2+ booru.  
Useful for batch Hydrus Network gallery downloading.

## Features

- **Binary Search Algorithm**: Utilizes binary search to efficiently find the end of a batch for given tags. (Up to 8 web requests with default consts.)
- **Customizable Search**: Allows users to specify tags supporting advanced search.

## Requirements

- Python 3.10+
- `pygelbooru` library
- `attrs` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/PetrK39/gelbooru_deep_search.git
    cd gelbooru-deep-search
    ```

2. (Optional) Install requirements
   ```bash
   pip install -r requirements.txt
   ```

2. Install the project:
    ```bash
    pip install .
    ```

## Usage

### Console command mode

To run the script, use the following command:

```bash
gelbooru_deep_search -t <tag1> <tag2>
```
You can use `|` piping or `>` redirect to write output in a file or use it in another script.  

```bash
gelbooru_deep_search -t tag1 tag2 | clip
gelbooru_deep_search -t tag1 tag2 > output.txt
```

Logging would be written into `stderr` stream, while useful data would be written into `stdout`

#### Basic arguments

- `-t`, `--tags`: Space-separated list of tags to search for. You would need to quote your search if it contains special characters
- `-a`, `--api`: Label of predefined API or custom URL. Predefined list: gelbooru, safebooru, rule34. "gelbooru" is default.

See `--help` for more advanced use.  

#### Example

```bash
gelbooru_deep_search -t "{kagamine_rin ~ kagamine_len} -rating:e* -rating:q*"
```

#### Example output

```
{kagamine_rin ~ kagamine_len} -rating:e* -rating:q* id:>=103181 id:<=9383564
{kagamine_rin ~ kagamine_len} -rating:e* -rating:q* id:>9383564 id:<=10999773
```

Each search would return up to 20000 results. (Default API is Gelbooru).  
You could use predefined API or pass your own parameters.  

### Module mode

```python
import asyncio

from gelbooru_deep_search import GelbooruDeepSearch, BooruConfig, KNOWN_API, format_steps_to_searches

bc: BooruConfig = KNOWN_API["gelbooru"]
gds: GelbooruDeepSearch = GelbooruDeepSearch(bc)
tags: list[str] = ["{blue_eyes", "~", "green_eyes}", "-rating:e*", "-rating:q*"]
# or just tags = "{blue_eyes ~ green_eyes} -rating:e* -rating:q*"

steps: list[tuple[int, int]] = asyncio.run(gds.get_deep_search_steps_async(tags))
print(steps) # contains raw step data
print(format_steps_to_searches(tags, steps)) # formatter that would build ready to use search list[str]
```

Note: for some reason web Gelbooru hides last 60 posts even at pid=20000

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests.  

# Gelbooru Deep Search Generator

This Python script generates search lines that allow you to bypass limitations of Gelbooru search of 20000 images. It helps in efficiently finding posts that match specific tags by breaking down the search into manageable chunks.

## Features

- **Binary Search Algorithm**: Utilizes binary search to efficiently find the end of a batch for given tags. (Up to 8 web requests with default consts.)
- **Customizable Search**: Allows users to specify tags and an output file for the search results.
- **Interactive File Handling**: Checks if the output file already exists and prompts the user to either delete it or append to it.

## Requirements

- Python 3.7+
- `pygelbooru` library

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/yourusername/gelbooru-deep-search.git
    cd gelbooru-deep-search
    ```

2. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

To run the script, use the following command:

```bash
python gelbooru_deep_search.py -t <tag1> <tag2> ... -o <output_file>
```

### Arguments

- `-t`, `--tags`: Space-separated list of tags to search for.
- `-o`, `--output`: Output file where the search results will be saved.

### Example

```bash
python gelbooru_deep_search.py -t blue_nails -o search_results.txt
```

### Example output

```
blue_nails id:>0 id:<7444901
blue_nails id:>7444901 id:<10272401
blue_nails id:>10272401 id:<10532280
```

Each search would return up to 20000 results.  
Note: limitation constants and booru api could be changed in script.  

## How It Works

1. **Initialization**: The script initializes the Gelbooru API client.
2. **Last Post ID Retrieval**: It retrieves the last post ID for the given tags.
3. **Binary Search**: Utilizes binary search to find the last post ID within each chunk.
4. **Output**: Writes the search lines to the specified output file.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests.  

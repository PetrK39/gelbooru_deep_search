import argparse
import asyncio
import os
import sys
import shutil
from typing import List
from pygelbooru import Gelbooru

MAX_POSTS_PER_SEARCH = 20000
MAX_POSTS_PER_PAGE = 100

async def generate_deep_search(tags: List[str], output_file: str):
    print("Generating deep search...")

    check_if_output_file_exist(output_file)

    gelbooru = Gelbooru()

    last_id = await get_last_id_async(gelbooru, tags)

    if(last_id == -1):
        print("Check your --tags, search returned no posts!")
        return
    
    print(f"Last post id is {last_id}")

    last_seen_id = 0
    steps = []

    while last_seen_id <= last_id:
        temp = await find_last_id_from_min_id_async(gelbooru, tags, last_seen_id)
        if(temp == -1):
            break
        print(f"Added step: {last_seen_id}, {temp}")
        steps.append((last_seen_id, temp))
        last_seen_id = temp

    with open(output_file, 'a') as file:
        file.writelines(f"{' '.join(tags)} id:>{step[0]} id:<{step[1]}" + '\n' for step in steps)
    print(f"{len(steps)} lines was appended to file")

def check_if_output_file_exist(output_file: str):
    if os.path.exists(output_file):
        print(f"Seems like output file {output_file} already exists.")

        key = input("Do you want to delete it? (Y/n): ").strip().lower()
        if key == 'y' or key == '':
            print(f"Deleting file {output_file}")
            os.remove(output_file)
        else:
            print(f"Output would be appended to existing file")

async def get_last_id_async(gelbooru: Gelbooru, tags: List[str]) -> int:
    post = await gelbooru.search_posts(tags=tags, limit=1)

    if post is None or post.id == 0:
        return -1

    return post.id

async def find_last_id_from_min_id_async(gelbooru: Gelbooru, tags: List[str], min_id: int) -> int:
    # adding 1 since we're checking first and last manually
    max_page = int(MAX_POSTS_PER_SEARCH / MAX_POSTS_PER_PAGE)
    left, right = 1, max_page - 1
    last_full_page = -1

    # check if we have more than GELBOORU_MAX_POSTS_PER_SEARCH with current min_id
    posts_last_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                  limit=MAX_POSTS_PER_PAGE, 
                                                  page=max_page)
    print(f"Reversed search, last page had {len(posts_last_page)} posts")
    if(len(posts_last_page) == MAX_POSTS_PER_PAGE):
        return posts_last_page[-1].id

    # check if we hit last or beyond last page
    posts_first_page = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                                   limit=MAX_POSTS_PER_PAGE, 
                                                   page=0)
    print(f"Reversed search, first page had {len(posts_first_page)} posts")
    if(0 < len(posts_first_page) < MAX_POSTS_PER_PAGE):
        return posts_first_page[-1].id
    elif(len(posts_first_page) == 0):
        return -1
    
    # binary search
    while left <= right:
        mid = (left + right) // 2
        posts = await gelbooru.search_posts(tags=tags + ['sort:id:asc', f'id:>{min_id}'], 
                                            limit=MAX_POSTS_PER_PAGE, 
                                            page=mid)
        print_visualisation(left, right, mid)
        # if last page with images (0 > len < MAX_PER_PAGE)
        if(0 < len(posts) < MAX_POSTS_PER_PAGE):
            return posts[-1].id
        # elif not last page (len == MAX_PER_PAGE)
        elif(len(posts) == MAX_POSTS_PER_PAGE):
            # save page num in case of next would contain 0 images
            last_full_page = mid
            left = mid + 1
        # else no images (len == 0)
        else:
            right = mid - 1
    
    # if last page with images was full
    posts_last_full = await gelbooru.search_posts(tags=[tags] + ['sort:id:asc', f'id:>{min_id}'], 
                                                  limit=MAX_POSTS_PER_PAGE, 
                                                  page=last_full_page)
    return posts_last_full[-1].id

def print_visualisation(left: int, right:int, mid:int):
    terminal_width, _ = shutil.get_terminal_size()
    visualisation = ['-'] * terminal_width
    visualisation[left % terminal_width] = '|'
    visualisation[right % terminal_width] = '|'
    visualisation[mid % terminal_width] = '+'
    string = ''.join(visualisation)
    sys.stdout.write(f"\r{string}")
    sys.stdout.flush()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gelbooru Deep Search Generator")
    parser.add_argument("-t", "--tags", nargs="+", required=True, help="Tags to search for")
    parser.add_argument("-o", "--output", required=True, help="Output file for results")

    args = parser.parse_args()

    asyncio.run(generate_deep_search(args.tags, args.output))
#!/usr/bin/env python3
"""
This script generates an Anki deck with all the leetcode problems currently
known.
"""

import argparse
import asyncio
from doctest import debug_script
import logging
from pyclbr import Function
import requests
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Coroutine, List, Optional, Dict
import json

# https://github.com/kerrickstaley/genanki
import genanki  # type: ignore
from tqdm import tqdm  # type: ignore

import leetcode_anki.helpers.leetcode

LEETCODE_ANKI_MODEL_ID = 4567610856
LEETCODE_ANKI_DECK_ID = 8589798175
OUTPUT_FILE = "leetcode.apkg"
OUTPUT_JSON = "leetcode.json"
ALLOWED_EXTENSIONS = {".py", ".go"}
GRIND75_URL = "https://www.techinterviewhandbook.org/grind75?mode=all&grouping=none&order=all_rounded"
GRIND75_NAME = "grind75"


logging.getLogger().setLevel(logging.INFO)


def get_grind75_problem_slugs() -> List[str]:
    """
    Get the problem slugs for all problems of the Grind 75 problem collection, in order.

    Note that there are more than 75 problems.
    """
    response = requests.get(GRIND75_URL)
    response.raise_for_status()
    return re.findall(b'https://leetcode.com/problems/(.*?)\"', response.content)

def get_grind75_lookup_table() -> Dict[str, int]:
    """
    Get the reverse lookup table to specify the order of each Grind 75 problem.
    """
    return {slug.decode("utf8"):i for i,slug in enumerate(get_grind75_problem_slugs())}

def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments for the script
    """
    parser = argparse.ArgumentParser(description="Generate Anki cards for leetcode")
    parser.add_argument(
        "--start", type=int, help="Start generation from this problem", default=0
    )
    parser.add_argument(
        "--stop", type=int, help="Stop generation on this problem", default=2**64
    )
    parser.add_argument(
        "--page-size",
        type=int,
        help="Get at most this many problems (decrease if leetcode API times out)",
        default=500,
    )
    parser.add_argument(
        "--list-id",
        type=str,
        help="Get all questions from a specific list id (https://leetcode.com/list?selectedList=<list_id>",
        default="",
    )
    parser.add_argument(
        "--output-file", type=str, help="Output filename", default=OUTPUT_FILE
    )

    args = parser.parse_args()

    return args


class LeetcodeNote(genanki.Note):
    """
    Extended base class for the Anki note, that correctly sets the unique
    identifier of the note.
    """

    @property
    def guid(self) -> str:
        # Hash by leetcode task handle
        return genanki.guid_for(self.fields[0])


async def generate_anki_note(
    leetcode_data: leetcode_anki.helpers.leetcode.LeetcodeData,
    leetcode_model: genanki.Model,
    leetcode_task_handle: str,
    output_description: bool = True,
    subsets: Optional[Dict[str, str]] = None,
    suspend: Optional[Function] = None,
) -> LeetcodeNote:
    """
    Generate a single Anki flashcard
    """
    def get_subsets(slug):
        return list(sorted(subsets[slug]))

    def paid_tag(paid):
        if paid:
            return "LeetCode::access::paid"
        return "LeetCode::access::free"

    is_paid = await leetcode_data.paid(leetcode_task_handle)

    suspend = suspend or (lambda x: False)

    note = LeetcodeNote(
        model=leetcode_model,
        fields=[
            leetcode_task_handle,
            str(await leetcode_data.problem_id(leetcode_task_handle)),
            str(await leetcode_data.title(leetcode_task_handle)),
            str(await leetcode_data.category(leetcode_task_handle)),
            await leetcode_data.description(leetcode_task_handle) if output_description else "",
            await leetcode_data.difficulty(leetcode_task_handle),
            "yes" if is_paid else "no",
            str(await leetcode_data.likes(leetcode_task_handle)),
            str(await leetcode_data.dislikes(leetcode_task_handle)),
            str(await leetcode_data.submissions_total(leetcode_task_handle)),
            str(await leetcode_data.submissions_accepted(leetcode_task_handle)),
            str(
                int(
                    await leetcode_data.submissions_accepted(leetcode_task_handle)
                    / await leetcode_data.submissions_total(leetcode_task_handle)
                    * 100
                )
            ),
            str(await leetcode_data.freq_bar(leetcode_task_handle)),
            str(await leetcode_data.total_times_encountered(leetcode_task_handle)),
            json.dumps(await leetcode_data.company_stats(leetcode_task_handle)),
        ],
        tags=await leetcode_data.tags(leetcode_task_handle) + get_subsets(leetcode_task_handle) + [paid_tag(is_paid)],
        # FIXME: sort field doesn't work
        sort_field=str(await leetcode_data.freq_bar(leetcode_task_handle)).zfill(3),
    )
    if suspend(leetcode_task_handle):
        for card in note.cards:
            card.suspend = True
    return note


async def generate(
    start: int, stop: int, page_size: int, list_id: str, output_file: str, grind75_only=False, allow_premium=True, output_description=True,
) -> None:
    """
    Generate an Anki deck
    """
    description_header = "" if not output_description else "<h3>Description</h3>"
    leetcode_model = genanki.Model(
        LEETCODE_ANKI_MODEL_ID,
        "LeetCode model",
        fields=[
            {"name": "Slug"},
            {"name": "Id"},
            {"name": "Title"},
            {"name": "Topic"},
            {"name": "Content"},
            {"name": "Difficulty"},
            {"name": "Paid"},
            {"name": "Likes"},
            {"name": "Dislikes"},
            {"name": "SubmissionsTotal"},
            {"name": "SubmissionsAccepted"},
            {"name": "SumissionAcceptRate"},
            {"name": "Frequency"},
            {"name": "Total Times Encountered"}, # Should correlate to frequency but might not?
            {"name": "Company Stats"},
            # TODO: add hints
        ],
        templates=[
            {
                "name": "LeetCode",
                "qfmt": f"""
                <h2>{{{{Id}}}}. {{{{Title}}}}</h2>
                <b>Difficulty:</b> {{{{Difficulty}}}}<br/>
                &#128077; {{{{Likes}}}} &#128078; {{{{Dislikes}}}}<br/>
                <b>Submissions (total/accepted):</b>
                {{{{SubmissionsTotal}}}}/{{{{SubmissionsAccepted}}}}
                ({{{{SumissionAcceptRate}}}}%)
                <br/>
                <b>Topic:</b> {{{{Topic}}}}<br/>
                <b>Frequency:</b>
                <progress value="{{{{Frequency}}}}" max="100">
                {{{{Frequency}}}}%
                </progress>
                <br/>
                <b>URL:</b>
                <a href='https://leetcode.com/problems/{{{{Slug}}}}/'>
                    https://leetcode.com/problems/{{{{Slug}}}}/
                </a>
                <br/>
                {description_header}
                {{{{Content}}}}
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <b>Discuss URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/discuss/'>
                    https://leetcode.com/problems/{{Slug}}/discuss/
                </a>
                <br/>
                <b>Solution URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/solution/'>
                    https://leetcode.com/problems/{{Slug}}/solution/
                </a>
                <br/>
                """,
            }
        ],
    )
    leetcode_deck = genanki.Deck(LEETCODE_ANKI_DECK_ID, Path(output_file).stem)

    leetcode_data = leetcode_anki.helpers.leetcode.LeetcodeData(
        start, stop, page_size, list_id
    )

    note_generators: List[Awaitable[LeetcodeNote]] = []

    task_handles = await leetcode_data.all_problems_handles()

    # TODO: Add a way to specify subsets (in order) from the command line
    # (probably from a set of files where each slug is on a separate line,
    # and the filename determines the subset name and tag).
    # Provide a separate script to generate a grind75.txt file that can be
    # used as a subset.
    grind75_subset = get_grind75_lookup_table()

    # Sort problems by their location in the Grind 75 list.
    # This order is a good order to prioritize problems.
    # See https://www.techinterviewhandbook.org/grind75/faq for why.
    # All problems not in the subset will sort after these in their original order
    # due to Python using a stable sort algorithm.
    task_handles.sort(key=lambda x: grind75_subset.get(x, len(grind75_subset)))

    if grind75_only:
        task_handles = [x for x in task_handles if x in grind75_subset]
    
    if not allow_premium:
        task_handles = [x for x in task_handles if not await leetcode_data.paid(x)]

    subsets = defaultdict(lambda: {"LeetCode::subset::all"})
    for slug,i in grind75_subset.items():
        if i < 75:
            subsets[slug].add(f"LeetCode::subset::{GRIND75_NAME}::base")
        else:
            subsets[slug].add(f"LeetCode::subset::{GRIND75_NAME}::extended")

    unsuspended_subsets = {
        f"LeetCode::subset::{GRIND75_NAME}::base"
    }

    def suspend(slug):
        # Suspend any cards that are not in an unsuspended subset.
        # Note that if they are in one subset that is unsuspended and
        # another that is not unsuspended, they won't be suspended.
        return len(subsets[slug] & unsuspended_subsets) == 0
        
    logging.info("Generating flashcards")
    for leetcode_task_handle in task_handles:
        note_generators.append(
            generate_anki_note(
                    leetcode_data,
                    leetcode_model,
                    leetcode_task_handle,
                    output_description,
                    subsets,
                    suspend = suspend
            )
        )

    for leetcode_note in tqdm(note_generators, unit="flashcard"):
        leetcode_deck.add_note(await leetcode_note)

    genanki.Package(leetcode_deck).write_to_file(output_file)


async def main() -> None:
    """
    The main script logic
    """
    args = parse_args()

    start, stop, page_size, list_id, output_file = (
        args.start,
        args.stop,
        args.page_size,
        args.list_id,
        args.output_file,
    )
    # TODO: Add CLI parameters for subset and premium
    await generate(start, stop, page_size, list_id, output_file, grind75_only=False, allow_premium=True, output_description=True)


if __name__ == "__main__":
    loop: asyncio.events.AbstractEventLoop = asyncio.get_event_loop()
    loop.run_until_complete(main())

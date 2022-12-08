"""
Break down LeetCode problems by topic and gather stats on frequency of each topic.

Like https://algo.monster/problems/stats, but they seem to ignore how often each
question is asked (or their data is outdated). Also, they don't follow guidelines
for how to render a pie chart.

For information on how to render a pie chart "correctly", see:
The Wall Street Journal Guide to Information Graphics: The Dos and Don'ts of
Presenting Data, Facts, and Figures Paperback – Illustrated, December 16, 2013
by Dona M. Wong  (Author)
(Note: Dona Wong was a PhD student of Edward Tufte)

A nice place to generate pie charts: https://chart-studio.plotly.com/
"""

import yaml
import pandas as pd
 
# Exported to CSV from Anki deck from https://github.com/alexbowe/leetcode-anki-with-grind75
# using https://ankiweb.net/shared/info/1478130872
# Could also load an Anki deck in SQLite instead -
# See https://github.com/ankidroid/Anki-Android/wiki/Database-Structure
CSV_PATH = "Selected Notes.csv"
TOPIC_TAG_PREFIX = "LeetCode::topic::"
GRIND_75_BASE_TAG = "LeetCode::subset::grind75::base"
FAANG_COMPANIES = {"facebook", "amazon", "airbnb", "netflix", "google"}

def get_company_stats_dict(x):
    if not isinstance(x, str):
        return []
    #if x == "nan":
    #    return []
    stats = eval(x)
    if not stats:
        return []
    # Yaml is used because it is a superset of JSON,
    # and this is a hack to get around the way CSV strings
    # are formatted.
    dicts = yaml.load(stats, Loader=yaml.SafeLoader)
    company_stats = [{"company":d["slug"], "times_encountered": d["timesEncountered"]}
                     for d in dicts if d["timesEncountered"] > 0]
    return company_stats

def get_sorted_tag_total_times_encountered(df):
    # Get total times encountered
    new_df = df.groupby("tag").times_encountered.sum()
    
    # Groupby removes the index, so we need to remove it to sort it
    new_df = new_df.reset_index()
    
    new_df = new_df.sort_values(["times_encountered"],ascending=False)
    new_df["freq"] = new_df.times_encountered / new_df.times_encountered.sum()
    new_df["cumsum"] = new_df.times_encountered.cumsum()
    new_df["cumfreq"] = new_df["cumsum"] / new_df.times_encountered.sum()
    return new_df

def get_sorted_slug_total_times_encountered(df):
    # Get total times encountered
    new_df = df.groupby(["slug", "grind75"]).times_encountered.sum()
    
    # Groupby removes the index, so we need to remove it to sort it
    new_df = new_df.reset_index()
    
    new_df = new_df.sort_values(["times_encountered"],ascending=False)
    new_df["freq"] = new_df.times_encountered / new_df.times_encountered.sum()
    new_df["cumsum"] = new_df.times_encountered.cumsum()
    new_df["cumfreq"] = new_df["cumsum"] / new_df.times_encountered.sum()
    return new_df

CSV_COLUMNS = [
    "slug",
    "id",
    "title",
    "topic",
    "content",
    "difficulty",
    "paid",
    "likes",
    "dislikes",
    "submissions_total",
    "submissions_accepted",
    "submission_accept_rate",
    "frequency",
    "total_times_encountered",
    "company_stats",
    "tags",
]

df = pd.read_csv(CSV_PATH, names=CSV_COLUMNS)

# Add grind75 column
df["grind75"] = df.tags.str.contains(GRIND_75_BASE_TAG)

# Split tags column
df["tags"] = df.tags.str.split(" ").tolist()
df = df.explode("tags")

# Filter out non-topic tags
df = df[df.tags.str.startswith(TOPIC_TAG_PREFIX)]

# Remove tag prefix
df["tag"] = df.tags.str[len(TOPIC_TAG_PREFIX):]
del df["tags"] # We don't need the plural column anymore

df["company_stats"] = df.company_stats.apply(get_company_stats_dict)
df = df.explode("company_stats")

# Remove questions that don't have any company stats
df = df[~df.company_stats.isnull()]

# Split company_stats into company and times_encountered fields
df["company"] = df.company_stats.apply(lambda x: x["company"])
df["times_encountered"] = df.company_stats.apply(lambda x: x["times_encountered"])
del df["company_stats"] # We don't need the dict column anymore

# Get total times encountered for each tag
global_total_times_encountered_df = get_sorted_tag_total_times_encountered(df)

# Get FAANG companies only
faang_df = df[df.company.isin(FAANG_COMPANIES)]
faang_total_times_encountered_df = get_sorted_tag_total_times_encountered(faang_df)

# Get slug-based total times encountered
global_slug_total_times_encountered_df = get_sorted_slug_total_times_encountered(df)

# Get slug-based total times encountered for FAANG
faang_slug_total_times_encountered_df = get_sorted_slug_total_times_encountered(faang_df)

# Write to CSV without the original row number
df.to_csv("leetcode_stats.csv", index=False)
global_slug_total_times_encountered_df.to_csv("global_leetcode_slug_stats.csv", index=False)
faang_slug_total_times_encountered_df.to_csv("faang_leetcode_slug_stats.csv", index=False)
global_total_times_encountered_df.to_csv("global_leetcode_tag_stats.csv", index=False)
faang_total_times_encountered_df.to_csv("faang_leetcode_tag_stats.csv", index=False)


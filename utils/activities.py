import random

from discord import Activity, ActivityType

# add all the activities u want to in this dict below
# use format: type (watch = watching) etc.: message


def gen_activities(bot, options: dict = None) -> Activity:
    """Generates and returns a random activity from the provided options"""
    if not options:
        options = {
            0: ["watch", f"{len(bot.users):,} Users"],
            1: ["watch", f"{len(bot.guilds):,} Servers"],
            2: ["listen", "/report"],
            3: ["watch", "Discord Defense Association"],
        }

    activities = []
    for _, activity in options.items():
        activities.append(Activity(type=get_types(activity[0]), name=activity[1]))

    return random.choice(activities)


def get_types(activity_type: str) -> str:
    """Returns an activity type"""

    if activity_type == "watch":
        activity_type = ActivityType.watching
    elif activity_type == "play":
        activity_type = ActivityType.playing
    elif activity_type == "comp":
        activity_type = ActivityType.competing
    elif activity_type == "listen":
        activity_type = ActivityType.listening
    else:
        activity_type = ActivityType.custom

    return activity_type

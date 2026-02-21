"""
Default starter metadata packs for first-run onboarding.
"""

STARTER_MOOD_GROUP = {
    "stable_key": "moodgroup_core_moods",
    "name": "Daily Moods",
    "icon": "mood",
    "color_value": 4282400832,
    "position": 10,
}

STARTER_MOODS = [
    {
        "stable_key": "mood_awesome",
        "key": "awesome",
        "name": "Awesome",
        "icon": "sentiment_very_satisfied",
        "score": 5,
        "category": "positive",
        "color_value": 4280391411,
        "position": 10,
    },
    {
        "stable_key": "mood_good",
        "key": "good",
        "name": "Good",
        "icon": "sentiment_satisfied",
        "score": 4,
        "category": "positive",
        "color_value": 4283215696,
        "position": 20,
    },
    {
        "stable_key": "mood_meh",
        "key": "meh",
        "name": "Meh",
        "icon": "sentiment_neutral",
        "score": 3,
        "category": "neutral",
        "color_value": 4294924066,
        "position": 30,
    },
    {
        "stable_key": "mood_bad",
        "key": "bad",
        "name": "Bad",
        "icon": "sentiment_dissatisfied",
        "score": 2,
        "category": "negative",
        "color_value": 4293467747,
        "position": 40,
    },
    {
        "stable_key": "mood_awful",
        "key": "awful",
        "name": "Awful",
        "icon": "sentiment_very_dissatisfied",
        "score": 1,
        "category": "negative",
        "color_value": 4293023059,
        "position": 50,
    },
]

# Activity groups store palette color as int (`color_value`) to match ActivityGroup model,
# while activities store display color as hex string (`color`) to match Activity model.
STARTER_ACTIVITY_GROUPS = [
    {
        "stable_key": "activitygroup_wellness",
        "name": "Wellness",
        "icon": "heartPulse",
        "color_value": 4280391411,
        "position": 10,
        "activities": [
            {
                "stable_key": "activity_wellness_steps",
                "name": "Steps",
                "icon": "footprints",
                "color": "#3DBE5D",
                "position": 10,
            },
            {
                "stable_key": "activity_wellness_sleep",
                "name": "Sleep",
                "icon": "bedDouble",
                "color": "#4F8DF5",
                "position": 20,
            },
            {
                "stable_key": "activity_wellness_exercise",
                "name": "Exercise",
                "icon": "dumbbell",
                "color": "#F39C12",
                "position": 30,
            },
        ],
    },
    {
        "stable_key": "activitygroup_life_flow",
        "name": "Life Flow",
        "icon": "sparkles",
        "color_value": 4283215696,
        "position": 20,
        "activities": [
            {
                "stable_key": "activity_lifeflow_work",
                "name": "Work",
                "icon": "briefcase",
                "color": "#607D8B",
                "position": 10,
            },
            {
                "stable_key": "activity_lifeflow_family",
                "name": "Family",
                "icon": "house",
                "color": "#E91E63",
                "position": 20,
            },
            {
                "stable_key": "activity_lifeflow_journaling",
                "name": "Journaling",
                "icon": "notebookPen",
                "color": "#8E44AD",
                "position": 30,
            },
        ],
    },
]

STARTER_GOAL_CATEGORY = {
    "stable_key": "goalcat_mindfulness",
    "name": "Mindfulness",
    "icon": "brain",
    "color_value": 4282400832,
    "position": 10,
}

STARTER_GOAL = {
    "stable_key": "goal_mindfulness_journal_5d_week",
    "title": "Journal 5 days this week",
    "icon": "bookOpen",
    "goal_type": "achieve",
    "frequency_type": "weekly",
    "target_count": 5,
    "position": 10,
}

from datetime import datetime


def format_date_for_google(date_input):
    if isinstance(date_input, datetime):
        return date_input.strftime("%Y/%m/%d")
    elif isinstance(date_input, str):
        # Assume user passes valid Gmail-style string
        return date_input
    return None


def build_query(**kwargs):
    query_parts = []

    for key, value in kwargs.items():
        if not value:
            continue

        if key in ["after", "before", "newer_than", "older_than"]:
            value = format_date_for_google(value)

        if key == "text":
            query_parts.append(value)
        elif key == "or_":
            query_parts.append(" OR ".join(value))
        elif key == "and_":
            query_parts.append(" AND ".join(value))
        elif key == "exclude":
            for item in value:
                query_parts.append(f"-{item}")
        else:
            query_parts.append(f"{key}:{value}")

    return " ".join(query_parts)

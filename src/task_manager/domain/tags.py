def normalize_tag_name(name: str) -> str:
    return " ".join(name.strip().lower().split())

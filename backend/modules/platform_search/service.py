from .registry import MODULES
from .schemas import SearchResult


def _token_matches(searchable: str, token: str) -> bool:
    if token in searchable:
        return True

    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y" in searchable

    if token.endswith("s") and len(token) > 3:
        return token[:-1] in searchable

    return False


def search_registry(query: str) -> list[SearchResult]:
    normalized = query.strip().lower()

    if not normalized:
        return []

    tokens = normalized.split()
    scored: list[SearchResult] = []

    for module in MODULES:
        searchable = " ".join(
            [
                module["title"],
                module["description"],
                *module["keywords"],
            ]
        ).lower()

        if not all(
            _token_matches(searchable, token)
            for token in tokens
        ):
            continue

        title_match = normalized in module["title"].lower()
        keyword_match = any(
            normalized in keyword.lower()
            for keyword in module["keywords"]
        )
        score = (
            0.98
            if title_match
            else 0.9
            if keyword_match
            else 0.82
        )

        scored.append(
            SearchResult(
                id=f"module-{module['id']}",
                type="Module",
                title=module["title"],
                subtitle=module["description"],
                module=module["title"],
                score=score,
                action=module["action"],
                metadata={
                    "version": module["version"],
                    "status": module["status"],
                },
            )
        )

    return sorted(scored, key=lambda item: item.score, reverse=True)

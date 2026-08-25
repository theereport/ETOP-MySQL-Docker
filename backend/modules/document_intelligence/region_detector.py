from __future__ import annotations

from .vision_models import Region

CHECK_LABEL = "Envelope and Check Image"


def _intersects_below(rect, y_threshold: float) -> bool:
    return rect.y0 >= y_threshold or rect.y1 > y_threshold


def _candidate_image_rectangles(page, y_threshold: float):
    candidates = []

    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None or not _intersects_below(rect, y_threshold):
            continue

        width = max(rect.x1 - rect.x0, 0.0)
        height = max(rect.y1 - rect.y0, 0.0)

        if width < page.rect.width * 0.45:
            continue
        if height < page.rect.height * 0.12:
            continue

        candidates.append(rect)

    for image in page.get_images(full=True):
        xref = image[0]
        for rect in page.get_image_rects(xref):
            if not _intersects_below(rect, y_threshold):
                continue

            width = max(rect.x1 - rect.x0, 0.0)
            height = max(rect.y1 - rect.y0, 0.0)

            if width < page.rect.width * 0.45:
                continue
            if height < page.rect.height * 0.12:
                continue

            candidates.append(rect)

    return candidates


def _broad_check_region(page, y_threshold: float) -> Region:
    return Region(
        x0=page.rect.x0 + page.rect.width * 0.03,
        y0=min(y_threshold + 2, page.rect.y1),
        x1=page.rect.x1 - page.rect.width * 0.03,
        y1=page.rect.y1 - page.rect.height * 0.03,
    )


def _region_key(region: Region) -> tuple[int, int, int, int]:
    return (
        round(region.x0),
        round(region.y0),
        round(region.x1),
        round(region.y1),
    )


def find_check_region(page, embedded_text: str) -> Region:
    """
    Find the actual check image rectangle, not merely everything below the
    section heading.

    Priority:
    1. Locate the "Envelope and Check Image" label.
    2. Inspect vector drawings and embedded image rectangles below that label.
    3. Select the largest plausible wide rectangle.
    4. Fall back to a conservative crop below the label.
    """
    matches = page.search_for(CHECK_LABEL)

    if matches:
        label = matches[0]
        y_threshold = label.y1 + 2
    else:
        y_threshold = page.rect.y0 + page.rect.height * 0.30

    candidates = _candidate_image_rectangles(page, y_threshold)

    if candidates:
        candidates.sort(
            key=lambda rect: (
                (rect.x1 - rect.x0) * (rect.y1 - rect.y0),
                rect.x1 - rect.x0,
            ),
            reverse=True,
        )
        rect = candidates[0]

        padding = 2.0
        return Region(
            x0=max(page.rect.x0, rect.x0 - padding),
            y0=max(page.rect.y0, rect.y0 - padding),
            x1=min(page.rect.x1, rect.x1 + padding),
            y1=min(page.rect.y1, rect.y1 + padding),
        )

    return _broad_check_region(page, y_threshold)


def find_check_regions(page, embedded_text: str) -> list[tuple[str, Region]]:
    """Return a governed primary crop plus bounded payer-identity fallbacks.

    PNC transaction pages can expose several wide vector/image rectangles.
    The largest rectangle is still the primary check crop, but it may contain
    only the lower check body and omit a payer block printed above it.  The
    fallback regions stay below the transaction page's check-image heading;
    they never cross into another transaction page.
    """

    matches = page.search_for(CHECK_LABEL)
    if matches:
        y_threshold = matches[0].y1 + 2
    else:
        y_threshold = page.rect.y0 + page.rect.height * 0.30

    broad = _broad_check_region(page, y_threshold)
    left_payer = Region(
        x0=broad.x0,
        y0=broad.y0,
        x1=min(
            broad.x1,
            broad.x0 + broad.width * 0.70,
        ),
        y1=broad.y1,
    )
    candidates = [
        ("detected_check_image", find_check_region(page, embedded_text)),
        ("below_label_full_width", broad),
        ("below_label_left_payer", left_payer),
    ]
    unique: list[tuple[str, Region]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for strategy, region in candidates:
        key = _region_key(region)
        if key in seen or region.width <= 0 or region.height <= 0:
            continue
        seen.add(key)
        unique.append((strategy, region))
    return unique

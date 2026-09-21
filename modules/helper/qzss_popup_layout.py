"""Width-aware boundaries for QZSS popup text, independent of Qt."""


MESSAGE_BREAKS = {
    "強い揺れに警戒": (("強い揺れに", "警戒"),),
    "ただちに高台へ避難": (("ただちに", "高台へ避難"),),
    "大規模地震の可能性が平常時より高まっています": (
        ("大規模地震の", "可能性が", "平常時より", "高まっています"),
    ),
    "今後もしばらく海面変動が続くと思われます": (
        ("今後もしばらく", "海面変動が", "続くと", "思われます"),
    ),
    "直ちに建物の中、又は地下に避難して下さい。": (
        ("直ちに", "建物の中、", "又は地下に", "避難して下さい。"),
        ("直ちに", "建物の中、又は", "地下に避難して", "下さい。"),
    ),
}


def message_units(text, width, measure):
    """Choose fitting phrase boundaries; unknown text uses normal wrapping."""
    choices = MESSAGE_BREAKS.get(text, ((text,),))
    return next(
        (units for units in choices if all(measure(unit) <= width for unit in units)),
        choices[-1],
    )


def region_groups(regions, width, measure, wrap_text):
    """Pack complete names; keep a wrapped long name as one page group."""
    groups = []
    current = ""
    for region in regions:
        if measure(region) > width:
            if current:
                groups.append([current])
                current = ""
            groups.append(wrap_text(region))
            continue
        candidate = current + ("・" if current else "") + region
        if current and measure(candidate) > width:
            groups.append([current])
            current = region
        else:
            current = candidate
    if current:
        groups.append([current])
    return groups


def paginate_groups(groups, capacity):
    """Move whole groups to the next page, splitting only oversized groups."""
    if capacity < 1:
        raise ValueError("A page must fit at least one text line")
    pages = [[]]
    for group in groups:
        if not group:
            continue
        if pages[-1] and len(pages[-1]) + len(group) > capacity:
            pages.append([])
        for row in group:
            if len(pages[-1]) == capacity:
                pages.append([])
            pages[-1].append(row)
    return pages

def dms_to_dd(degree: float, minute: float, second: float, direction: str) -> float:
    """
    Converts degrees, minutes, seconds (DMS) to decimal degrees (DD).

    Args:
        degree: The degree part of the coordinate
        minute: The minute part of the coordinate
        second: The second part of the coordinate
        direction: The direction ('N', 'S', 'E', 'W' or 'LU', 'LS', 'BT', 'BB')

    Returns:
        The coordinate in decimal degrees
    """
    dd = degree + minute / 60 + second / 3600
    if direction.upper() in ["S", "LS", "BB"]:
        dd *= -1
    return dd

"""Humanized mouse trajectory generation using cubic Bézier curves and Fitts's Law."""

import math
import random
from typing import List, Tuple


def _ease_in_out(t: float) -> float:
    """Sigmoidal ease-in-out curve following human biomechanical motion."""
    return t * t * (3.0 - 2.0 * t)


def generate_human_trajectory(
    start: Tuple[int, int],
    end: Tuple[int, int],
    steps: int = 25,
    deviation_factor: float = 0.25,
    jitter_px: float = 1.5,
) -> List[Tuple[int, int, float]]:
    """Generates an organic, humanized mouse path between start and end.

    Args:
        start: Initial cursor position (x0, y0).
        end: Target coordinate (x1, y1).
        steps: Number of waypoints along the curve.
        deviation_factor: Curvature amplitude relative to distance.
        jitter_px: Amplitude of organic micro-tremors in pixels.

    Returns:
        List of (x, y, delay_seconds) waypoints.
    """
    x0, y0 = start
    x3, y3 = end

    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy)

    if dist < 5.0 or steps <= 2:
        return [(x3, y3, 0.01)]

    # Normal vector perpendicular to trajectory
    norm_x = -dy / dist if dist > 0 else 0
    norm_y = dx / dist if dist > 0 else 0

    # Randomized control points for cubic Bézier curve
    dev1 = (random.random() - 0.5) * 2.0 * deviation_factor * dist
    dev2 = (random.random() - 0.5) * 2.0 * deviation_factor * dist

    # P1 is ~30% along chord, P2 is ~70% along chord with lateral deviation
    x1 = x0 + dx * 0.3 + norm_x * dev1
    y1 = y0 + dy * 0.3 + norm_y * dev1

    x2 = x0 + dx * 0.7 + norm_x * dev2
    y2 = y0 + dy * 0.7 + norm_y * dev2

    waypoints: List[Tuple[int, int, float]] = []

    for i in range(1, steps + 1):
        raw_t = i / float(steps)
        # Apply human easing (Fitts's Law acceleration/deceleration)
        t = _ease_in_out(raw_t)

        # Cubic Bézier formula
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        bx = uuu * x0 + 3 * uu * t * x1 + 3 * u * tt * x2 + ttt * x3
        by = uuu * y0 + 3 * uu * t * y1 + 3 * u * tt * y2 + ttt * y3

        # Add organic micro-tremors (except at the final landing point)
        if i < steps:
            jitter_x = (random.random() - 0.5) * 2.0 * jitter_px
            jitter_y = (random.random() - 0.5) * 2.0 * jitter_px
            px = int(round(bx + jitter_x))
            py = int(round(by + jitter_y))
        else:
            px = int(round(x3))
            py = int(round(y3))

        # Dynamic variable delay (longer delays during fine-motor deceleration)
        base_delay = 0.005 + 0.008 * (1.0 - math.sin(raw_t * math.pi))
        waypoints.append((px, py, base_delay))

    return waypoints

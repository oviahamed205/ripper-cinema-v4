"""
Human Behavioral Physics Engine (The Ghost User).
Implements Fitts's Law, Cubic Bezier Curves, Gaussian Micro-Jitter,
Scroll Dynamics, and Akamai sensor_data telemetry generation.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class Point:
    x: float
    y: float


@dataclass
class TrajectoryPoint:
    x: float
    y: float
    t: int  # timestamp in milliseconds


class HumanEmulator:
    """Simulates realistic human kinematics and generates anti-bot telemetry."""

    def __init__(self, a: float = 0.15, b: float = 0.25) -> None:
        self.a = a  # Fitts's law intercept (seconds)
        self.b = b  # Fitts's law slope (seconds/bit)

    def calculate_fitts_movement_time(self, d: float, w: float) -> float:
        """
        Fitts's Law equation: T = a + b * log2(1 + D/W).
        Returns calculated movement time in seconds.
        """
        effective_w = max(w, 1.0)
        index_of_difficulty = math.log2(1.0 + (d / effective_w))
        return max(0.2, self.a + self.b * index_of_difficulty)

    def generate_cubic_bezier_path(
        self,
        start: Point,
        end: Point,
        target_width: float = 40.0,
        num_steps: int = 50,
    ) -> List[TrajectoryPoint]:
        """
        Generate a human-like mouse trajectory using Cubic Bezier curves:
        B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3
        With acceleration for t < 0.3, friction deceleration for t > 0.7,
        and Gaussian micro-jitters (std_dev = 2.5px).
        """
        dx = end.x - start.x
        dy = end.y - start.y
        distance = math.hypot(dx, dy)
        total_time_s = self.calculate_fitts_movement_time(distance, target_width)

        # Generate control points with human asymmetry
        # Deviation orthogonal to direct vector
        mid_x = (start.x + end.x) / 2.0
        mid_y = (start.y + end.y) / 2.0
        norm_len = max(distance, 1.0)
        perp_x = -dy / norm_len
        perp_y = dx / norm_len

        # Random control point deviations
        dev1 = random.uniform(-0.25, 0.25) * distance
        dev2 = random.uniform(-0.25, 0.25) * distance

        p0 = start
        p1 = Point(start.x + 0.25 * dx + perp_x * dev1, start.y + 0.25 * dy + perp_y * dev1)
        p2 = Point(start.x + 0.75 * dx + perp_y * dev2, start.y + 0.75 * dy + perp_x * dev2)
        p3 = end

        trajectory: List[TrajectoryPoint] = []
        base_time_ms = int(time.time() * 1000)

        for step in range(num_steps + 1):
            linear_t = step / float(num_steps)

            # Apply acceleration (t < 0.3) and deceleration/friction (t > 0.7) easing
            if linear_t < 0.3:
                # Easing in (acceleration)
                sub_in = max(0.0, min(1.0, linear_t / 0.3))
                t = (sub_in ** 1.8) * 0.3
            elif linear_t > 0.7:
                # Easing out (deceleration)
                sub = max(0.0, min(1.0, (linear_t - 0.7) / 0.3))
                t = 0.7 + (1.0 - (1.0 - sub) ** 1.8) * 0.3
            else:
                t = linear_t

            # Cubic Bezier Formula
            omt = 1.0 - t
            bx = (omt**3) * p0.x + 3 * (omt**2) * t * p1.x + 3 * omt * (t**2) * p2.x + (t**3) * p3.x
            by = (omt**3) * p0.y + 3 * (omt**2) * t * p1.y + 3 * omt * (t**2) * p2.y + (t**3) * p3.y

            # Gaussian micro-jitters (std_dev = 2.5px) except at exact start and end
            if 0 < step < num_steps:
                bx += random.gauss(0, 2.5)
                by += random.gauss(0, 2.5)

            step_time_ms = base_time_ms + int(t * total_time_s * 1000)
            trajectory.append(TrajectoryPoint(x=round(bx, 2), y=round(by, 2), t=step_time_ms))

        return trajectory

    def generate_scroll_burst(self, total_pixels: int = 800) -> List[Dict[str, Any]]:
        """
        Simulate human page scrolling with friction deceleration and pause distribution.
        Friction coefficient between 0.85 and 0.95.
        Velocity starts at ~40px/frame and decays.
        """
        events: List[Dict[str, Any]] = []
        remaining = total_pixels
        friction = random.uniform(0.85, 0.95)
        velocity = 40.0
        current_y = 0.0
        curr_time = int(time.time() * 1000)

        while remaining > 0 and velocity > 1.0:
            delta = min(velocity, float(remaining))
            current_y += delta
            remaining -= int(delta)
            curr_time += random.randint(14, 18)  # ~60fps
            events.append({
                "type": "scroll",
                "y": round(current_y, 1),
                "delta": round(delta, 1),
                "t": curr_time,
            })
            velocity *= friction

        return events

    def generate_akamai_sensor_data(
        self,
        page_url: str,
        start_x: int = 100,
        start_y: int = 200,
        end_x: int = 600,
        end_y: int = 450,
    ) -> Dict[str, Any]:
        """
        Generate complete Akamai Bot Manager sensor_data POST telemetry.
        Includes mouseMovements, keyPresses, touchStart, deviceMotion,
        and strictly monotonically increasing timestamps.
        """
        path = self.generate_cubic_bezier_path(
            start=Point(start_x, start_y),
            end=Point(end_x, end_y),
            target_width=80.0,
            num_steps=30,
        )

        mouse_telemetry: List[List[Any]] = []
        for pt in path:
            mouse_telemetry.append([int(pt.x), int(pt.y), pt.t])

        base_t = path[0].t
        return {
            "sensor_data": {
                "ver": "1.8.2",
                "pageUrl": page_url,
                "mouseMovements": mouse_telemetry,
                "keyPresses": [],
                "touchStart": [],
                "deviceMotion": [
                    {"alpha": 0.0, "beta": 0.0, "gamma": 0.0, "t": base_t + 50},
                    {"alpha": 0.0, "beta": 0.0, "gamma": 0.0, "t": base_t + 150},
                ],
                "screen": {"width": 1920, "height": 1080, "availWidth": 1920, "availHeight": 1040, "colorDepth": 24},
                "hardwareConcurrency": 16,
                "deviceMemory": 8,
            }
        }
